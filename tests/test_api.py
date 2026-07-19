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
