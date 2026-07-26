import sqlite3
from datetime import datetime, timezone

import pytest

from outlet_monitor.models import ProductSnapshot
from outlet_monitor import specs as specs_parser
from outlet_monitor.storage import (
    CREATE_TABLE_SQL,
    LATEST_SNAPSHOT_SQL,
    SPECS_VERSION_KEY,
    _meta_get,
    append_snapshots,
    changes_since_previous,
    connect,
    count_consecutive_failures,
    get_category_counts,
    get_last_scrape_run,
    get_last_success_at,
    get_latest_snapshots,
    record_scrape_run,
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


def test_connect_puts_a_file_backed_db_in_wal_mode(tmp_path):
    # WAL is what lets a slow /export.csv reader coexist with the scheduled
    # scrape's writer instead of locking it out.
    db_path = tmp_path / "price_history.db"
    conn = connect(db_path)
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    finally:
        conn.close()

    assert mode == "wal"
    assert timeout == 10000


def test_connect_builds_the_covering_index_and_drops_the_redundant_ones(conn):
    indexes = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='price_history'"
        )
    }

    assert "idx_price_history_pid_ts_price" in indexes
    assert "idx_price_history_ts_product" in indexes
    assert not indexes & {
        "idx_price_history_product_id",
        "idx_price_history_timestamp",
        "idx_price_history_category",
    }


def test_connect_drops_redundant_indexes_left_by_an_older_schema(tmp_path):
    db_path = tmp_path / "price_history.db"
    old = sqlite3.connect(db_path)
    old.executescript(CREATE_TABLE_SQL)
    old.executescript(
        "CREATE INDEX idx_price_history_product_id ON price_history(product_id);"
        "CREATE INDEX idx_price_history_timestamp ON price_history(timestamp);"
        "CREATE INDEX idx_price_history_category ON price_history(category);"
    )
    old.commit()
    old.close()

    conn = connect(db_path)
    try:
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='price_history'"
            )
        }
    finally:
        conn.close()

    assert "idx_price_history_pid_ts_price" in indexes
    assert not indexes & {
        "idx_price_history_product_id",
        "idx_price_history_timestamp",
        "idx_price_history_category",
    }


def test_latest_snapshot_query_uses_the_covering_index(conn):
    append_snapshots(conn, [make_snapshot()])
    plan = "\n".join(
        str(row) for row in conn.execute("EXPLAIN QUERY PLAN " + LATEST_SNAPSHOT_SQL)
    )

    # The whole point of the composite index is that both GROUP BY subqueries
    # resolve without touching the main table.
    assert plan.count("COVERING INDEX idx_price_history_pid_ts_price") == 2


def test_append_snapshots_stores_the_parsed_specs(conn):
    append_snapshots(
        conn,
        [
            make_snapshot(
                specs=[
                    {"label": "Memória", "value": "8GB Soldered DDR4-3200 + 8GB SODIMM DDR4-3200"},
                    {"label": "Armazenamento", "value": "1TB SSD M.2 2242 PCIe® 4.0x4 NVMe®"},
                    {"label": "Tela", "value": '15,6" FHD (1920 x 1080), TN'},
                    {"label": "Processador", "value": "Intel Core™ i5-13420H, 8C"},
                    {"label": "Placa de Vídeo", "value": "NVIDIA® GeForce RTX™ 4050 6GB GDDR6"},
                ]
            )
        ],
    )

    row = get_latest_snapshots(conn)[0]

    assert (row["ram_gb"], row["storage_gb"], row["screen_in"]) == (16, 1024, 15.6)
    assert (row["cpu_brand"], row["cpu_model"]) == ("Intel", "i5-13420H")
    # sqlite stores this as an integer; readers must see a real bool.
    assert row["gpu_discrete"] is True


def test_append_snapshots_stores_null_for_unparseable_specs(conn):
    append_snapshots(conn, [make_snapshot(specs=[{"label": "Memória", "value": "sob consulta"}])])

    row = get_latest_snapshots(conn)[0]

    # NULL, not 0 — the difference decides whether a "16 GB or more" filter
    # excludes this row or treats it as a machine with no memory.
    assert row["ram_gb"] is None
    assert row["gpu_discrete"] is None


def test_connect_backfills_parsed_specs_for_rows_written_before_the_columns(tmp_path):
    db_path = tmp_path / "legacy.db"
    legacy = sqlite3_connect_without_new_columns(db_path)
    legacy.execute(
        "INSERT INTO price_history "
        "(timestamp, product_id, sku, name, url, list_price, sale_price, discount_pct, condition, availability, raw_specs) "
        "VALUES ('2026-07-19T00:00:00+00:00', 'legacy1', 'sku1', 'Old', 'https://x', 100.0, 90.0, 10.0, 'New', 'Available', '')"
    )
    legacy.commit()
    legacy.close()

    # The legacy row predates the `specs` column entirely, so it backfills from
    # the '[]' default and lands on NULLs rather than erroring.
    conn = connect(db_path)
    try:
        assert get_latest_snapshots(conn)[0]["ram_gb"] is None
        assert _meta_get(conn, SPECS_VERSION_KEY) == str(specs_parser.PARSER_VERSION)
    finally:
        conn.close()


def test_connect_replays_the_backfill_when_the_parser_version_is_bumped(tmp_path, monkeypatch):
    db_path = tmp_path / "price_history.db"
    conn = connect(db_path)
    append_snapshots(
        conn,
        [make_snapshot(specs=[{"label": "Memória", "value": "16GB"}])],
    )
    # Corrupt a parsed value by hand to prove the backfill actually reran.
    conn.execute("UPDATE price_history SET ram_gb = 999")
    conn.commit()
    conn.close()

    # Same version: the wrong value survives, so no full-table rewrite happened.
    conn = connect(db_path)
    assert conn.execute("SELECT ram_gb FROM price_history").fetchone()[0] == 999
    conn.close()

    monkeypatch.setattr(specs_parser, "PARSER_VERSION", specs_parser.PARSER_VERSION + 1)
    conn = connect(db_path)
    try:
        # A corrected regex reaches history without a re-scrape.
        assert conn.execute("SELECT ram_gb FROM price_history").fetchone()[0] == 16
    finally:
        conn.close()


def test_scrape_run_round_trips(conn):
    record_scrape_run(
        conn,
        started_at="2026-07-26T10:00:00+00:00",
        finished_at="2026-07-26T10:00:12+00:00",
        status="ok",
        trigger="scheduled",
        products_fetched=117,
        rows_written=117,
    )

    run = get_last_scrape_run(conn)

    assert run["status"] == "ok"
    assert run["trigger"] == "scheduled"
    assert run["products_fetched"] == 117
    assert run["duration_seconds"] == 12.0
    assert run["error"] == ""


def test_get_last_scrape_run_is_none_on_an_empty_database(conn):
    assert get_last_scrape_run(conn) is None


def test_count_consecutive_failures_stops_at_the_most_recent_success(conn):
    for status in ("failed", "ok", "failed", "failed"):
        record_scrape_run(
            conn,
            started_at="2026-07-26T10:00:00+00:00",
            finished_at="2026-07-26T10:00:01+00:00",
            status=status,
            trigger="scheduled",
        )

    # Two failures since the last 'ok'; the earlier one must not be counted.
    assert count_consecutive_failures(conn) == 2


def test_count_consecutive_failures_is_zero_without_any_runs(conn):
    assert count_consecutive_failures(conn) == 0


def test_get_last_success_at_falls_back_to_the_newest_snapshot(conn):
    # The production-upgrade case: years of price history, no scrape_runs rows
    # yet. Without the fallback this reports "never succeeded" and the UI
    # raises a staleness alarm over a perfectly healthy install.
    append_snapshots(conn, [make_snapshot(timestamp=datetime(2026, 7, 25, tzinfo=timezone.utc))])

    assert get_last_success_at(conn) == "2026-07-25T00:00:00+00:00"


def test_get_last_success_at_prefers_a_recorded_run(conn):
    append_snapshots(conn, [make_snapshot(timestamp=datetime(2026, 7, 25, tzinfo=timezone.utc))])
    record_scrape_run(
        conn,
        started_at="2026-07-26T10:00:00+00:00",
        finished_at="2026-07-26T10:00:05+00:00",
        status="ok",
        trigger="manual",
    )

    assert get_last_success_at(conn) == "2026-07-26T10:00:05+00:00"


def test_get_last_success_at_ignores_failed_runs(conn):
    record_scrape_run(
        conn,
        started_at="2026-07-26T10:00:00+00:00",
        finished_at="2026-07-26T10:00:05+00:00",
        status="failed",
        trigger="scheduled",
        error="stale pageFilterId",
    )

    assert get_last_success_at(conn) is None


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


def test_get_latest_snapshots_includes_the_deal_metrics(conn):
    for day, price in ((17, 2252.92), (18, 1999.00), (19, 2100.00), (20, 1800.00)):
        append_snapshots(
            conn,
            [make_snapshot(timestamp=datetime(2026, 7, day, tzinfo=timezone.utc), sale_price=price)],
        )

    row = get_latest_snapshots(conn)[0]

    assert row["snapshot_count"] == 4
    assert row["first_seen"] == "2026-07-17T00:00:00+00:00"
    assert row["days_tracked"] == 3.0
    # Cheapest it has ever been, with four snapshots backing that up.
    assert row["at_all_time_low"] is True
    assert row["pct_below_high"] == pytest.approx(20.1, abs=0.05)
    assert row["deal_score"] == pytest.approx(20.1, abs=0.05)


def test_get_latest_snapshots_withholds_the_low_flag_on_thin_history(conn):
    append_snapshots(conn, [make_snapshot(timestamp=datetime(2026, 7, 18, tzinfo=timezone.utc), sale_price=2000.0)])
    append_snapshots(conn, [make_snapshot(timestamp=datetime(2026, 7, 19, tzinfo=timezone.utc), sale_price=1500.0)])

    row = get_latest_snapshots(conn)[0]

    # Cheapest of the two prices on record, but two points is not history.
    assert row["snapshot_count"] == 2
    assert row["at_all_time_low"] is None
    # It can still rank, just heavily discounted (25% off peak x 1/3 confidence).
    assert row["deal_score"] == pytest.approx(8.3, abs=0.05)


def test_get_latest_snapshots_makes_no_claim_about_a_price_that_never_moved(conn):
    for day in (17, 18, 19, 20):
        append_snapshots(
            conn,
            [make_snapshot(timestamp=datetime(2026, 7, day, tzinfo=timezone.utc), sale_price=2000.0)],
        )

    row = get_latest_snapshots(conn)[0]

    # The shape all real data had as of 2026-07-25: plenty of snapshots, one
    # price throughout. There is no low to be at, and nothing to rank.
    assert row["snapshot_count"] == 4
    assert row["at_all_time_low"] is None
    assert row["deal_score"] == 0.0


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


def test_changes_since_previous_labels_a_first_ever_listing_as_new(conn):
    day1 = datetime(2026, 7, 19, tzinfo=timezone.utc)
    day2 = datetime(2026, 7, 20, tzinfo=timezone.utc)
    append_snapshots(conn, [make_snapshot(product_id="old", timestamp=day1)])
    append_snapshots(
        conn,
        [
            make_snapshot(product_id="old", timestamp=day2),
            make_snapshot(product_id="fresh", timestamp=day2),
        ],
    )

    changes = {c["product_id"]: c for c in changes_since_previous(conn)}

    assert changes["fresh"]["event"] == "new"


def test_changes_since_previous_labels_a_returning_product_as_relisted(conn):
    # Sold out on day 2, back on the shelf on day 3 — not a new listing.
    for day, products in (
        (19, ["anchor", "comes_back"]),
        (20, ["anchor"]),
        (21, ["anchor", "comes_back"]),
    ):
        append_snapshots(
            conn,
            [
                make_snapshot(product_id=p, timestamp=datetime(2026, 7, day, tzinfo=timezone.utc))
                for p in products
            ],
        )

    changes = {c["product_id"]: c for c in changes_since_previous(conn)}

    assert changes["comes_back"]["event"] == "relisted"
    assert changes["comes_back"]["old_price"] is None


def test_changes_since_previous_labels_a_price_move_as_price(conn):
    day1 = datetime(2026, 7, 19, tzinfo=timezone.utc)
    day2 = datetime(2026, 7, 20, tzinfo=timezone.utc)
    append_snapshots(conn, [make_snapshot(timestamp=day1, sale_price=2252.92)])
    append_snapshots(conn, [make_snapshot(timestamp=day2, sale_price=2100.00)])

    assert changes_since_previous(conn)[0]["event"] == "price"


def test_changes_since_previous_withholds_the_low_flag_on_thin_history(conn):
    day1 = datetime(2026, 7, 19, tzinfo=timezone.utc)
    day2 = datetime(2026, 7, 20, tzinfo=timezone.utc)
    append_snapshots(conn, [make_snapshot(timestamp=day1, sale_price=2252.92)])
    append_snapshots(conn, [make_snapshot(timestamp=day2, sale_price=2100.00)])

    # Cheapest of two prices, but two is below MIN_SNAPSHOTS_FOR_HISTORY.
    assert changes_since_previous(conn)[0]["all_time_low"] is None


def test_changes_since_previous_flags_a_record_low(conn):
    for day, price in ((17, 2252.92), (18, 2200.00), (19, 2100.00), (20, 1899.00)):
        append_snapshots(
            conn,
            [make_snapshot(timestamp=datetime(2026, 7, day, tzinfo=timezone.utc), sale_price=price)],
        )

    assert changes_since_previous(conn)[0]["all_time_low"] is True


def test_changes_since_previous_never_flags_a_rising_price_as_a_low(conn):
    for day, price in ((17, 1899.00), (18, 2000.00), (19, 2100.00), (20, 2252.92)):
        append_snapshots(
            conn,
            [make_snapshot(timestamp=datetime(2026, 7, day, tzinfo=timezone.utc), sale_price=price)],
        )

    change = changes_since_previous(conn)[0]
    assert change["event"] == "price"
    assert change["all_time_low"] is False


def test_changes_since_previous_flags_a_relisted_product_at_a_record_low(conn):
    # A sold-out configuration returning cheaper than it has ever been is the
    # single most useful alert this produces, so the flag is not limited to
    # "price" events.
    for day, products, price in (
        (17, ["anchor", "comes_back"], 2252.92),
        (18, ["anchor", "comes_back"], 2200.00),
        (19, ["anchor"], 2200.00),
        (20, ["anchor", "comes_back"], 1750.00),
    ):
        append_snapshots(
            conn,
            [
                make_snapshot(
                    product_id=p,
                    timestamp=datetime(2026, 7, day, tzinfo=timezone.utc),
                    sale_price=price,
                )
                for p in products
            ],
        )

    changes = {c["product_id"]: c for c in changes_since_previous(conn)}

    assert changes["comes_back"]["event"] == "relisted"
    assert changes["comes_back"]["all_time_low"] is True


def test_append_snapshots_ignores_a_product_repeated_within_one_scrape(conn):
    day1 = datetime(2026, 7, 19, tzinfo=timezone.utc)

    written = append_snapshots(
        conn,
        [make_snapshot(product_id="dup", timestamp=day1), make_snapshot(product_id="dup", timestamp=day1)],
    )

    assert written == 1
    assert len(get_latest_snapshots(conn)) == 1


def test_append_snapshots_still_records_the_same_product_at_a_later_scrape(conn):
    append_snapshots(conn, [make_snapshot(timestamp=datetime(2026, 7, 19, tzinfo=timezone.utc))])
    written = append_snapshots(conn, [make_snapshot(timestamp=datetime(2026, 7, 20, tzinfo=timezone.utc))])

    assert written == 1
    assert conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0] == 2


def test_connect_clears_pre_existing_duplicates_before_indexing(tmp_path):
    db_path = tmp_path / "dupes.db"
    seed = sqlite3.connect(db_path)
    seed.executescript(CREATE_TABLE_SQL)
    # Two identical rows for one product in one scrape — what the outlet API
    # handed back before fetch_all_products() de-duplicated its pages.
    for _ in range(2):
        seed.execute(
            "INSERT INTO price_history "
            "(timestamp, product_id, sku, name, url, list_price, sale_price, discount_pct, condition, availability, raw_specs) "
            "VALUES ('2026-07-25T11:31:25+00:00', 'dup', '82UM0002BR', 'Lenovo V15', 'https://x', 2879.99, 2591.99, 10.0, 'Produto novo', 'Available', '')"
        )
    seed.commit()
    seed.close()

    conn = connect(db_path)

    assert conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0] == 1
    assert len(get_latest_snapshots(conn)) == 1
    conn.close()


def test_connect_leaves_distinct_rows_alone_when_indexing(tmp_path):
    db_path = tmp_path / "clean.db"
    conn = connect(db_path)
    append_snapshots(
        conn,
        [
            make_snapshot(product_id="a", timestamp=datetime(2026, 7, 19, tzinfo=timezone.utc)),
            make_snapshot(product_id="b", timestamp=datetime(2026, 7, 19, tzinfo=timezone.utc)),
        ],
    )
    conn.close()

    reopened = connect(db_path)

    assert reopened.execute("SELECT COUNT(*) FROM price_history").fetchone()[0] == 2
    reopened.close()


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
            # Nothing to parse, so every derived spec is NULL rather than 0 —
            # a "16 GB or more" filter must exclude this row, not treat it as
            # a machine with no memory.
            "ram_gb": None,
            "storage_gb": None,
            "screen_in": None,
            "cpu_brand": None,
            "cpu_model": None,
            "gpu_discrete": None,
            "lowest_price": 90.0,
            "highest_price": 90.0,
            "snapshot_count": 1,
            "first_seen": "2026-07-19T00:00:00+00:00",
            "currently_listed": True,
            # A single snapshot is no price range at all: nothing can be
            # claimed about it, so the low is unknown and it cannot rank.
            "at_all_time_low": None,
            "pct_below_high": 0.0,
            "deal_score": 0.0,
            "days_tracked": 0.0,
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
