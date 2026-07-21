"""Turns a /notify payload into formatted Telegram messages."""

from __future__ import annotations

from html import escape

from .schemas import NotifyRequest, PriceChange

# Telegram hard-caps a message at 4096 characters; leave room for the header.
MAX_MESSAGE_CHARS = 3800


def format_brl(value: float) -> str:
    """1234.5 -> 'R$ 1.234,50' (pt-BR separators, no locale dependency)."""
    formatted = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {formatted}"


def _change_line(change: PriceChange) -> str:
    name = escape(change.name)
    label = f'<a href="{escape(change.url, quote=True)}">{name}</a>' if change.url else f"<b>{name}</b>"

    if change.old_price is None:
        return f"🆕 {label}\n    {format_brl(change.new_price)}"

    delta = change.new_price - change.old_price
    arrow = "📉" if delta < 0 else "📈"
    pct = (delta / change.old_price * 100) if change.old_price else 0.0
    sign = "+" if delta > 0 else "-"
    pct_text = f"{abs(pct):.1f}".replace(".", ",")

    return (
        f"{arrow} {label}\n"
        f"    <s>{format_brl(change.old_price)}</s> → <b>{format_brl(change.new_price)}</b>"
        f"  ({sign}{pct_text}% · {sign}{format_brl(abs(delta))})"
    )


def build_messages(payload: NotifyRequest) -> list[str]:
    """Render the report, split into chunks that fit Telegram's size limit."""
    drops = sum(1 for c in payload.changes if c.old_price is not None and c.new_price < c.old_price)
    rises = sum(1 for c in payload.changes if c.old_price is not None and c.new_price > c.old_price)
    news = sum(1 for c in payload.changes if c.old_price is None)

    parts = []
    if drops:
        parts.append(f"{drops} queda(s)")
    if rises:
        parts.append(f"{rises} alta(s)")
    if news:
        parts.append(f"{news} novo(s)")
    summary = ", ".join(parts) or f"{len(payload.changes)} atualização(ões)"

    title = escape(payload.title) if payload.title else "Alerta de preços — Lenovo Outlet"
    header = f"<b>{title}</b>\n{summary}\n"

    messages: list[str] = []
    current = header
    for change in payload.changes:
        line = "\n" + _change_line(change) + "\n"
        if len(current) + len(line) > MAX_MESSAGE_CHARS:
            messages.append(current.rstrip())
            current = header + line
        else:
            current += line
    messages.append(current.rstrip())
    return messages
