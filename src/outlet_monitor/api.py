import csv
import io
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, jsonify, request

from outlet_monitor.notify import send_price_changes_async
from outlet_monitor.scrape import ScrapeError, fetch_all_products
from outlet_monitor.storage import (
    COLUMNS,
    DEFAULT_DB_PATH,
    append_snapshots,
    changes_since_previous,
    connect,
    get_category_counts,
    get_latest_snapshots,
    get_product_history,
    iter_all_snapshots,
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
            products = fetch_all_products()
        except ScrapeError as exc:
            return jsonify({"error": str(exc)}), 502

        conn = connect(app.config["DB_PATH"])
        try:
            written = append_snapshots(conn, products)
            changes = changes_since_previous(conn)
        finally:
            conn.close()

        # Handed to a background thread: the notifier is not on the critical
        # path of a scrape, so this response never waits on Telegram.
        send_price_changes_async(changes)

        return (
            jsonify(
                {
                    "fetched": len(products),
                    "written": written,
                    "changes": len(changes),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ),
            201,
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

log = logging.getLogger(__name__)


def _run_scheduled_scrapes(app: Flask, interval_seconds: float) -> None:
    """Fetch and persist a snapshot every `interval_seconds`, forever.

    Sleeps first rather than scraping immediately on startup, so a container
    restart/redeploy doesn't trigger an extra scrape on top of the schedule.
    """
    while True:
        time.sleep(interval_seconds)
        try:
            products = fetch_all_products()
        except ScrapeError as exc:
            log.error("scheduled scrape failed: %s", exc)
            continue

        # Everything below is wrapped because an exception escaping here kills
        # this thread for good: the loop is the only thing keeping the schedule
        # alive, and Flask keeps serving normally afterwards, so a dead thread
        # looks exactly like a healthy deployment that has silently stopped
        # collecting data. sqlite's "database is locked" is the realistic
        # trigger (see storage._apply_pragmas), but any failure here should
        # cost one interval, not every future one.
        try:
            conn = connect(app.config["DB_PATH"])
            try:
                written = append_snapshots(conn, products)
                changes = changes_since_previous(conn)
            finally:
                conn.close()
        except Exception:
            log.exception("scheduled scrape: failed to persist snapshot")
            continue

        send_price_changes_async(changes)
        log.info(
            "scheduled scrape: fetched=%d written=%d changes=%d",
            len(products),
            written,
            len(changes),
        )


def start_scheduled_scrapes(app: Flask) -> None:
    hours = float(os.environ.get("HOURS_BETWEEN_FETCH", DEFAULT_HOURS_BETWEEN_FETCH))
    thread = threading.Thread(
        target=_run_scheduled_scrapes, args=(app, hours * 3600), daemon=True
    )
    thread.start()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    flask_app = create_app()
    start_scheduled_scrapes(flask_app)
    flask_app.run(host="0.0.0.0", port=5000)
