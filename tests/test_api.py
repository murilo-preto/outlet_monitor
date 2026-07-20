from datetime import datetime, timezone

import pytest

import outlet_monitor.api as api_module
from outlet_monitor.models import ProductSnapshot
from outlet_monitor.scrape import ScrapeError


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
