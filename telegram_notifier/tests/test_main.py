from fastapi.testclient import TestClient

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
