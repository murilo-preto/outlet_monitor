import requests

from outlet_monitor import notify


CHANGES = [
    {"product_id": "p1", "name": "Yoga Slim 7i", "url": "https://x/yoga",
     "category": "Yoga", "old_price": 5999.00, "new_price": 4999.00},
    {"product_id": "p2", "name": "Lenovo V14 Intel Core i3", "url": "https://x/v14",
     "category": "V Series", "old_price": None, "new_price": 8999.00},
]


class FakeResponse:
    def __init__(self, text='{"sent": 1}'):
        self.text = text

    def raise_for_status(self):
        return None


def test_send_price_changes_posts_notifier_payload(monkeypatch):
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append((url, json, timeout))
        return FakeResponse()

    monkeypatch.setattr(notify.requests, "post", fake_post)
    monkeypatch.delenv("NOTIFIER_URL", raising=False)

    assert notify.send_price_changes(CHANGES) is True

    url, payload, timeout = calls[0]
    assert url == "http://notifier:8000/notify"
    assert timeout == notify.TIMEOUT_SECONDS
    # product_id is internal to the monitor and must not leak into the payload.
    assert payload == {
        "changes": [
            {"name": "Yoga Slim 7i", "new_price": 4999.00, "old_price": 5999.00,
             "url": "https://x/yoga", "category": "Yoga"},
            # "V Series" is unguessable from the name — it only reaches the
            # notifier because the monitor classified it.
            {"name": "Lenovo V14 Intel Core i3", "new_price": 8999.00, "old_price": None,
             "url": "https://x/v14", "category": "V Series"},
        ]
    }


def test_send_price_changes_swallows_connection_errors(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        raise requests.ConnectionError("notifier is down")

    monkeypatch.setattr(notify.requests, "post", fake_post)

    # A dead notifier must never propagate into the scrape that called us.
    assert notify.send_price_changes(CHANGES) is False


def test_send_price_changes_swallows_http_errors(monkeypatch):
    class Failing(FakeResponse):
        def raise_for_status(self):
            raise requests.HTTPError("500 Server Error")

    monkeypatch.setattr(notify.requests, "post", lambda *a, **kw: Failing())

    assert notify.send_price_changes(CHANGES) is False


def test_send_price_changes_skips_empty_list(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("should not have been called")

    monkeypatch.setattr(notify.requests, "post", explode)

    assert notify.send_price_changes([]) is False


def test_send_price_changes_honours_notifier_url(monkeypatch):
    calls = []
    monkeypatch.setattr(
        notify.requests, "post",
        lambda url, json=None, timeout=None: calls.append(url) or FakeResponse(),
    )
    monkeypatch.setenv("NOTIFIER_URL", "http://elsewhere:9000/")

    notify.send_price_changes(CHANGES)

    assert calls == ["http://elsewhere:9000/notify"]


def test_empty_notifier_url_disables_notifications(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("should not have been called")

    monkeypatch.setattr(notify.requests, "post", explode)
    monkeypatch.setenv("NOTIFIER_URL", "")

    assert notify.send_price_changes(CHANGES) is False


def test_async_send_runs_in_background_thread(monkeypatch):
    seen = {}

    def fake_post(url, json=None, timeout=None):
        seen["thread"] = __import__("threading").current_thread().name
        return FakeResponse()

    monkeypatch.setattr(notify.requests, "post", fake_post)
    monkeypatch.delenv("NOTIFIER_URL", raising=False)

    thread = notify.send_price_changes_async(CHANGES)
    thread.join(timeout=5)

    assert seen["thread"] == "notify-price-changes"
    assert not thread.is_alive()


def test_async_send_is_a_noop_without_changes():
    assert notify.send_price_changes_async([]) is None


def test_send_price_changes_tolerates_missing_optional_keys(monkeypatch):
    sent = []
    monkeypatch.setattr(
        notify.requests, "post",
        lambda url, json=None, timeout=None: sent.append(json) or FakeResponse(),
    )
    monkeypatch.delenv("NOTIFIER_URL", raising=False)

    # A caller that only knows name/new_price must not blow up the scrape.
    assert notify.send_price_changes([{"name": "Bare", "new_price": 10.0}]) is True
    assert sent[0]["changes"][0] == {
        "name": "Bare", "new_price": 10.0, "old_price": None,
        "url": None, "category": None,
    }


def test_send_price_changes_swallows_unexpected_errors(monkeypatch):
    monkeypatch.setattr(notify.requests, "post", lambda *a, **kw: FakeResponse())

    # Malformed change: no "name" at all. Must be logged, not raised.
    assert notify.send_price_changes([{"new_price": 1.0}]) is False
