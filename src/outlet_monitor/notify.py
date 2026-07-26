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


def _post(path: str, payload: dict, what: str) -> bool:
    """POST to the notifier, swallowing every failure. Never raises."""
    base_url = _notifier_url()
    if not base_url:
        log.debug("NOTIFIER_URL is empty, skipping %s", what)
        return False

    try:
        response = requests.post(f"{base_url}{path}", json=payload, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as exc:
        log.warning("could not send %s: %s", what, exc)
        return False
    except Exception:
        # Belt and braces: notifying is never worth losing a scrape over.
        log.exception("unexpected error sending %s", what)
        return False

    log.info("sent %s: %s", what, response.text.strip())
    return True


def send_price_changes(changes: list[dict]) -> bool:
    """POST the changes to the notifier. Returns whether it was delivered.

    Never raises — every failure mode is logged and swallowed.
    """
    if not changes:
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
                    # "new" / "relisted" / "price". Only we can tell a first
                    # listing from a returning one; the notifier has no history.
                    "event": change.get("event"),
                    # True/False/None — None meaning "not enough history to
                    # say". Same reasoning as `event`: the notifier stores no
                    # prices, so it could never work this out itself.
                    "all_time_low": change.get("all_time_low"),
                }
                for change in changes
            ]
        }
    except Exception:
        # A malformed change must be logged, not raised into the scrape.
        log.exception("unexpected error building payload for %d change(s)", len(changes))
        return False

    return _post("/notify", payload, f"{len(changes)} price change(s)")


def send_admin_alert(text: str, level: str = "warning") -> bool:
    """Tell the operator something is wrong. Same never-raise contract as above.

    Goes to a dedicated endpoint rather than /notify: that one fans out to
    every subscriber and carries a list of price changes, and an operational
    alert is neither of those things.
    """
    return _post("/alert", {"text": text, "level": level}, "admin alert")


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


def send_admin_alert_async(text: str, level: str = "warning") -> threading.Thread:
    """Same as send_admin_alert, off the caller's thread."""
    thread = threading.Thread(
        target=send_admin_alert, args=(text, level), name="notify-admin-alert", daemon=True
    )
    thread.start()
    return thread
