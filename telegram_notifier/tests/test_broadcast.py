import asyncio

import pytest
from telegram.error import Forbidden, RetryAfter, TelegramError

from app import broadcast as broadcast_module
from app import store
from app.broadcast import broadcast, select_changes
from app.schemas import NotifyRequest, PriceChange


DROP = PriceChange(
    name="Yoga Slim 7i", old_price=5999.0, new_price=4999.0, category="Yoga", event="price"
)
NEW = PriceChange(name="ThinkPad T14", new_price=4200.0, category="ThinkPad", event="new")


@pytest.fixture
def db(tmp_path, monkeypatch):
    # SEED_LINES is read from the environment at import time, so setting
    # PRODUCT_LINES here would have no effect — patch the attribute.
    monkeypatch.setattr(store, "SEED_LINES", ["ThinkPad", "Yoga"])
    path = tmp_path / "subscribers.db"

    # Redirecting _connect rather than DEFAULT_DB_PATH: every store function
    # takes `db_path=DEFAULT_DB_PATH` as a *default argument*, which python
    # binds once at definition time, so reassigning the module attribute never
    # reaches them. _connect is the one choke point they all share.
    real_connect = store._connect
    monkeypatch.setattr(store, "_connect", lambda _ignored=None: real_connect(path))

    store.init_db()
    return path


class FakeBot:
    """Records sends; optionally raises a scripted error per chat."""

    def __init__(self, errors=None):
        self.sent: list[tuple[int, str]] = []
        self.errors = errors or {}

    async def send_message(self, chat_id, text, **kwargs):
        error = self.errors.get(chat_id)
        if error is not None:
            # Pop so a retry after RetryAfter succeeds the second time.
            self.errors[chat_id] = None
            raise error
        self.sent.append((chat_id, text))


def test_no_filters_means_everything():
    assert select_changes([DROP, NEW], []) == [DROP, NEW]


def test_filters_select_by_category():
    assert select_changes([DROP, NEW], ["Yoga"]) == [DROP]


def test_filters_are_case_insensitive():
    assert select_changes([DROP, NEW], ["yoga"]) == [DROP]


def test_name_is_a_fallback_when_the_category_is_unexpected():
    # Deliberate over-delivery: a product landing in "Other" must still reach
    # someone following its line. One extra alert beats a missed price drop.
    orphan = PriceChange(name="Yoga Book 9i", new_price=100.0, category="Other")
    assert select_changes([orphan], ["Yoga"]) == [orphan]


def test_non_matching_changes_are_excluded():
    assert select_changes([NEW], ["Yoga"]) == []


def test_broadcast_sends_only_what_each_subscriber_follows(db):
    store.subscribe(1, db_path=db)
    store.subscribe(2, db_path=db)
    store.toggle_filter(2, "Yoga", db)
    bot = FakeBot()

    result = asyncio.run(broadcast(bot, NotifyRequest(changes=[DROP, NEW])))

    assert result["sent"] == 2
    assert result["skipped"] == 0
    chat1 = next(text for chat, text in bot.sent if chat == 1)
    chat2 = next(text for chat, text in bot.sent if chat == 2)
    assert "ThinkPad T14" in chat1
    assert "ThinkPad T14" not in chat2


def test_a_subscriber_matching_nothing_is_skipped_not_failed(db):
    store.subscribe(1, db_path=db)
    store.toggle_filter(1, "Legion", db)
    bot = FakeBot()

    result = asyncio.run(broadcast(bot, NotifyRequest(changes=[DROP])))

    assert (result["skipped"], result["sent"], result["failed"]) == (1, 0, 0)
    assert bot.sent == []


def test_a_blocked_subscriber_is_removed_for_good(db):
    store.subscribe(1, db_path=db)
    bot = FakeBot(errors={1: Forbidden("bot was blocked by the user")})

    result = asyncio.run(broadcast(bot, NotifyRequest(changes=[DROP])))

    assert result["removed"] == 1
    assert store.is_subscribed(1, db) is False


def test_one_failure_does_not_stop_the_rest_of_the_fanout(db):
    store.subscribe(1, db_path=db)
    store.subscribe(2, db_path=db)
    bot = FakeBot(errors={1: TelegramError("boom")})

    result = asyncio.run(broadcast(bot, NotifyRequest(changes=[DROP])))

    assert result["failed"] == 1
    assert result["sent"] == 1
    assert [chat for chat, _ in bot.sent] == [2]


def test_rate_limiting_is_retried_once_and_counted_as_sent(db, monkeypatch):
    store.subscribe(1, db_path=db)
    bot = FakeBot(errors={1: RetryAfter(3)})
    slept = []
    monkeypatch.setattr(broadcast_module.asyncio, "sleep", _record(slept))

    result = asyncio.run(broadcast(bot, NotifyRequest(changes=[DROP])))

    assert result["sent"] == 1
    assert len(bot.sent) == 1
    # Backs off for the interval Telegram asked for, plus a second of margin.
    assert 4 in slept


def test_broadcast_learns_new_lines_from_the_payload(db):
    store.subscribe(1, db_path=db)
    legion = PriceChange(name="Legion 5i", new_price=6199.0, category="Legion", event="new")

    asyncio.run(broadcast(FakeBot(), NotifyRequest(changes=[legion])))

    # The filter menu grows without a redeploy.
    assert "Legion" in store.known_lines(db)


def _record(sink):
    async def fake_sleep(seconds):
        sink.append(seconds)

    return fake_sleep
