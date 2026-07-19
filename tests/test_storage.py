import sqlite3
from datetime import datetime, timezone

import pytest

from outlet_monitor.models import ProductSnapshot
from outlet_monitor.storage import append_snapshots, connect, get_category_counts, get_latest_snapshots


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
def conn():
    connection = connect(":memory:")
    yield connection
    connection.close()


def test_connect_creates_schema(conn):
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='price_history'"
    ).fetchall()
    assert tables == [("price_history",)]


def test_connect_is_idempotent_on_existing_file(tmp_path):
    db_path = tmp_path / "price_history.db"
    connect(db_path).close()

    # re-connecting to an already-initialized db file should not error
    conn2 = connect(db_path)
    tables = conn2.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='price_history'"
    ).fetchall()
    conn2.close()
    assert tables == [("price_history",)]


def test_append_snapshots_writes_rows(conn):
    written = append_snapshots(conn, [make_snapshot()])

    assert written == 1
    rows = conn.execute("SELECT product_id, sku, list_price, sale_price FROM price_history").fetchall()
    assert rows == [("82X5X00900_abc", "82X5X00900", 2634.99, 2252.92)]


def test_specs_round_trip_as_structured_list(conn):
    specs = [
        {"label": "Processador", "value": "AMD Ryzen 3 7320U"},
        {"label": "Tela", "value": '14" FHD (1920 x 1080), TN, antirreflexo, 60 Hz'},
    ]
    append_snapshots(conn, [make_snapshot(specs=specs)])

    rows = get_latest_snapshots(conn)

    assert rows[0]["specs"] == specs


def test_append_is_additive_not_overwriting(conn):
    append_snapshots(conn, [make_snapshot(timestamp=datetime(2026, 7, 19, tzinfo=timezone.utc))])
    append_snapshots(conn, [make_snapshot(timestamp=datetime(2026, 7, 20, tzinfo=timezone.utc), sale_price=2100.00)])

    rows = conn.execute(
        "SELECT timestamp, sale_price FROM price_history WHERE product_id = ? ORDER BY timestamp",
        ("82X5X00900_abc",),
    ).fetchall()
    assert len(rows) == 2
    assert rows[0][1] == 2252.92
    assert rows[1][1] == 2100.00


def test_append_snapshots_skips_zero_price_rows(conn):
    written = append_snapshots(conn, [make_snapshot(list_price=0.0, sale_price=0.0)])

    assert written == 0
    assert conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0] == 0


def test_get_latest_snapshots_filters_by_category(conn):
    append_snapshots(
        conn,
        [
            make_snapshot(product_id="think1", category="ThinkPad"),
            make_snapshot(product_id="idea1", category="IdeaPad"),
        ],
    )

    thinkpads = get_latest_snapshots(conn, category="ThinkPad")

    assert [p["product_id"] for p in thinkpads] == ["think1"]


def test_get_category_counts_reflects_latest_snapshot_only(conn):
    append_snapshots(conn, [make_snapshot(product_id="think1", category="ThinkPad")])
    append_snapshots(conn, [make_snapshot(product_id="idea1", category="IdeaPad")])
    append_snapshots(conn, [make_snapshot(product_id="idea2", category="IdeaPad")])

    counts = {row["category"]: row["product_count"] for row in get_category_counts(conn)}

    assert counts == {"ThinkPad": 1, "IdeaPad": 2}


def test_connect_migrates_pre_category_schema(tmp_path):
    db_path = tmp_path / "legacy.db"
    legacy_conn = sqlite3_connect_without_new_columns(db_path)
    legacy_conn.execute(
        "INSERT INTO price_history "
        "(timestamp, product_id, sku, name, url, list_price, sale_price, discount_pct, condition, availability, raw_specs) "
        "VALUES ('2026-07-19T00:00:00+00:00', 'legacy1', 'sku1', 'Old Product', 'https://x', 100.0, 90.0, 10.0, 'New', 'Available', '')"
    )
    legacy_conn.commit()
    legacy_conn.close()

    conn = connect(db_path)
    rows = get_latest_snapshots(conn)
    conn.close()

    assert rows == [
        {
            "id": 1,
            "timestamp": "2026-07-19T00:00:00+00:00",
            "product_id": "legacy1",
            "sku": "sku1",
            "name": "Old Product",
            "url": "https://x",
            "list_price": 100.0,
            "sale_price": 90.0,
            "discount_pct": 10.0,
            "condition": "New",
            "availability": "Available",
            "raw_specs": "",
            "category": "Other",
            "image_url": "",
            "specs": [],
        }
    ]


def sqlite3_connect_without_new_columns(db_path):
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            product_id TEXT NOT NULL,
            sku TEXT NOT NULL,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            list_price REAL NOT NULL,
            sale_price REAL NOT NULL,
            discount_pct REAL NOT NULL,
            condition TEXT NOT NULL,
            availability TEXT NOT NULL,
            raw_specs TEXT NOT NULL
        );
        """
    )
    return conn
