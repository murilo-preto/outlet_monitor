import sqlite3
from datetime import datetime, timezone

import pytest

from outlet_monitor.models import ProductSnapshot
from outlet_monitor.storage import (
    append_snapshots,
    changes_since_previous,
    connect,
    get_category_counts,
    get_latest_snapshots,
)


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


def test_get_latest_snapshots_includes_all_time_lowest_and_highest_price(conn):
    append_snapshots(conn, [make_snapshot(timestamp=datetime(2026, 7, 17, tzinfo=timezone.utc), sale_price=2252.92)])
    append_snapshots(conn, [make_snapshot(timestamp=datetime(2026, 7, 18, tzinfo=timezone.utc), sale_price=1999.00)])
    append_snapshots(conn, [make_snapshot(timestamp=datetime(2026, 7, 19, tzinfo=timezone.utc), sale_price=2100.00)])

    rows = get_latest_snapshots(conn)

    assert rows[0]["sale_price"] == 2100.00
    assert rows[0]["lowest_price"] == 1999.00
    assert rows[0]["highest_price"] == 2252.92


def test_get_latest_snapshots_flags_products_missing_from_latest_scrape(conn):
    append_snapshots(
        conn,
        [
            make_snapshot(product_id="stays", timestamp=datetime(2026, 7, 18, tzinfo=timezone.utc)),
            make_snapshot(product_id="delisted", timestamp=datetime(2026, 7, 18, tzinfo=timezone.utc)),
        ],
    )
    # Second scrape run only returns "stays" — "delisted" dropped out of the outlet.
    append_snapshots(conn, [make_snapshot(product_id="stays", timestamp=datetime(2026, 7, 19, tzinfo=timezone.utc))])

    rows = {row["product_id"]: row for row in get_latest_snapshots(conn)}

    assert rows["stays"]["currently_listed"] is True
    assert rows["delisted"]["currently_listed"] is False


def test_changes_since_previous_is_empty_on_first_scrape(conn):
    # Everything is "new" on a fresh db; reporting it would mean a report with
    # one line per product in the outlet.
    append_snapshots(conn, [make_snapshot(product_id="a"), make_snapshot(product_id="b")])

    assert changes_since_previous(conn) == []


def test_changes_since_previous_reports_price_moves(conn):
    day1 = datetime(2026, 7, 19, tzinfo=timezone.utc)
    day2 = datetime(2026, 7, 20, tzinfo=timezone.utc)
    append_snapshots(
        conn,
        [
            make_snapshot(product_id="dropped", timestamp=day1, sale_price=5000.00),
            make_snapshot(product_id="rose", timestamp=day1, sale_price=3000.00),
            make_snapshot(product_id="flat", timestamp=day1, sale_price=1000.00),
        ],
    )
    append_snapshots(
        conn,
        [
            make_snapshot(product_id="dropped", timestamp=day2, sale_price=4200.00),
            make_snapshot(product_id="rose", timestamp=day2, sale_price=3300.00),
            make_snapshot(product_id="flat", timestamp=day2, sale_price=1000.00),
        ],
    )

    changes = {c["product_id"]: c for c in changes_since_previous(conn)}

    assert set(changes) == {"dropped", "rose"}
    assert (changes["dropped"]["old_price"], changes["dropped"]["new_price"]) == (5000.00, 4200.00)
    assert (changes["rose"]["old_price"], changes["rose"]["new_price"]) == (3000.00, 3300.00)


def test_changes_since_previous_reports_new_products_with_no_old_price(conn):
    day1 = datetime(2026, 7, 19, tzinfo=timezone.utc)
    day2 = datetime(2026, 7, 20, tzinfo=timezone.utc)
    append_snapshots(conn, [make_snapshot(product_id="old", timestamp=day1)])
    append_snapshots(
        conn,
        [
            make_snapshot(product_id="old", timestamp=day2),
            make_snapshot(product_id="fresh", timestamp=day2, name="Yoga Slim 7i", sale_price=4999.00),
        ],
    )

    changes = changes_since_previous(conn)

    assert len(changes) == 1
    assert changes[0]["product_id"] == "fresh"
    assert changes[0]["old_price"] is None
    assert changes[0]["new_price"] == 4999.00
    assert changes[0]["name"] == "Yoga Slim 7i"


def test_changes_since_previous_ignores_delisted_products(conn):
    day1 = datetime(2026, 7, 19, tzinfo=timezone.utc)
    day2 = datetime(2026, 7, 20, tzinfo=timezone.utc)
    append_snapshots(
        conn,
        [
            make_snapshot(product_id="stays", timestamp=day1),
            make_snapshot(product_id="gone", timestamp=day1),
        ],
    )
    append_snapshots(conn, [make_snapshot(product_id="stays", timestamp=day2)])

    assert changes_since_previous(conn) == []


def test_changes_since_previous_compares_only_the_two_newest_runs(conn):
    for day, price in ((17, 5000.00), (18, 4000.00), (19, 4000.00)):
        append_snapshots(
            conn,
            [make_snapshot(timestamp=datetime(2026, 7, day, tzinfo=timezone.utc), sale_price=price)],
        )

    # Price moved between day 17 and 18, but the last two runs are identical.
    assert changes_since_previous(conn) == []


def test_changes_since_previous_ignores_sub_cent_noise(conn):
    day1 = datetime(2026, 7, 19, tzinfo=timezone.utc)
    day2 = datetime(2026, 7, 20, tzinfo=timezone.utc)
    append_snapshots(conn, [make_snapshot(timestamp=day1, sale_price=2252.92)])
    append_snapshots(conn, [make_snapshot(timestamp=day2, sale_price=2252.921)])

    assert changes_since_previous(conn) == []


def test_changes_since_previous_carries_the_category(conn):
    day1 = datetime(2026, 7, 19, tzinfo=timezone.utc)
    day2 = datetime(2026, 7, 20, tzinfo=timezone.utc)
    # "V Series" is the case that matters: the notifier cannot guess it from
    # the product name, so it has to travel with the change.
    append_snapshots(conn, [make_snapshot(name="Lenovo V14 Intel Core i3", category="V Series", timestamp=day1, sale_price=2630.83)])
    append_snapshots(conn, [make_snapshot(name="Lenovo V14 Intel Core i3", category="V Series", timestamp=day2, sale_price=2400.00)])

    changes = changes_since_previous(conn)

    assert changes[0]["category"] == "V Series"


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
            "lowest_price": 90.0,
            "highest_price": 90.0,
            "currently_listed": True,
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
