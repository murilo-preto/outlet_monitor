import pytest
from fastapi.testclient import TestClient

from app import store
from app.main import app


# Constructed without a `with` block on purpose: that skips the lifespan, so
# app.state.bot is never set. This is the cold-start window, and the one path
# where these endpoints could 500 instead of answering.
client = TestClient(app)


def test_notify_reports_that_the_bot_is_not_ready():
    response = client.post("/notify", json={"changes": [{"name": "x", "new_price": 1.0}]})

    assert response.status_code == 503


def test_alert_reports_that_the_bot_is_not_ready():
    response = client.post("/alert", json={"text": "coleta falhou"})

    assert response.status_code == 503


def test_alert_rejects_an_empty_message():
    assert client.post("/alert", json={"text": ""}).status_code == 422


def test_alert_rejects_an_unknown_level():
    assert (
        client.post("/alert", json={"text": "x", "level": "catastrophe"}).status_code == 422
    )


class FakeBot:
    def __init__(self):
        self.sent: list[tuple] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))


@pytest.fixture
def ready(tmp_path, monkeypatch):
    """A client whose bot is available, without running the polling lifespan."""
    monkeypatch.setattr(store, "SEED_LINES", ["Yoga"])
    real_connect = store._connect
    monkeypatch.setattr(
        store, "_connect", lambda _ignored=None: real_connect(tmp_path / "subscribers.db")
    )
    store.init_db()

    bot = FakeBot()
    monkeypatch.setattr(app.state, "bot", bot, raising=False)
    return TestClient(app), bot


def test_health_reports_the_subscriber_count(ready):
    client, _ = ready

    body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["subscribers"] == 0


def test_subscribers_count_endpoint(ready):
    client, _ = ready
    store.subscribe(1)

    assert client.get("/subscribers/count").json() == {"count": 1}


def test_notify_broadcasts_to_subscribers(ready):
    client, bot = ready
    store.subscribe(1)

    body = client.post(
        "/notify",
        json={"changes": [{"name": "Yoga Slim 7i", "old_price": 5999.0, "new_price": 4999.0}]},
    ).json()

    assert body["subscribers"] == 1
    assert body["sent"] == 1
    assert len(bot.sent) == 1


def test_alert_delivers_to_the_admin_chat(ready, monkeypatch):
    client, bot = ready
    monkeypatch.setenv("ADMIN_CHAT_ID", "4242")

    assert client.post("/alert", json={"text": "coleta falhou"}).json() == {"sent": 1}
    assert bot.sent[0][0] == "4242"


def test_alert_succeeds_with_no_admin_chat_configured(ready, monkeypatch):
    client, bot = ready
    monkeypatch.delenv("ADMIN_CHAT_ID", raising=False)

    # Reported as delivered-to-nobody, not as an error: an unconfigured admin
    # channel is the default, and the monitor calls this while already failing.
    assert client.post("/alert", json={"text": "coleta falhou"}).json() == {"sent": 0}
    assert bot.sent == []
