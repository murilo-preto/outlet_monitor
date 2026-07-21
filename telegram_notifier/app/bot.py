"""Telegram bot: subscription and product-line filters over long polling."""

from __future__ import annotations

import logging
import os

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    Defaults,
    MessageHandler,
    filters,
)

from . import store

logger = logging.getLogger(__name__)

# Only the first of each group shows up in the BotFather menu; the rest are
# aliases, because people reach for /stop, /sair or /ajuda out of habit.
# Names must be [a-z0-9_] — Telegram has no accented commands, and PTB rejects them.
SUBSCRIBE_COMMANDS = ["start", "inscrever", "assinar", "iniciar", "comecar"]
UNSUBSCRIBE_COMMANDS = ["parar", "stop", "cancelar", "cancel", "sair", "descadastrar", "unsubscribe"]
PRODUCTS_COMMANDS = ["produtos", "filtros", "seguir", "linhas", "escolher"]
HELP_COMMANDS = ["ajuda", "help", "status", "comandos"]

CALLBACK_TOGGLE = "tog"
CALLBACK_ALL = "all"
CALLBACK_DONE = "done"

WELCOME = (
    "✅ Inscrição confirmada!\n\n"
    "Escolha abaixo as linhas que você quer acompanhar. "
    "Sem nenhuma marcada, você recebe <b>todas</b> as mudanças."
)
ALREADY_SUBSCRIBED = "Você já está inscrito. Ajuste abaixo o que quer acompanhar."
GOODBYE = "🛑 Inscrição cancelada. Envie /start quando quiser voltar a receber os alertas."
NOT_SUBSCRIBED = "Você não estava inscrito. Envie /start para começar a receber os alertas."
UNKNOWN_COMMAND = "Não conheço esse comando. Envie /ajuda para ver o que eu sei fazer."
NEED_SUBSCRIPTION = "Você não está inscrito. Envie /start primeiro."
MENU_PROMPT = "Toque para marcar ou desmarcar. Sem nada marcado, você recebe <b>tudo</b>."
MENU_CLOSED = "Pronto! Use /produtos quando quiser mudar sua seleção.\n\n{summary}"


def _describe_filters(lines: list[str]) -> str:
    if not lines:
        return "Você recebe alertas de <b>todos</b> os produtos."
    return "Você acompanha: <b>" + "</b>, <b>".join(lines) + "</b>"


def _menu_markup(chat_id: int) -> InlineKeyboardMarkup:
    active = set(store.get_filters(chat_id))
    buttons = [
        InlineKeyboardButton(
            f"{'✅' if line in active else '▫️'} {line}",
            callback_data=f"{CALLBACK_TOGGLE}:{line}",
        )
        for line in store.known_lines()
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append(
        [
            InlineKeyboardButton(
                f"{'✅' if not active else '📋'} Tudo", callback_data=CALLBACK_ALL
            ),
            InlineKeyboardButton("✔️ Pronto", callback_data=CALLBACK_DONE),
        ]
    )
    return InlineKeyboardMarkup(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None:
        return
    label = chat.username or chat.title or chat.first_name
    added = store.subscribe(chat.id, label)
    logger.info("subscribe chat_id=%s new=%s", chat.id, added)
    await chat.send_message(
        WELCOME if added else ALREADY_SUBSCRIBED, reply_markup=_menu_markup(chat.id)
    )


async def parar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None:
        return
    removed = store.unsubscribe(chat.id)
    logger.info("unsubscribe chat_id=%s existed=%s", chat.id, removed)
    await chat.send_message(GOODBYE if removed else NOT_SUBSCRIBED)


async def produtos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None:
        return
    if not store.is_subscribed(chat.id):
        await chat.send_message(NEED_SUBSCRIPTION)
        return
    await chat.send_message(MENU_PROMPT, reply_markup=_menu_markup(chat.id))


async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None:
        return

    if not store.is_subscribed(chat.id):
        status = "Status: ⚪ <b>não inscrito</b>\n\n/start — receber alertas de preço"
    else:
        status = (
            "Status: ✅ <b>inscrito</b>\n"
            f"{_describe_filters(store.get_filters(chat.id))}\n\n"
            "/produtos — escolher as linhas que quer acompanhar\n"
            "/parar — cancelar os alertas"
        )
    await chat.send_message(
        f"<b>Monitor de preços — Lenovo Outlet</b>\n\n{status}\n/ajuda — mostrar esta mensagem"
    )


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None:
        return
    logger.info("unknown command chat_id=%s text=%r", chat.id, update.effective_message.text)
    await chat.send_message(UNKNOWN_COMMAND)


async def on_menu_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat = update.effective_chat
    if query is None or chat is None:
        return

    if not store.is_subscribed(chat.id):
        await query.answer(NEED_SUBSCRIPTION, show_alert=True)
        return

    data = query.data or ""
    if data == CALLBACK_DONE:
        summary = _describe_filters(store.get_filters(chat.id))
        await query.answer()
        await query.edit_message_text(MENU_CLOSED.format(summary=summary))
        return

    if data == CALLBACK_ALL:
        store.clear_filters(chat.id)
        logger.info("filters cleared chat_id=%s", chat.id)
        await query.answer("Recebendo tudo")
    elif data.startswith(f"{CALLBACK_TOGGLE}:"):
        line = data.split(":", 1)[1]
        active = store.toggle_filter(chat.id, line)
        logger.info("filter chat_id=%s line=%s active=%s", chat.id, line, active)
        await query.answer(f"{'Seguindo' if active else 'Removido'}: {line}")
    else:
        await query.answer()
        return

    try:
        await query.edit_message_reply_markup(reply_markup=_menu_markup(chat.id))
    except BadRequest:
        # Telegram rejects an edit that produces an identical keyboard; harmless.
        pass


async def _post_init(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand(SUBSCRIBE_COMMANDS[0], "Receber alertas de preço"),
            BotCommand(PRODUCTS_COMMANDS[0], "Escolher linhas para acompanhar"),
            BotCommand(UNSUBSCRIBE_COMMANDS[0], "Cancelar os alertas"),
            BotCommand(HELP_COMMANDS[0], "Ver status e comandos"),
        ]
    )


def build_application() -> Application:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    application = (
        Application.builder()
        .token(token)
        .defaults(Defaults(parse_mode=ParseMode.HTML))
        .post_init(_post_init)
        .build()
    )
    application.add_handler(CommandHandler(SUBSCRIBE_COMMANDS, start))
    application.add_handler(CommandHandler(UNSUBSCRIBE_COMMANDS, parar))
    application.add_handler(CommandHandler(PRODUCTS_COMMANDS, produtos))
    application.add_handler(CommandHandler(HELP_COMMANDS, ajuda))
    application.add_handler(CallbackQueryHandler(on_menu_click))
    # Must be registered last: catches any other /command.
    application.add_handler(MessageHandler(filters.COMMAND, unknown))
    return application
