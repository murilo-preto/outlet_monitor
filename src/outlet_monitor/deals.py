"""How good a price actually is, judged only against that product's own history.

Kept free of sqlite/storage imports so the formulas can be unit-tested without
a database, and tuned without a migration — nothing here is persisted.

The confidence weighting is the load-bearing idea. As of 2026-07-25, 87 of the
123 tracked products had two snapshots or fewer: the catalogue jumped from ~22
to ~117 tracked products in a single week. With two data points a product's
current price is its all-time low half the time, so an unweighted "menor preço
histórico" flag would fire on most of the catalogue and mean nothing. Rather
than hiding thin-history products entirely (which would leave the deals list
empty today), their scores are scaled down until enough history exists to back
the claim up.
"""

from datetime import datetime

# Prices are stored as REAL; compare with a cent of tolerance rather than ==.
# Matches storage.PRICE_EPSILON, duplicated here to keep this module dependency-free.
PRICE_EPSILON = 0.01

# Below this, "is this the cheapest it has ever been?" has no defensible answer
# and is reported as None (unknown) rather than True or False.
MIN_SNAPSHOTS_FOR_HISTORY = 3

# At or above this many snapshots a product's own price range is taken at face
# value. Between the two thresholds the score is scaled linearly.
SNAPSHOTS_FOR_FULL_CONFIDENCE = 4


def is_all_time_low(
    sale_price: float, lowest_price: float, highest_price: float, snapshot_count: int
) -> bool | None:
    """Whether this is the cheapest the product has ever been recorded at.

    Two things must hold before the claim means anything, and both are None
    (unknown) rather than False when they don't — saying "not a low" when the
    truth is "we cannot tell" is a stronger statement than the data supports:

    - Enough snapshots to have seen the product more than in passing.
    - An actual price *range*. This one matters more than it looks: as of the
      2026-07-25 export not a single one of the 123 tracked products had ever
      changed price in 18 scrapes, so a bare `sale_price <= lowest_price` test
      returned True for every product that had simply sat at one price. A
      product at its only observed price is not at a low; it has no low yet.
    """
    if snapshot_count < MIN_SNAPSHOTS_FOR_HISTORY:
        return None
    if highest_price - lowest_price <= PRICE_EPSILON:
        return None
    return sale_price <= lowest_price + PRICE_EPSILON


def pct_below_high(sale_price: float, highest_price: float) -> float:
    """How far the current price sits below this product's own peak, 0-100."""
    if highest_price <= 0 or sale_price >= highest_price:
        return 0.0
    return (highest_price - sale_price) / highest_price * 100


def history_confidence(snapshot_count: int) -> float:
    """How much this product's observed price range can be trusted, 0.0-1.0.

    One snapshot is no range at all, so it scores 0 and can never rank.
    """
    if snapshot_count < 2:
        return 0.0
    return min(1.0, (snapshot_count - 1) / (SNAPSHOTS_FOR_FULL_CONFIDENCE - 1))


def deal_score(sale_price: float, highest_price: float, snapshot_count: int) -> float:
    """Rank a current price against the product's own history.

    Deliberately ignores `discount_pct`: that is Lenovo's list-vs-sale marketing
    claim, present on nearly every item and identical whether or not the price
    actually moved. Only observed history can distinguish a real drop.
    """
    return round(pct_below_high(sale_price, highest_price) * history_confidence(snapshot_count), 1)


def days_tracked(first_seen: str, last_seen: str) -> float:
    """Days between a product's first and most recent snapshot, to one decimal."""
    try:
        delta = datetime.fromisoformat(last_seen) - datetime.fromisoformat(first_seen)
    except (TypeError, ValueError):
        return 0.0
    return round(delta.total_seconds() / 86400, 1)


def enrich(snapshot: dict) -> dict:
    """Add the derived deal fields to a snapshot dict, in place.

    Expects the keys get_latest_snapshots() produces: sale_price, lowest_price,
    highest_price, snapshot_count, first_seen, timestamp.
    """
    sale_price = snapshot["sale_price"]
    snapshot_count = snapshot["snapshot_count"]

    snapshot["at_all_time_low"] = is_all_time_low(
        sale_price, snapshot["lowest_price"], snapshot["highest_price"], snapshot_count
    )
    snapshot["pct_below_high"] = round(pct_below_high(sale_price, snapshot["highest_price"]), 1)
    snapshot["deal_score"] = deal_score(sale_price, snapshot["highest_price"], snapshot_count)
    snapshot["days_tracked"] = days_tracked(snapshot["first_seen"], snapshot["timestamp"])
    return snapshot
