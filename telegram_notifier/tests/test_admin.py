import asyncio

from telegram.error import TelegramError

from app.admin import send_admin_alert
from app.schemas import AlertRequest


class FakeBot:
    def __init__(self, error=None):
        self.sent: list[tuple[str, str]] = []
        self.error = error

    async def send_message(self, chat_id, text, **kwargs):
        if self.error:
            raise self.error
        self.sent.append((chat_id, text))


def test_alert_goes_to_the_configured_admin_chat(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_ID", "4242")
    bot = FakeBot()

    sent = asyncio.run(send_admin_alert(bot, AlertRequest(text="coleta falhou", level="error")))

    assert sent == 1
    chat_id, text = bot.sent[0]
    assert chat_id == "4242"
    assert "coleta falhou" in text
    assert text.startswith("🚨")


def test_warning_level_uses_a_softer_marker(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_ID", "4242")
    bot = FakeBot()

    asyncio.run(send_admin_alert(bot, AlertRequest(text="algo estranho")))

    assert bot.sent[0][1].startswith("⚠️")


def test_no_admin_chat_configured_is_a_silent_noop(monkeypatch):
    # The default for a fresh deployment. Alerting about a scrape failure must
    # never itself become a failure.
    monkeypatch.delenv("ADMIN_CHAT_ID", raising=False)
    bot = FakeBot()

    assert asyncio.run(send_admin_alert(bot, AlertRequest(text="coleta falhou"))) == 0
    assert bot.sent == []


def test_a_telegram_error_is_swallowed(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_ID", "4242")
    bot = FakeBot(error=TelegramError("chat not found"))

    assert asyncio.run(send_admin_alert(bot, AlertRequest(text="coleta falhou"))) == 0
