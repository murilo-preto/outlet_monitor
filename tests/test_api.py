import csv
import io
import sqlite3
from datetime import datetime, timezone

import pytest

import outlet_monitor.api as api_module
from outlet_monitor.models import ProductSnapshot
from outlet_monitor.scrape import ScrapeError
from outlet_monitor.storage import COLUMNS, connect


def make_snapshot(**overrides) -> ProductSnapshot:
    defaults = dict(
        timestamp=datetime(2026, 7, 19, tzinfo=timezone.utc),
        product_id="82X5X00900_abc",
        sku="82X5X00900",
        name="IdeaPad 1i",
        url="https://www.lenovo.com/p/laptops/ideapad/82x5x00900",
        list_price=2634.99,
        sale_price=2252.92,
        discount_pct=14.0,
        condition="Remanufaturado Certificado",
        availability="Available",
        raw_specs="Processador: AMD Ryzen 3 7320U",
        category="IdeaPad",
        image_url="https://p3-ofp.static.pub/fes/cms/2021/10/25/hero.png",
        specs=[{"label": "Processador", "value": "AMD Ryzen 3 7320U"}],
    )
    defaults.update(overrides)
    return ProductSnapshot(**defaults)


@pytest.fixture
def client(tmp_path):
    app = api_module.create_app(db_path=tmp_path / "test.db")
    app.config["TESTING"] = True
    return app.test_client()


def test_health(client):
    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_scrape_fetches_and_persists(client, monkeypatch):
    monkeypatch.setattr(api_module, "fetch_all_products", lambda: [make_snapshot()])

    resp = client.post("/scrape")

    assert resp.status_code == 201
    body = resp.get_json()
    assert body["fetched"] == 1
    assert body["written"] == 1
    assert "timestamp" in body


def test_scrape_returns_502_on_scrape_error(client, monkeypatch):
    def raise_scrape_error():
        raise ScrapeError("stale pageFilterId")

    monkeypatch.setattr(api_module, "fetch_all_products", raise_scrape_error)

    resp = client.post("/scrape")

    assert resp.status_code == 502
    assert "stale pageFilterId" in resp.get_json()["error"]


def test_list_products_returns_latest_snapshot_only(client, monkeypatch):
    monkeypatch.setattr(
        api_module,
        "fetch_all_products",
        lambda: [make_snapshot(timestamp=datetime(2026, 7, 19, tzinfo=timezone.utc), sale_price=2252.92)],
    )
    client.post("/scrape")

    monkeypatch.setattr(
        api_module,
        "fetch_all_products",
        lambda: [make_snapshot(timestamp=datetime(2026, 7, 20, tzinfo=timezone.utc), sale_price=2100.00)],
    )
    client.post("/scrape")

    resp = client.get("/products")

    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body) == 1
    assert body[0]["sale_price"] == 2100.00


def test_product_history_returns_all_snapshots(client, monkeypatch):
    monkeypatch.setattr(
        api_module,
        "fetch_all_products",
        lambda: [make_snapshot(timestamp=datetime(2026, 7, 19, tzinfo=timezone.utc), sale_price=2252.92)],
    )
    client.post("/scrape")
    monkeypatch.setattr(
        api_module,
        "fetch_all_products",
        lambda: [make_snapshot(timestamp=datetime(2026, 7, 20, tzinfo=timezone.utc), sale_price=2100.00)],
    )
    client.post("/scrape")

    resp = client.get("/products/82X5X00900_abc/history")

    assert resp.status_code == 200
    body = resp.get_json()
    assert [row["sale_price"] for row in body] == [2252.92, 2100.00]


def test_product_history_404_for_unknown_product(client):
    resp = client.get("/products/does-not-exist/history")

    assert resp.status_code == 404


def test_list_products_includes_lowest_and_highest_price_across_history(client, monkeypatch):
    monkeypatch.setattr(
        api_module,
        "fetch_all_products",
        lambda: [make_snapshot(timestamp=datetime(2026, 7, 18, tzinfo=timezone.utc), sale_price=1999.00)],
    )
    client.post("/scrape")
    monkeypatch.setattr(
        api_module,
        "fetch_all_products",
        lambda: [make_snapshot(timestamp=datetime(2026, 7, 19, tzinfo=timezone.utc), sale_price=2252.92)],
    )
    client.post("/scrape")

    resp = client.get("/products")

    body = resp.get_json()
    assert body[0]["sale_price"] == 2252.92
    assert body[0]["lowest_price"] == 1999.00
    assert body[0]["highest_price"] == 2252.92


def test_list_products_flags_products_missing_from_latest_scrape(client, monkeypatch):
    monkeypatch.setattr(
        api_module,
        "fetch_all_products",
        lambda: [
            make_snapshot(product_id="stays", timestamp=datetime(2026, 7, 18, tzinfo=timezone.utc)),
            make_snapshot(product_id="delisted", timestamp=datetime(2026, 7, 18, tzinfo=timezone.utc)),
        ],
    )
    client.post("/scrape")
    monkeypatch.setattr(
        api_module,
        "fetch_all_products",
        lambda: [make_snapshot(product_id="stays", timestamp=datetime(2026, 7, 19, tzinfo=timezone.utc))],
    )
    client.post("/scrape")

    resp = client.get("/products")

    body = {p["product_id"]: p for p in resp.get_json()}
    assert body["stays"]["currently_listed"] is True
    assert body["delisted"]["currently_listed"] is False


def test_list_products_filters_by_category(client, monkeypatch):
    monkeypatch.setattr(
        api_module,
        "fetch_all_products",
        lambda: [
            make_snapshot(product_id="think1", category="ThinkPad"),
            make_snapshot(product_id="idea1", category="IdeaPad"),
        ],
    )
    client.post("/scrape")

    resp = client.get("/products?category=ThinkPad")

    assert resp.status_code == 200
    body = resp.get_json()
    assert [p["product_id"] for p in body] == ["think1"]


def test_list_categories_returns_counts(client, monkeypatch):
    monkeypatch.setattr(
        api_module,
        "fetch_all_products",
        lambda: [
            make_snapshot(product_id="think1", category="ThinkPad"),
            make_snapshot(product_id="idea1", category="IdeaPad"),
            make_snapshot(product_id="idea2", category="IdeaPad"),
        ],
    )
    client.post("/scrape")

    resp = client.get("/categories")

    assert resp.status_code == 200
    body = {row["category"]: row["product_count"] for row in resp.get_json()}
    assert body == {"ThinkPad": 1, "IdeaPad": 2}


def test_export_csv_returns_every_snapshot_ever_recorded(client, monkeypatch):
    monkeypatch.setattr(
        api_module,
        "fetch_all_products",
        lambda: [make_snapshot(timestamp=datetime(2026, 7, 19, tzinfo=timezone.utc), sale_price=2252.92)],
    )
    client.post("/scrape")
    monkeypatch.setattr(
        api_module,
        "fetch_all_products",
        lambda: [make_snapshot(timestamp=datetime(2026, 7, 20, tzinfo=timezone.utc), sale_price=2100.00)],
    )
    client.post("/scrape")

    resp = client.get("/export.csv")

    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    rows = list(csv.reader(io.StringIO(resp.get_data(as_text=True).lstrip("\ufeff"))))
    assert rows[0] == list(COLUMNS)
    assert [row[COLUMNS.index("sale_price")] for row in rows[1:]] == ["2252.92", "2100.0"]


def test_export_csv_is_a_download_with_a_dated_filename(client):
    resp = client.get("/export.csv")

    disposition = resp.headers["Content-Disposition"]
    assert disposition.startswith("attachment;")
    assert f"outlet-monitor-{datetime.now(timezone.utc):%Y-%m-%d}.csv" in disposition


def test_export_csv_is_empty_apart_from_the_header_with_no_data(client):
    resp = client.get("/export.csv")

    rows = list(csv.reader(io.StringIO(resp.get_data(as_text=True).lstrip("\ufeff"))))
    assert rows == [list(COLUMNS)]


def test_cors_header_present(client):
    resp = client.get("/health")

    assert resp.headers["Access-Control-Allow-Origin"] == "*"


def test_start_scheduled_scrapes_reads_hours_between_fetch_env(client, monkeypatch):
    monkeypatch.setenv("HOURS_BETWEEN_FETCH", "2")
    captured = {}

    class FakeThread:
        def __init__(self, target, args, daemon):
            captured["target"] = target
            captured["interval_seconds"] = args[1]
            captured["daemon"] = daemon

        def start(self):
            captured["started"] = True

    monkeypatch.setattr(api_module.threading, "Thread", FakeThread)

    api_module.start_scheduled_scrapes(client.application)

    assert captured["interval_seconds"] == 2 * 3600
    assert captured["daemon"] is True
    assert captured["started"] is True


def test_start_scheduled_scrapes_defaults_to_24_hours(client, monkeypatch):
    monkeypatch.delenv("HOURS_BETWEEN_FETCH", raising=False)
    captured = {}

    class FakeThread:
        def __init__(self, target, args, daemon):
            captured["interval_seconds"] = args[1]

        def start(self):
            pass

    monkeypatch.setattr(api_module.threading, "Thread", FakeThread)

    api_module.start_scheduled_scrapes(client.application)

    assert captured["interval_seconds"] == 24 * 3600


def test_run_scheduled_scrapes_persists_a_snapshot_per_interval(client, monkeypatch):
    monkeypatch.setattr(api_module, "fetch_all_products", lambda: [make_snapshot()])

    sleep_calls = {"n": 0}

    def fake_sleep(_seconds):
        sleep_calls["n"] += 1
        if sleep_calls["n"] > 1:
            raise RuntimeError("stop loop")

    monkeypatch.setattr(api_module.time, "sleep", fake_sleep)

    with pytest.raises(RuntimeError, match="stop loop"):
        api_module._run_scheduled_scrapes(client.application, 0.01)

    resp = client.get("/products")
    assert len(resp.get_json()) == 1


def test_run_scheduled_scrapes_recovers_from_scrape_error(client, monkeypatch):
    def raise_scrape_error():
        raise ScrapeError("stale pageFilterId")

    monkeypatch.setattr(api_module, "fetch_all_products", raise_scrape_error)

    sleep_calls = {"n": 0}

    def fake_sleep(_seconds):
        sleep_calls["n"] += 1
        if sleep_calls["n"] > 1:
            raise RuntimeError("stop loop")

    monkeypatch.setattr(api_module.time, "sleep", fake_sleep)

    with pytest.raises(RuntimeError, match="stop loop"):
        api_module._run_scheduled_scrapes(client.application, 0.01)


def test_health_stays_a_dumb_liveness_probe(client):
    # Wired into the Docker healthcheck in both compose files: if this ever
    # reflects data staleness, a Lenovo API change becomes a restart loop.
    assert client.get("/health").get_json() == {"status": "ok"}


def test_status_on_an_empty_database_reports_nulls_without_erroring(client):
    body = client.get("/status").get_json()

    assert body["last_run"] is None
    assert body["last_success_at"] is None
    assert body["hours_since_last_success"] is None
    assert body["consecutive_failures"] == 0
    assert body["stale"] is False
    assert body["products_tracked"] == 0


def test_successful_scrape_records_an_ok_run(client, monkeypatch):
    monkeypatch.setattr(api_module, "fetch_all_products", lambda: [make_snapshot()])

    client.post("/scrape")
    body = client.get("/status").get_json()

    assert body["last_run"]["status"] == "ok"
    assert body["last_run"]["trigger"] == "manual"
    assert body["last_run"]["products_fetched"] == 1
    assert body["consecutive_failures"] == 0
    assert body["products_tracked"] == 1


def test_failed_scrape_still_returns_502_and_records_the_failure(client, monkeypatch):
    def raise_scrape_error():
        raise ScrapeError("stale pageFilterId")

    monkeypatch.setattr(api_module, "fetch_all_products", raise_scrape_error)

    assert client.post("/scrape").status_code == 502

    body = client.get("/status").get_json()
    assert body["last_run"]["status"] == "failed"
    assert "stale pageFilterId" in body["last_run"]["error"]
    assert body["consecutive_failures"] == 1


def test_a_database_write_failure_is_recorded_as_a_failed_run(client, monkeypatch):
    monkeypatch.setattr(api_module, "fetch_all_products", lambda: [make_snapshot()])

    def raise_locked(*_args, **_kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(api_module, "append_snapshots", raise_locked)

    # Reaching Lenovo but storing nothing is as much a hole in the history as
    # never reaching them, so it has to show up in /status too.
    with pytest.raises(sqlite3.OperationalError):
        client.post("/scrape")

    body = client.get("/status").get_json()
    assert body["last_run"]["status"] == "failed"
    assert "database is locked" in body["last_run"]["error"]
    assert body["consecutive_failures"] == 1


def test_recording_a_failure_never_masks_the_original_error(client, monkeypatch):
    def raise_scrape_error():
        raise ScrapeError("stale pageFilterId")

    monkeypatch.setattr(api_module, "fetch_all_products", raise_scrape_error)

    def unusable_db(*_args, **_kwargs):
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(api_module, "record_scrape_run", unusable_db)

    # The caller still learns the real problem (502, stale filter id) rather
    # than a 500 about the bookkeeping that failed while reporting it.
    assert client.post("/scrape").status_code == 502


def test_status_flags_stale_data(client, monkeypatch):
    conn = connect(client.application.config["DB_PATH"])
    try:
        api_module.record_scrape_run(
            conn,
            started_at="2026-01-01T00:00:00+00:00",
            finished_at="2026-01-01T00:00:05+00:00",
            status="ok",
            trigger="scheduled",
        )
    finally:
        conn.close()

    monkeypatch.setenv("HOURS_BETWEEN_FETCH", "8")
    body = client.get("/status").get_json()

    assert body["stale"] is True
    assert body["hours_since_last_success"] > 8


def test_repeated_failures_alert_the_operator_exactly_once(client, monkeypatch):
    def raise_scrape_error():
        raise ScrapeError("stale pageFilterId")

    monkeypatch.setattr(api_module, "fetch_all_products", raise_scrape_error)
    monkeypatch.setenv("SCRAPE_FAILURES_BEFORE_ALERT", "3")

    alerts = []
    monkeypatch.setattr(
        api_module, "send_admin_alert_async", lambda text, level="warning": alerts.append(text)
    )

    for _ in range(5):
        client.post("/scrape")

    # One message per outage, not one per failed scrape: with >= instead of ==
    # a week-long Lenovo change would send twenty-one identical alerts.
    assert len(alerts) == 1
    assert "3 tentativas seguidas" in alerts[0]


def test_run_scheduled_scrapes_survives_a_database_write_failure(client, monkeypatch):
    """A locked/failing database must cost one interval, not the whole schedule.

    Before this was handled, the OperationalError propagated out of the loop
    and killed the daemon thread outright — Flask kept serving, so the
    deployment looked healthy while silently never scraping again.
    """
    monkeypatch.setattr(api_module, "fetch_all_products", lambda: [make_snapshot()])

    def raise_locked(*_args, **_kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(api_module, "append_snapshots", raise_locked)

    sleep_calls = {"n": 0}

    def fake_sleep(_seconds):
        sleep_calls["n"] += 1
        if sleep_calls["n"] > 2:
            raise RuntimeError("stop loop")

    monkeypatch.setattr(api_module.time, "sleep", fake_sleep)

    # Reaching the "stop loop" sentinel means the write failure was swallowed
    # and the loop went round again, rather than the thread dying on the first.
    with pytest.raises(RuntimeError, match="stop loop"):
        api_module._run_scheduled_scrapes(client.application, 0.01)

    assert sleep_calls["n"] == 3


def test_scheduled_scrape_failure_is_recorded_not_just_logged(client, monkeypatch):
    def raise_scrape_error():
        raise ScrapeError("stale pageFilterId")

    monkeypatch.setattr(api_module, "fetch_all_products", raise_scrape_error)

    sleep_calls = {"n": 0}

    def fake_sleep(_seconds):
        sleep_calls["n"] += 1
        if sleep_calls["n"] > 1:
            raise RuntimeError("stop loop")

    monkeypatch.setattr(api_module.time, "sleep", fake_sleep)

    with pytest.raises(RuntimeError, match="stop loop"):
        api_module._run_scheduled_scrapes(client.application, 0.01)

    # The whole point: a background failure has to leave a trace somewhere the
    # UI can see, not only in a log line that scrolls away.
    body = client.get("/status").get_json()
    assert body["last_run"]["status"] == "failed"
    assert body["last_run"]["trigger"] == "scheduled"
