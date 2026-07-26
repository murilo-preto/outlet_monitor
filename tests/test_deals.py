import pytest

from outlet_monitor import deals


@pytest.mark.parametrize(
    "snapshot_count,expected",
    [
        (1, None),
        (2, None),  # a single observed move proves nothing
        (3, True),  # MIN_SNAPSHOTS_FOR_HISTORY
        (18, True),
    ],
)
def test_all_time_low_is_unknown_until_there_is_enough_history(snapshot_count, expected):
    # The distinction that matters: None means "we cannot tell", which callers
    # must render differently from False ("this is not a low").
    assert deals.is_all_time_low(1000.0, 1000.0, 1500.0, snapshot_count) is expected


def test_all_time_low_is_unknown_when_the_price_has_never_moved():
    # The case real data is full of: as of 2026-07-25 not one of the 123
    # tracked products had ever changed price. `current <= lowest` is trivially
    # true for all of them, and calling that a record low is meaningless.
    assert deals.is_all_time_low(1000.0, 1000.0, 1000.0, 18) is None


def test_all_time_low_is_false_when_the_price_sits_above_the_low():
    assert deals.is_all_time_low(1200.0, 1000.0, 1500.0, 5) is False


def test_all_time_low_tolerates_sub_cent_float_noise():
    # Prices are REAL columns; an exact == would miss a genuine record low.
    assert deals.is_all_time_low(1000.009, 1000.0, 1500.0, 5) is True
    assert deals.is_all_time_low(1000.02, 1000.0, 1500.0, 5) is False


def test_pct_below_high_measures_distance_from_the_products_own_peak():
    assert deals.pct_below_high(750.0, 1000.0) == 25.0


@pytest.mark.parametrize("sale,high", [(1000.0, 1000.0), (1200.0, 1000.0), (500.0, 0.0)])
def test_pct_below_high_is_zero_at_or_above_the_peak(sale, high):
    # Also covers highest_price == 0, which would otherwise divide by zero.
    assert deals.pct_below_high(sale, high) == 0.0


@pytest.mark.parametrize(
    "snapshot_count,expected",
    [(0, 0.0), (1, 0.0), (2, pytest.approx(1 / 3)), (3, pytest.approx(2 / 3)), (4, 1.0), (40, 1.0)],
)
def test_history_confidence_ramps_up_and_saturates(snapshot_count, expected):
    assert deals.history_confidence(snapshot_count) == expected


def test_deal_score_discounts_products_with_thin_history():
    # Same 50% drop from peak, very different amounts of evidence for it.
    assert deals.deal_score(500.0, 1000.0, 4) == 50.0
    assert deals.deal_score(500.0, 1000.0, 2) == pytest.approx(16.7, abs=0.05)
    assert deals.deal_score(500.0, 1000.0, 1) == 0.0


def test_deal_score_is_zero_for_a_product_that_has_never_moved():
    assert deals.deal_score(1000.0, 1000.0, 18) == 0.0


def test_days_tracked_spans_first_to_latest_snapshot():
    assert (
        deals.days_tracked("2026-07-19T00:00:00+00:00", "2026-07-26T12:00:00+00:00") == 7.5
    )


def test_days_tracked_is_zero_for_an_unparseable_timestamp():
    # Never worth raising out of a read path over a cosmetic field.
    assert deals.days_tracked("", "2026-07-26T00:00:00+00:00") == 0.0


def test_enrich_adds_every_derived_field():
    snapshot = {
        "sale_price": 500.0,
        "lowest_price": 500.0,
        "highest_price": 1000.0,
        "snapshot_count": 4,
        "first_seen": "2026-07-19T00:00:00+00:00",
        "timestamp": "2026-07-26T00:00:00+00:00",
    }

    assert deals.enrich(snapshot) is snapshot
    assert snapshot["at_all_time_low"] is True
    assert snapshot["pct_below_high"] == 50.0
    assert snapshot["deal_score"] == 50.0
    assert snapshot["days_tracked"] == 7.0
