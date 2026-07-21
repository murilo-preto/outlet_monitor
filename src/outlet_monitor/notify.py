"""Fire-and-forget client for the Telegram notifier service.

The notifier is a separate container reached only over HTTP. Nothing here may
raise into a scrape: a notifier that is down, slow or misconfigured must never
cost us a price snapshot.
"""

import logging
import os
import threading

import requests

log = logging.getLogger(__name__)

# Service name on the compose network. Set to "" to disable notifications.
DEFAULT_NOTIFIER_URL = "http://notifier:8000"
TIMEOUT_SECONDS = 15.0


def _notifier_url() -> str:
    return os.environ.get("NOTIFIER_URL", DEFAULT_NOTIFIER_URL).strip().rstrip("/")


def send_price_changes(changes: list[dict]) -> bool:
    """POST the changes to the notifier. Returns whether it was delivered.

    Never raises — every failure mode is logged and swallowed.
    """
    if not changes:
        return False

    base_url = _notifier_url()
    if not base_url:
        log.debug("NOTIFIER_URL is empty, skipping notification")
        return False

    try:
        payload = {
            "changes": [
                {
                    "name": change["name"],
                    "new_price": change["new_price"],
                    "old_price": change.get("old_price"),
                    "url": change.get("url"),
                    # The line the notifier groups and filters by. Ours is
                    # already classified, so it beats guessing from the product
                    # name — some families ("V Series") are not derivable from
                    # the name at all.
                    "category": change.get("category"),
                }
                for change in changes
            ]
        }
        response = requests.post(
            f"{base_url}/notify", json=payload, timeout=TIMEOUT_SECONDS
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        log.warning("could not notify %d price change(s): %s", len(changes), exc)
        return False
    except Exception:
        # Belt and braces: notifying is never worth losing a scrape over.
        log.exception("unexpected error notifying %d price change(s)", len(changes))
        return False

    log.info("notified %d price change(s): %s", len(changes), response.text.strip())
    return True


def send_price_changes_async(changes: list[dict]) -> threading.Thread | None:
    """Hand the POST to a background thread so a scrape never waits on it.

    `changes` is already materialized by the caller, so this thread never
    touches the SQLite connection — sqlite3 connections are not shareable
    across threads.
    """
    if not changes:
        return None

    thread = threading.Thread(
        target=send_price_changes, args=(changes,), name="notify-price-changes", daemon=True
    )
    thread.start()
    return thread
