import pytest
from pydantic import ValidationError

from app.schemas import NotifyRequest, PriceChange


def test_minimal_change_only_needs_a_name_and_a_price():
    change = PriceChange(name="ThinkPad T14", new_price=4200.00)

    assert change.old_price is None
    assert change.url is None
    assert change.category is None
    assert change.event is None


@pytest.mark.parametrize("event", ["price", "new", "relisted"])
def test_known_events_are_accepted(event):
    assert PriceChange(name="x", new_price=1.0, event=event).event == event


def test_unknown_event_is_rejected():
    # A typo here would silently render as a new listing, so it must not parse.
    with pytest.raises(ValidationError):
        PriceChange(name="x", new_price=1.0, event="reslisted")


def test_empty_name_is_rejected():
    with pytest.raises(ValidationError):
        PriceChange(name="", new_price=1.0)


def test_notify_request_needs_at_least_one_change():
    with pytest.raises(ValidationError):
        NotifyRequest(changes=[])


def test_notify_request_title_is_optional():
    assert NotifyRequest(changes=[{"name": "x", "new_price": 1.0}]).title is None
