"""Operational alerts to a single admin chat.

Kept apart from the price broadcast: that fans out to every subscriber and
carries a list of price changes, neither of which fits "the scraper has been
failing for a day".
"""

from __future__ import annotations

import logging
import os

from telegram import Bot, LinkPreviewOptions
from telegram.error import TelegramError

from .schemas import AlertRequest

logger = logging.getLogger(__name__)

_NO_PREVIEW = LinkPreviewOptions(is_disabled=True)

_LEVEL_PREFIX = {"warning": "⚠️", "error": "🚨"}


def admin_chat_id() -> str:
    """Read at call time, not import time, so tests and redeploys can change it."""
    return os.environ.get("ADMIN_CHAT_ID", "").strip()


async def send_admin_alert(bot: Bot, payload: AlertRequest) -> int:
    """Deliver one alert. Returns how many chats received it (0 or 1).

    An unset ADMIN_CHAT_ID is the default for a fresh deployment and must be a
    silent no-op — never a 500 — or the monitor's own failure handling starts
    reporting failures of its own.
    """
    chat_id = admin_chat_id()
    if not chat_id:
        logger.info("ADMIN_CHAT_ID is not set, dropping alert: %s", payload.text)
        return 0

    prefix = _LEVEL_PREFIX.get(payload.level, "")
    text = f"{prefix} {payload.text}".strip() if prefix not in payload.text else payload.text

    try:
        await bot.send_message(chat_id, text, link_preview_options=_NO_PREVIEW)
    except TelegramError:
        logger.exception("failed to deliver admin alert to chat_id=%s", chat_id)
        return 0
    return 1
