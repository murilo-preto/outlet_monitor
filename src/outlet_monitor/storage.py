import json
import sqlite3
from pathlib import Path

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

# Indexes are created after migrations run, since idx_price_history_category
# references a column that may not exist yet on a pre-existing db file.
CREATE_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_price_history_product_id ON price_history(product_id);
CREATE INDEX IF NOT EXISTS idx_price_history_timestamp ON price_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_price_history_category ON price_history(category);
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
INSERT INTO price_history
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

LATEST_SNAPSHOT_SQL = f"""
SELECT {_SELECT_COLUMNS_PH}, bounds.lowest_price, bounds.highest_price,
    ph.timestamp = (SELECT MAX(timestamp) FROM price_history) AS currently_listed
FROM price_history ph
INNER JOIN (
    SELECT product_id, MAX(timestamp) AS max_ts
    FROM price_history
    GROUP BY product_id
) latest ON ph.product_id = latest.product_id AND ph.timestamp = latest.max_ts
INNER JOIN (
    SELECT product_id, MIN(sale_price) AS lowest_price, MAX(sale_price) AS highest_price
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


def connect(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(CREATE_TABLE_SQL)
    _apply_migrations(conn)
    conn.executescript(CREATE_INDEXES_SQL)
    return conn


def append_snapshots(conn: sqlite3.Connection, snapshots: list[ProductSnapshot]) -> int:
    """Append snapshots as new rows (never updates/overwrites existing rows).

    Rows with no usable price are skipped rather than written as garbage.
    Returns the number of rows actually written.
    """
    valid = [s for s in snapshots if s.list_price > 0 and s.sale_price > 0]

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
    return len(valid)


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
        snapshot = _row_to_dict(row[:-3])
        snapshot["lowest_price"], snapshot["highest_price"] = row[-3], row[-2]
        snapshot["currently_listed"] = bool(row[-1])
        result.append(snapshot)
    return result


def get_product_history(conn: sqlite3.Connection, product_id: str) -> list[dict]:
    """Return every snapshot ever recorded for a product_id, oldest first."""
    rows = conn.execute(HISTORY_SQL, (product_id,)).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_category_counts(conn: sqlite3.Connection) -> list[dict]:
    """Return each category present with how many currently-tracked products it has."""
    rows = conn.execute(CATEGORY_COUNTS_SQL).fetchall()
    return [{"category": category, "product_count": count} for category, count in rows]
