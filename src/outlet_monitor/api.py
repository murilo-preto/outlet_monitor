import csv
import io
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, jsonify, request

from outlet_monitor.notify import send_admin_alert_async, send_price_changes_async
from outlet_monitor.scrape import ScrapeError, fetch_all_products
from outlet_monitor.storage import (
    COLUMNS,
    DEFAULT_DB_PATH,
    append_snapshots,
    changes_since_previous,
    connect,
    count_consecutive_failures,
    count_tracked_products,
    get_category_counts,
    get_last_scrape_run,
    get_last_success_at,
    get_latest_snapshots,
    get_product_history,
    iter_all_snapshots,
    record_scrape_run,
)


def create_app(db_path: Path | str = DEFAULT_DB_PATH) -> Flask:
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path

    @app.after_request
    def add_cors_headers(response):
        # Local dev tool, no auth/cookies involved — the frontend (a different
        # origin/port) needs to call this API directly from the browser.
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.post("/scrape")
    def scrape():
        try:
            result = _perform_scrape(app, trigger="manual")
        except ScrapeError as exc:
            return jsonify({"error": str(exc)}), 502
        return jsonify(result), 201

    @app.get("/status")
    def status():
        """Whether data collection is actually still working.

        Deliberately separate from /health, which is a liveness probe wired
        into the Docker healthcheck. Folding staleness into that would turn
        "Lenovo changed their API" into a container restart loop — strictly
        worse than serving a page with old prices.
        """
        conn = connect(app.config["DB_PATH"])
        try:
            last_run = get_last_scrape_run(conn)
            last_success_at = get_last_success_at(conn)
            failures = count_consecutive_failures(conn)
            tracked = count_tracked_products(conn)
        finally:
            conn.close()

        hours_since = None
        if last_success_at:
            delta = datetime.now(timezone.utc) - datetime.fromisoformat(last_success_at)
            hours_since = round(delta.total_seconds() / 3600, 2)

        interval = _hours_between_fetch()
        return jsonify(
            {
                "last_run": last_run,
                "last_success_at": last_success_at,
                "hours_since_last_success": hours_since,
                "consecutive_failures": failures,
                # One missed cycle plus slack, so a scrape running slightly
                # late never reads as broken.
                "stale": hours_since is not None and hours_since > interval * STALE_MULTIPLIER,
                "products_tracked": tracked,
            }
        )

    @app.get("/categories")
    def list_categories():
        conn = connect(app.config["DB_PATH"])
        try:
            categories = get_category_counts(conn)
        finally:
            conn.close()
        return jsonify(categories)

    @app.get("/products")
    def list_products():
        category = request.args.get("category")
        conn = connect(app.config["DB_PATH"])
        try:
            products = get_latest_snapshots(conn, category=category)
        finally:
            conn.close()
        return jsonify(products)

    @app.get("/products/<product_id>/history")
    def product_history(product_id: str):
        conn = connect(app.config["DB_PATH"])
        try:
            history = get_product_history(conn, product_id)
        finally:
            conn.close()

        if not history:
            return jsonify({"error": f"no history for product_id {product_id!r}"}), 404
        return jsonify(history)

    @app.get("/export.csv")
    def export_csv():
        db_path = app.config["DB_PATH"]

        def generate():
            # The connection is opened inside the generator and closed only
            # once the last row has been written, since rows are pulled from
            # sqlite lazily as the response streams out.
            conn = connect(db_path)
            try:
                buffer = io.StringIO()
                writer = csv.writer(buffer)

                def flush() -> str:
                    chunk = buffer.getvalue()
                    buffer.seek(0)
                    buffer.truncate(0)
                    return chunk

                # BOM so Excel reads the accented product names as UTF-8
                # instead of falling back to the local ANSI codepage.
                yield "\ufeff"
                writer.writerow(COLUMNS)
                yield flush()
                for row in iter_all_snapshots(conn):
                    writer.writerow(row)
                    yield flush()
            finally:
                conn.close()

        filename = f"outlet-monitor-{datetime.now(timezone.utc):%Y-%m-%d}.csv"
        return Response(
            generate(),
            mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return app


DEFAULT_HOURS_BETWEEN_FETCH = 24.0

# How many intervals may pass before the data is called stale: one missed
# cycle plus slack.
STALE_MULTIPLIER = 2.0

DEFAULT_FAILURES_BEFORE_ALERT = 3

log = logging.getLogger(__name__)


def _hours_between_fetch() -> float:
    return float(os.environ.get("HOURS_BETWEEN_FETCH", DEFAULT_HOURS_BETWEEN_FETCH))


def _failures_before_alert() -> int:
    return int(os.environ.get("SCRAPE_FAILURES_BEFORE_ALERT", DEFAULT_FAILURES_BEFORE_ALERT))


def _perform_scrape(app: Flask, trigger: str) -> dict:
    """Run one scrape end to end, recording the outcome either way.

    Re-raises after recording, so both callers keep the error handling they
    already had — 502 for the endpoint, log-and-continue for the scheduler —
    while the failure still becomes visible in /status.
    """
    started_at = datetime.now(timezone.utc)

    try:
        products = fetch_all_products()
    except ScrapeError as exc:
        _record_failure(app, started_at, trigger, str(exc))
        raise

    conn = connect(app.config["DB_PATH"])
    try:
        written = append_snapshots(conn, products)
        changes = changes_since_previous(conn)
        finished_at = datetime.now(timezone.utc)
        record_scrape_run(
            conn,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            status="ok",
            trigger=trigger,
            products_fetched=len(products),
            rows_written=written,
        )
    finally:
        conn.close()

    # Handed to a background thread: the notifier is not on the critical path
    # of a scrape, so this never waits on Telegram.
    send_price_changes_async(changes)

    return {
        "fetched": len(products),
        "written": written,
        "changes": len(changes),
        "timestamp": finished_at.isoformat(),
    }


def _record_failure(app: Flask, started_at: datetime, trigger: str, error: str) -> None:
    """Persist a failed run and alert the operator once per outage streak."""
    conn = connect(app.config["DB_PATH"])
    try:
        record_scrape_run(
            conn,
            started_at=started_at.isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
            status="failed",
            trigger=trigger,
            error=error,
        )
        failures = count_consecutive_failures(conn)
    finally:
        conn.close()

    # Equality, not >=: an outage lasting a week should produce one message,
    # not one per scrape for a week.
    if failures == _failures_before_alert():
        send_admin_alert_async(
            f"⚠️ Falha na coleta do outlet ({failures} tentativas seguidas)\n{error}",
            level="error",
        )


def _run_scheduled_scrapes(app: Flask, interval_seconds: float) -> None:
    """Fetch and persist a snapshot every `interval_seconds`, forever.

    Sleeps first rather than scraping immediately on startup, so a container
    restart/redeploy doesn't trigger an extra scrape on top of the schedule.
    """
    while True:
        time.sleep(interval_seconds)
        try:
            result = _perform_scrape(app, trigger="scheduled")
        except ScrapeError as exc:
            log.error("scheduled scrape failed: %s", exc)
            continue
        except Exception:
            # Any other failure must cost one interval, not every future one:
            # an exception escaping here kills this thread for good, and Flask
            # keeps serving normally afterwards, so a dead thread looks exactly
            # like a healthy deployment that silently stopped collecting data.
            log.exception("scheduled scrape: failed to persist snapshot")
            continue

        log.info(
            "scheduled scrape: fetched=%d written=%d changes=%d",
            result["fetched"],
            result["written"],
            result["changes"],
        )


def start_scheduled_scrapes(app: Flask) -> None:
    hours = _hours_between_fetch()
    thread = threading.Thread(
        target=_run_scheduled_scrapes, args=(app, hours * 3600), daemon=True
    )
    thread.start()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    flask_app = create_app()
    start_scheduled_scrapes(flask_app)
    flask_app.run(host="0.0.0.0", port=5000)
