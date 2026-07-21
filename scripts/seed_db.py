#!/usr/bin/env python3
"""Manual dev tool: populates the database with synthetic price history.

Not part of the automated test suite (nothing in tests/ imports this) — it
exists so you can exercise the frontend (price charts, all-time low/high,
delisted-product styling) with realistic-looking data without hitting
Lenovo's live outlet API. Run it directly:

    docker compose run --rm api python scripts/seed_db.py --reset
"""

import argparse
import random
from datetime import datetime, timedelta, timezone

from outlet_monitor.models import ProductSnapshot
from outlet_monitor.storage import DEFAULT_DB_PATH, append_snapshots, connect

random.seed(42)

IMAGE_URL = "https://p3-ofp.static.pub/fes/cms/2021/10/25/hero.png"

# (sku, name, category, condition, base list price)
PRODUCTS = [
    ("82X5X00900", 'IdeaPad 1i 15" Intel Core i3', "IdeaPad", "Novo", 2999.00),
    ("21HK000ABR", "ThinkPad E14 Gen 5 Intel Core i5", "ThinkPad", "Remanufaturado Certificado", 6499.00),
    ("82YM0000BR", 'Yoga 7i 14" Intel Core i7', "Yoga", "Novo", 8999.00),
    ("82XW0000BR", "Legion 5 Intel Core i7 RTX 4060", "Legion", "Novo", 10999.00),
    ("82XV0000BR", "LOQ 15IRX9 Intel Core i5 RTX 3050", "LOQ", "Remanufaturado Certificado", 7499.00),
    ("21JG0000BR", "ThinkBook 15 Gen 4 Intel Core i5", "ThinkBook", "Novo", 5999.00),
    ("82R20000BR", "V15 G4 AMN Ryzen 5", "V Series", "Novo", 3499.00),
]


def make_history(
    now: datetime, sku: str, name: str, category: str, condition: str, base_price: float, days: int, delisted: bool
) -> list[ProductSnapshot]:
    """Build `days` days of snapshots, oldest first, ending at `now`.

    Price random-walks around a discounted baseline with one deep-discount day
    (all-time low) and one near-list-price day (all-time high) planted partway
    through, so the frontend's lowest/current/highest comparison has something
    to show. If `delisted`, the final (most-recent) day is dropped so this
    product's latest row lands before the run's overall latest timestamp —
    exercising the "no longer in the outlet" styling.
    """
    product_id = f"{sku}_{category.lower().replace(' ', '')}"
    price = base_price * 0.8

    snapshots = []
    for day in range(days):
        timestamp = now - timedelta(days=days - day - 1)
        price = max(base_price * 0.55, min(base_price * 0.98, price * (1 + random.uniform(-0.03, 0.03))))

        if day == days // 3:
            price = base_price * 0.5
        elif day == (days * 2) // 3:
            price = base_price * 0.97

        discount_pct = round((1 - price / base_price) * 100, 1)
        snapshots.append(
            ProductSnapshot(
                timestamp=timestamp,
                product_id=product_id,
                sku=sku,
                name=name,
                url=f"https://www.lenovo.com/br/outlet/pt/p/laptops/{sku.lower()}",
                list_price=base_price,
                sale_price=round(price, 2),
                discount_pct=discount_pct,
                condition=condition,
                availability="Available",
                raw_specs="Processador: Intel Core i5-1335U",
                category=category,
                image_url=IMAGE_URL,
                specs=[{"label": "Processador", "value": "Intel Core i5-1335U"}],
            )
        )

    if delisted:
        snapshots.pop()

    return snapshots


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--db-path", default=DEFAULT_DB_PATH, help=f"SQLite file to write to (default: {DEFAULT_DB_PATH})"
    )
    parser.add_argument("--days", type=int, default=21, help="days of history per product (default: 21)")
    parser.add_argument("--reset", action="store_true", help="wipe existing price_history rows before seeding")
    args = parser.parse_args()

    conn = connect(args.db_path)
    try:
        if args.reset:
            conn.execute("DELETE FROM price_history")
            conn.commit()

        now = datetime.now(timezone.utc)
        total_written = 0
        for index, (sku, name, category, condition, base_price) in enumerate(PRODUCTS):
            # Last product simulates one that fell out of the outlet since the last scrape.
            delisted = index == len(PRODUCTS) - 1
            snapshots = make_history(now, sku, name, category, condition, base_price, args.days, delisted)
            total_written += append_snapshots(conn, snapshots)

        print(f"Seeded {total_written} snapshots across {len(PRODUCTS)} products into {args.db_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
