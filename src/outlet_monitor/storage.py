import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from outlet_monitor import deals
from outlet_monitor.models import ProductSnapshot

DEFAULT_DB_PATH = Path("data/price_history.db")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS price_history (
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
    raw_specs TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Other',
    image_url TEXT NOT NULL DEFAULT '',
    specs TEXT NOT NULL DEFAULT '[]'
);
"""

# Indexes are created after migrations run, since they reference columns that
# may not exist yet on a pre-existing db file.
#
# The composite index is what makes the two GROUP BY subqueries in
# LATEST_SNAPSHOT_SQL *covering*: with only a single-column index on
# product_id, sqlite walks it in product order but still has to fetch every
# row from the main table to read `timestamp` and `sale_price`. Carrying all
# three columns in the index removes those lookups entirely — measured at 15x
# on /products and /categories at 45k rows (~4 months of scraping at the
# current 3-per-day rate), and the gap widens from there.
#
# The three single-column indexes it replaces are all redundant now:
#   - product_id is a prefix of this index;
#   - timestamp is a prefix of the UNIQUE (timestamp, product_id) index below;
#   - category was never chosen by any query plan, because get_latest_snapshots
#     appends its WHERE *after* the joins, filtering the ~123-row result rather
#     than the scan.
# Dropped after the replacement exists, so there is never a window without one.
CREATE_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_price_history_pid_ts_price
    ON price_history(product_id, timestamp, sale_price);
DROP INDEX IF EXISTS idx_price_history_product_id;
DROP INDEX IF EXISTS idx_price_history_timestamp;
DROP INDEX IF EXISTS idx_price_history_category;
"""

# One row per product per scrape. The scraper already de-duplicates what the
# outlet API hands back, so this is the backstop: any future source of repeats
# is dropped by INSERT OR IGNORE instead of silently double-counting a product.
UNIQUE_SNAPSHOT_INDEX = "idx_price_history_ts_product"
CREATE_UNIQUE_SNAPSHOT_INDEX_SQL = f"""
CREATE UNIQUE INDEX {UNIQUE_SNAPSHOT_INDEX} ON price_history(timestamp, product_id)
"""

# Ran once, immediately before the unique index is first built: the index
# cannot be created while duplicates from before it existed are still on disk.
# Keeps the earliest row of each (timestamp, product_id) — they are identical
# copies of one listing, so which one survives doesn't matter.
DELETE_DUPLICATE_SNAPSHOTS_SQL = """
DELETE FROM price_history
WHERE id NOT IN (SELECT MIN(id) FROM price_history GROUP BY timestamp, product_id)
"""

# Columns added after the initial release: (name, ALTER-COLUMN-DEF). Applied to
# any pre-existing db file that predates them, so older data/price_history.db
# volumes don't break on the new INSERT/SELECT column lists.
_MIGRATIONS = (
    ("category", "TEXT NOT NULL DEFAULT 'Other'"),
    ("image_url", "TEXT NOT NULL DEFAULT ''"),
    ("specs", "TEXT NOT NULL DEFAULT '[]'"),
)

INSERT_SQL = """
INSERT OR IGNORE INTO price_history
    (timestamp, product_id, sku, name, url, list_price, sale_price, discount_pct, condition, availability, raw_specs, category, image_url, specs)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

COLUMNS = (
    "id",
    "timestamp",
    "product_id",
    "sku",
    "name",
    "url",
    "list_price",
    "sale_price",
    "discount_pct",
    "condition",
    "availability",
    "raw_specs",
    "category",
    "image_url",
    "specs",
)
_SELECT_COLUMNS = ", ".join(COLUMNS)
_SELECT_COLUMNS_PH = ", ".join(f"ph.{col}" for col in COLUMNS)

# Computed per read by LATEST_SNAPSHOT_SQL, never stored. Order must match the
# trailing SELECT expressions there.
_EXTRA_COLUMNS = (
    "lowest_price",
    "highest_price",
    "snapshot_count",
    "first_seen",
    "currently_listed",
)

# snapshot_count and first_seen ride along on the aggregation that already
# computes the price bounds — all four columns come from the same covering
# index scan, so the extra deal metrics cost nothing beyond the two values.
LATEST_SNAPSHOT_SQL = f"""
SELECT {_SELECT_COLUMNS_PH}, bounds.lowest_price, bounds.highest_price,
    bounds.snapshot_count, bounds.first_seen,
    ph.timestamp = (SELECT MAX(timestamp) FROM price_history) AS currently_listed
FROM price_history ph
INNER JOIN (
    SELECT product_id, MAX(timestamp) AS max_ts
    FROM price_history
    GROUP BY product_id
) latest ON ph.product_id = latest.product_id AND ph.timestamp = latest.max_ts
INNER JOIN (
    SELECT product_id, MIN(sale_price) AS lowest_price, MAX(sale_price) AS highest_price,
        COUNT(*) AS snapshot_count, MIN(timestamp) AS first_seen
    FROM price_history
    GROUP BY product_id
) bounds ON ph.product_id = bounds.product_id
"""

HISTORY_SQL = f"""
SELECT {_SELECT_COLUMNS}
FROM price_history
WHERE product_id = ?
ORDER BY timestamp
"""

EXPORT_SQL = f"""
SELECT {_SELECT_COLUMNS}
FROM price_history
ORDER BY timestamp, product_id
"""

LAST_TWO_TIMESTAMPS_SQL = """
SELECT DISTINCT timestamp FROM price_history ORDER BY timestamp DESC LIMIT 2
"""

SNAPSHOT_AT_SQL = """
SELECT product_id, name, url, sale_price, category
FROM price_history
WHERE timestamp = ?
"""

SEEN_BEFORE_SQL = """
SELECT DISTINCT product_id FROM price_history WHERE timestamp < ?
"""

# Bounded at the run being reported on, so a scrape committing concurrently
# can't make a change look like a record it isn't. The current run's own rows
# are already committed when changes_since_previous() runs, so they count.
ALL_TIME_LOW_SQL = """
SELECT product_id, MIN(sale_price), MAX(sale_price), COUNT(*)
FROM price_history
WHERE timestamp <= ?
GROUP BY product_id
"""

CATEGORY_COUNTS_SQL = """
SELECT category, COUNT(*) AS product_count
FROM (
    SELECT ph.product_id, ph.category
    FROM price_history ph
    INNER JOIN (
        SELECT product_id, MAX(timestamp) AS max_ts
        FROM price_history
        GROUP BY product_id
    ) latest ON ph.product_id = latest.product_id AND ph.timestamp = latest.max_ts
)
GROUP BY category
ORDER BY product_count DESC, category ASC
"""


def _apply_migrations(conn: sqlite3.Connection) -> None:
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(price_history)")}
    for column, definition in _MIGRATIONS:
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE price_history ADD COLUMN {column} {definition}")
    conn.commit()


def _ensure_unique_snapshot_index(conn: sqlite3.Connection) -> None:
    """Build the (timestamp, product_id) unique index, once, per database file.

    Guarded on the index not already existing rather than using IF NOT EXISTS,
    so the duplicate sweep is a one-time migration cost and not a full scan on
    every connection — connect() runs per request.
    """
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (UNIQUE_SNAPSHOT_INDEX,),
    ).fetchone()
    if exists:
        return

    conn.execute(DELETE_DUPLICATE_SNAPSHOTS_SQL)
    conn.execute(CREATE_UNIQUE_SNAPSHOT_INDEX_SQL)
    conn.commit()


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    """Put the connection in WAL mode with a write timeout.

    Without WAL, a reader blocks writers outright: /export.csv holds a read
    transaction open for the *entire* HTTP response (rows are pulled lazily as
    the client consumes the stream), so a slow client downloading the export
    would make the scheduled scrape's INSERT fail with "database is locked" —
    measured at 5s to fail under the rollback journal, 0.3ms to succeed under
    WAL. WAL lets that reader and the writer coexist.

    journal_mode is a persistent property of the file (this is a no-op after
    the first connection ever made to it); synchronous and busy_timeout are
    per-connection and have to be set every time. synchronous=NORMAL is safe
    under WAL — a crash can lose the last commit but cannot corrupt the file.
    """
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=10000")


def connect(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    _apply_pragmas(conn)
    conn.executescript(CREATE_TABLE_SQL)
    _apply_migrations(conn)
    conn.executescript(CREATE_INDEXES_SQL)
    _ensure_unique_snapshot_index(conn)
    return conn


def append_snapshots(conn: sqlite3.Connection, snapshots: list[ProductSnapshot]) -> int:
    """Append snapshots as new rows (never updates/overwrites existing rows).

    Rows with no usable price are skipped rather than written as garbage, and
    a product already recorded at this timestamp is ignored rather than stored
    twice. Returns the number of rows actually written, which is why it counts
    what sqlite committed instead of the size of the input.
    """
    valid = [s for s in snapshots if s.list_price > 0 and s.sale_price > 0]
    before = conn.total_changes

    conn.executemany(
        INSERT_SQL,
        [
            (
                s.timestamp.isoformat(),
                s.product_id,
                s.sku,
                s.name,
                s.url,
                s.list_price,
                s.sale_price,
                s.discount_pct,
                s.condition,
                s.availability,
                s.raw_specs,
                s.category,
                s.image_url,
                json.dumps(s.specs, ensure_ascii=False),
            )
            for s in valid
        ],
    )
    conn.commit()
    return conn.total_changes - before


def _row_to_dict(row: tuple) -> dict:
    result = dict(zip(COLUMNS, row))
    result["specs"] = json.loads(result["specs"])
    return result


def get_latest_snapshots(conn: sqlite3.Connection, category: str | None = None) -> list[dict]:
    """Return the most recent snapshot for every product_id, optionally filtered by category.

    Each snapshot also carries:
    - `lowest_price`/`highest_price`: the min/max sale_price ever recorded for
      that product, computed fresh from price_history rather than stored, so
      they're always current.
    - `currently_listed`: whether this product's snapshot came from the most
      recent scrape run (all products in one scrape share the same
      timestamp). False means the product is still tracked (its price history
      is kept) but the outlet no longer listed it as of the last scrape.
    """
    sql = LATEST_SNAPSHOT_SQL
    params: tuple = ()
    if category is not None:
        sql += " WHERE ph.category = ?"
        params = (category,)
    sql += " ORDER BY ph.product_id"
    rows = conn.execute(sql, params).fetchall()
    result = []
    for row in rows:
        # Split on len(COLUMNS) rather than counting back from the end: the
        # trailing columns are positional, and indexing them negatively breaks
        # silently every time COLUMNS grows.
        snapshot = _row_to_dict(row[: len(COLUMNS)])
        snapshot.update(zip(_EXTRA_COLUMNS, row[len(COLUMNS) :]))
        snapshot["currently_listed"] = bool(snapshot["currently_listed"])
        result.append(deals.enrich(snapshot))
    return result


def iter_all_snapshots(conn: sqlite3.Connection) -> Iterator[tuple]:
    """Yield every snapshot ever recorded as a raw column tuple, oldest first.

    Column order matches COLUMNS. Unlike the other readers this stays a
    cursor-backed iterator and does no per-row decoding, so a full export
    never materialises the whole table in memory.
    """
    yield from conn.execute(EXPORT_SQL)


def get_product_history(conn: sqlite3.Connection, product_id: str) -> list[dict]:
    """Return every snapshot ever recorded for a product_id, oldest first."""
    rows = conn.execute(HISTORY_SQL, (product_id,)).fetchall()
    return [_row_to_dict(row) for row in rows]


# Prices are stored as REAL, so compare with a cent of tolerance rather than ==.
PRICE_EPSILON = 0.01


def _all_time_lows(
    conn: sqlite3.Connection, current_ts: str
) -> dict[str, tuple[float, float, int]]:
    """product_id -> (lowest, highest, snapshot count) sale_price, up to current_ts."""
    return {
        product_id: (lowest, highest, count)
        for product_id, lowest, highest, count in conn.execute(ALL_TIME_LOW_SQL, (current_ts,))
    }


def changes_since_previous(conn: sqlite3.Connection) -> list[dict]:
    """What changed between the two most recent scrape runs.

    Returns one dict per product whose `sale_price` moved, plus products that
    appear in the newest run and not in the one before it (`old_price` is None
    for those). Delisted products are not reported — a product going away is
    not a price fluctuation.

    Each change carries an `event`:
    - "price": the product was listed before and its `sale_price` moved.
    - "new": first time this product_id has ever been seen.
    - "relisted": it was absent from the previous run but had been listed at
      some earlier point. Outlet stock churns — units sell out and the same
      configuration reappears days later — so this is worth telling apart from
      a genuinely new listing.

    Each change also carries `all_time_low`: whether this price is the cheapest
    ever recorded for the product, or None when there is too little history to
    say (see deals.is_all_time_low). It is set for every event, not just price
    moves — a sold-out configuration returning at its cheapest-ever price is
    exactly the alert worth receiving.

    Returns an empty list when there is only one scrape on record: on a fresh
    database every product would otherwise look "new" and produce a report
    hundreds of items long.
    """
    timestamps = [row[0] for row in conn.execute(LAST_TWO_TIMESTAMPS_SQL)]
    if len(timestamps) < 2:
        return []

    current_ts, previous_ts = timestamps[0], timestamps[1]
    previous = {
        row[0]: row for row in conn.execute(SNAPSHOT_AT_SQL, (previous_ts,))
    }
    seen_before = {row[0] for row in conn.execute(SEEN_BEFORE_SQL, (previous_ts,))}
    lows = _all_time_lows(conn, current_ts)

    changes = []
    for product_id, name, url, sale_price, category in conn.execute(
        SNAPSHOT_AT_SQL, (current_ts,)
    ):
        before = previous.get(product_id)
        if before is None:
            old_price = None
            event = "relisted" if product_id in seen_before else "new"
        elif abs(before[3] - sale_price) >= PRICE_EPSILON:
            old_price = before[3]
            event = "price"
        else:
            continue

        lowest, highest, snapshot_count = lows.get(product_id, (sale_price, sale_price, 1))
        changes.append(
            {
                "product_id": product_id,
                "name": name,
                "url": url,
                "category": category,
                "old_price": old_price,
                "new_price": sale_price,
                "event": event,
                "all_time_low": deals.is_all_time_low(
                    sale_price, lowest, highest, snapshot_count
                ),
            }
        )
    return changes


def get_category_counts(conn: sqlite3.Connection) -> list[dict]:
    """Return each category present with how many currently-tracked products it has."""
    rows = conn.execute(CATEGORY_COUNTS_SQL).fetchall()
    return [{"category": category, "product_count": count} for category, count in rows]
