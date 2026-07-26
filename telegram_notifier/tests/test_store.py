import pytest

from app import store


@pytest.fixture
def db(tmp_path, monkeypatch):
    # SEED_LINES is read from the environment at import time, so setting
    # PRODUCT_LINES here would have no effect — patch the attribute.
    monkeypatch.setattr(store, "SEED_LINES", ["ThinkPad", "IdeaPad", "Yoga"])
    path = tmp_path / "subscribers.db"

    # Redirecting _connect rather than DEFAULT_DB_PATH: every store function
    # takes `db_path=DEFAULT_DB_PATH` as a *default argument*, which python
    # binds once at definition time, so reassigning the module attribute never
    # reaches them. _connect is the one choke point they all share.
    real_connect = store._connect
    monkeypatch.setattr(store, "_connect", lambda _ignored=None: real_connect(path))

    store.init_db()
    return path


def test_subscribe_reports_whether_the_chat_was_new(db):
    assert store.subscribe(1, "alice", db) is True
    assert store.subscribe(1, "alice", db) is False
    assert store.is_subscribed(1, db) is True


def test_unsubscribe_reports_whether_the_chat_existed(db):
    store.subscribe(1, db_path=db)

    assert store.unsubscribe(1, db) is True
    assert store.unsubscribe(1, db) is False
    assert store.is_subscribed(1, db) is False


def test_unsubscribing_cascades_to_filters(db):
    store.subscribe(1, db_path=db)
    store.toggle_filter(1, "Yoga", db)

    store.unsubscribe(1, db)
    store.subscribe(1, db_path=db)

    # A real regression guard: the ON DELETE CASCADE only fires because
    # _connect sets PRAGMA foreign_keys = ON, which sqlite leaves off by
    # default. Without it the old filter silently outlives the subscription.
    assert store.get_filters(1, db) == []


def test_toggle_filter_adds_then_removes(db):
    store.subscribe(1, db_path=db)

    assert store.toggle_filter(1, "Yoga", db) is True
    assert store.get_filters(1, db) == ["Yoga"]
    assert store.toggle_filter(1, "Yoga", db) is False
    assert store.get_filters(1, db) == []


def test_get_filters_comes_back_sorted(db):
    store.subscribe(1, db_path=db)
    for line in ("Yoga", "IdeaPad", "ThinkPad"):
        store.toggle_filter(1, line, db)

    assert store.get_filters(1, db) == ["IdeaPad", "ThinkPad", "Yoga"]


def test_clear_filters_leaves_the_subscription_intact(db):
    store.subscribe(1, db_path=db)
    store.toggle_filter(1, "Yoga", db)

    store.clear_filters(1, db)

    assert store.get_filters(1, db) == []
    assert store.is_subscribed(1, db) is True


def test_subscribers_with_filters_includes_those_with_none(db):
    store.subscribe(1, db_path=db)
    store.subscribe(2, db_path=db)
    store.toggle_filter(2, "Yoga", db)

    # An empty list means "send everything" downstream, so a filterless
    # subscriber must be present with [], not missing from the result.
    assert store.subscribers_with_filters(db) == [(1, []), (2, ["Yoga"])]


def test_known_lines_puts_seeded_first_then_discovered(db):
    class Change:
        category = "Legion"
        name = "Legion 5i"

    store.remember_lines([Change()], db)

    assert store.known_lines(db) == ["ThinkPad", "IdeaPad", "Yoga", "Legion"]


def test_remember_lines_prefers_the_supplied_category(db):
    class Change:
        # The name says "Lenovo"; only the caller knows the line is V Series.
        category = "V Series"
        name = "Lenovo V14 Intel Core i3"

    assert store.remember_lines([Change()], db) == ["V Series"]


def test_remember_lines_ignores_a_leading_word_that_is_not_a_line(db):
    class Change:
        category = None
        name = "Lenovo V14 Intel Core i3"

    # "Lenovo" would match half the catalogue as a filter.
    assert store.remember_lines([Change()], db) == []


def test_remember_lines_skips_names_already_covered_by_a_known_line(db):
    class Change:
        category = None
        name = "Yoga Slim 7i"

    assert store.remember_lines([Change()], db) == []


def test_remember_lines_is_a_noop_the_second_time(db):
    class Change:
        category = "Legion"
        name = "Legion 5i"

    assert store.remember_lines([Change()], db) == ["Legion"]
    assert store.remember_lines([Change()], db) == []


def test_count_subscribers(db):
    assert store.count_subscribers(db) == 0
    store.subscribe(1, db_path=db)
    store.subscribe(2, db_path=db)
    assert store.count_subscribers(db) == 2
