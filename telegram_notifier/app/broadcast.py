"""Fan-out of price reports, filtered per subscriber."""

from __future__ import annotations

import asyncio
import logging
import os

from telegram import Bot, LinkPreviewOptions
from telegram.error import Forbidden, RetryAfter, TelegramError

from . import store
from .report import build_messages
from .schemas import NotifyRequest, PriceChange

logger = logging.getLogger(__name__)

# Telegram tolerates ~30 messages/second for broadcasts. 0.05s ≈ 20/s, with margin.
DELAY_SECONDS = float(os.environ.get("BROADCAST_DELAY_SECONDS", "0.05"))

_NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


def _matches(change: PriceChange, lowered: list[str]) -> bool:
    """A change belongs to a subscriber if its category or its name says so.

    Category is the authoritative signal, but the name is still checked so a
    product landing in an unexpected category ("Other") isn't silently withheld
    from someone following its line. Erring toward one extra alert beats a
    missed price drop.
    """
    if change.category and change.category.lower() in lowered:
        return True
    return any(line in change.name.lower() for line in lowered)


def select_changes(changes: list[PriceChange], filters: list[str]) -> list[PriceChange]:
    """Changes this subscriber cares about. No filters means everything."""
    if not filters:
        return changes
    lowered = [line.lower() for line in filters]
    return [c for c in changes if _matches(c, lowered)]


async def _send_with_retry(bot: Bot, chat_id: int, text: str) -> None:
    """Send one message, honouring a single RetryAfter back-off from Telegram."""
    try:
        await bot.send_message(chat_id, text, link_preview_options=_NO_PREVIEW)
    except RetryAfter as exc:
        await asyncio.sleep(exc.retry_after + 1)
        await bot.send_message(chat_id, text, link_preview_options=_NO_PREVIEW)


async def broadcast(bot: Bot, payload: NotifyRequest) -> dict[str, int]:
    """Deliver each subscriber the slice of the report matching their filters."""
    store.remember_lines(payload.changes)

    recipients = store.subscribers_with_filters()
    sent = skipped = failed = removed = 0

    for chat_id, filters in recipients:
        changes = select_changes(payload.changes, filters)
        if not changes:
            skipped += 1
            continue

        messages = build_messages(payload.model_copy(update={"changes": changes}))
        try:
            for message in messages:
                await _send_with_retry(bot, chat_id, message)
                await asyncio.sleep(DELAY_SECONDS)
            sent += 1
        except Forbidden:
            # User blocked the bot or deleted the chat — drop them for good.
            store.unsubscribe(chat_id)
            removed += 1
            logger.info("removed blocked subscriber chat_id=%s", chat_id)
        except TelegramError:
            failed += 1
            logger.exception("failed to notify chat_id=%s", chat_id)

    return {
        "subscribers": len(recipients),
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
        "removed": removed,
    }
