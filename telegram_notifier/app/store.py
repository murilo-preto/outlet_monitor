"""SQLite storage for Telegram subscribers and their product-line filters.

Deliberately independent from the price monitor's database: this service owns
its own file and never reads the monitor's schema.
"""

from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB_PATH = Path(os.environ.get("SUBSCRIBERS_DB_PATH", "/data/subscribers.db"))

# Lenovo product lines offered in the menu out of the box. New lines discovered
# in /notify payloads are appended to the `known_lines` table automatically.
SEED_LINES = [
    line.strip()
    for line in os.environ.get(
        "PRODUCT_LINES",
        "ThinkPad,ThinkBook,IdeaPad,Yoga,Legion,LOQ,ThinkCentre,ThinkStation",
    ).split(",")
    if line.strip()
]


@contextmanager
def _connect(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id    INTEGER PRIMARY KEY,
                label      TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS filters (
                chat_id INTEGER NOT NULL
                    REFERENCES subscribers(chat_id) ON DELETE CASCADE,
                line    TEXT NOT NULL,
                PRIMARY KEY (chat_id, line)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS known_lines (
                line       TEXT PRIMARY KEY,
                seeded     INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.executemany(
            "INSERT OR IGNORE INTO known_lines (line, seeded) VALUES (?, 1)",
            [(line,) for line in SEED_LINES],
        )


# --- subscribers ------------------------------------------------------------


def subscribe(chat_id: int, label: str | None = None, db_path: Path = DEFAULT_DB_PATH) -> bool:
    """Register a chat. Returns True if it was newly added, False if already there."""
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO subscribers (chat_id, label) VALUES (?, ?)",
            (chat_id, label),
        )
        return cur.rowcount > 0


def unsubscribe(chat_id: int, db_path: Path = DEFAULT_DB_PATH) -> bool:
    """Remove a chat and its filters. Returns True if it was subscribed."""
    with _connect(db_path) as conn:
        cur = conn.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))
        return cur.rowcount > 0


def is_subscribed(chat_id: int, db_path: Path = DEFAULT_DB_PATH) -> bool:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT 1 FROM subscribers WHERE chat_id = ?", (chat_id,)).fetchone()
    return row is not None


def list_subscribers(db_path: Path = DEFAULT_DB_PATH) -> list[int]:
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT chat_id FROM subscribers ORDER BY created_at").fetchall()
    return [row[0] for row in rows]


def count_subscribers(db_path: Path = DEFAULT_DB_PATH) -> int:
    with _connect(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM subscribers").fetchone()[0]


def subscribers_with_filters(db_path: Path = DEFAULT_DB_PATH) -> list[tuple[int, list[str]]]:
    """Every subscriber paired with its filters. An empty list means "send everything"."""
    with _connect(db_path) as conn:
        chat_ids = [
            row[0]
            for row in conn.execute("SELECT chat_id FROM subscribers ORDER BY created_at")
        ]
        rows = conn.execute("SELECT chat_id, line FROM filters").fetchall()

    by_chat: dict[int, list[str]] = {chat_id: [] for chat_id in chat_ids}
    for chat_id, line in rows:
        by_chat.setdefault(chat_id, []).append(line)
    return [(chat_id, sorted(by_chat[chat_id])) for chat_id in chat_ids]


# --- filters ----------------------------------------------------------------


def get_filters(chat_id: int, db_path: Path = DEFAULT_DB_PATH) -> list[str]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT line FROM filters WHERE chat_id = ? ORDER BY line", (chat_id,)
        ).fetchall()
    return [row[0] for row in rows]


def toggle_filter(chat_id: int, line: str, db_path: Path = DEFAULT_DB_PATH) -> bool:
    """Add the line if absent, remove it if present. Returns True if now active."""
    with _connect(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM filters WHERE chat_id = ? AND line = ?", (chat_id, line)
        )
        if cur.rowcount:
            return False
        conn.execute("INSERT INTO filters (chat_id, line) VALUES (?, ?)", (chat_id, line))
        return True


def clear_filters(chat_id: int, db_path: Path = DEFAULT_DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM filters WHERE chat_id = ?", (chat_id,))


# --- known product lines ----------------------------------------------------


def known_lines(db_path: Path = DEFAULT_DB_PATH) -> list[str]:
    """Seeded lines first (in configured order), then auto-discovered ones."""
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT line, seeded FROM known_lines").fetchall()

    seeded = {line for line, is_seed in rows if is_seed}
    discovered = sorted(line for line, is_seed in rows if not is_seed)
    return [line for line in SEED_LINES if line in seeded] + discovered


_LINE_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9]{2,19}$")

# Words that lead a product name without naming its line. Guessing "Lenovo"
# from "Lenovo V14 Intel Core i3..." yields a menu entry matching half the
# catalogue — the real line there is "V Series", which the name never states.
_NOT_A_LINE = {"lenovo", "notebook", "laptop", "computador", "pc", "the", "new"}


def remember_lines(changes: Iterable, db_path: Path = DEFAULT_DB_PATH) -> list[str]:
    """Learn product lines from a payload, so the menu stays current.

    Prefers the `category` the caller supplies — it is already classified and
    authoritative. Only when it is absent does this fall back to the leading
    token of the product name, which works for names like "Yoga Slim 7i" but
    cannot recover a line the name never mentions.
    """
    lowered = {line.lower() for line in known_lines(db_path)}
    added: list[str] = []

    def remember(line: str) -> None:
        if line.lower() in lowered:
            return
        added.append(line)
        lowered.add(line.lower())

    for change in changes:
        category = (getattr(change, "category", None) or "").strip()
        if category:
            remember(category)
            continue

        name = (getattr(change, "name", "") or "").strip()
        token = name.split(" ")[0] if name else ""
        if not _LINE_TOKEN.match(token) or token.lower() in _NOT_A_LINE:
            continue
        if any(line in name.lower() for line in lowered):
            continue
        remember(token)

    if added:
        with _connect(db_path) as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO known_lines (line, seeded) VALUES (?, 0)",
                [(line,) for line in added],
            )
    return added
