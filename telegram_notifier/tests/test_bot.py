import asyncio

import pytest
from telegram.error import BadRequest

from app import bot as bot_module
from app import store


@pytest.fixture
def db(tmp_path, monkeypatch):
    # SEED_LINES is read from the environment at import time, so setting
    # PRODUCT_LINES here would have no effect — patch the attribute.
    monkeypatch.setattr(store, "SEED_LINES", ["ThinkPad", "Yoga"])
    path = tmp_path / "subscribers.db"

    # Redirecting _connect rather than DEFAULT_DB_PATH: every store function
    # takes `db_path=DEFAULT_DB_PATH` as a *default argument*, which python
    # binds once at definition time, so reassigning the module attribute never
    # reaches them. _connect is the one choke point they all share.
    real_connect = store._connect
    monkeypatch.setattr(store, "_connect", lambda _ignored=None: real_connect(path))

    store.init_db()
    return path


class FakeChat:
    def __init__(self, chat_id=1):
        self.id = chat_id
        self.username = "alice"
        self.title = None
        self.first_name = None
        self.messages: list[tuple[str, object]] = []

    async def send_message(self, text, reply_markup=None, **kwargs):
        self.messages.append((text, reply_markup))


class FakeQuery:
    def __init__(self, data, edit_error=None):
        self.data = data
        self.answers: list[tuple] = []
        self.edited_text: str | None = None
        self.edited_markup = False
        self._edit_error = edit_error

    async def answer(self, text=None, show_alert=False):
        self.answers.append((text, show_alert))

    async def edit_message_text(self, text, **kwargs):
        self.edited_text = text

    async def edit_message_reply_markup(self, reply_markup=None):
        if self._edit_error:
            raise self._edit_error
        self.edited_markup = True


class FakeUpdate:
    def __init__(self, chat, query=None, text=None):
        self.effective_chat = chat
        self.callback_query = query
        self.effective_message = type("Msg", (), {"text": text})()


def button_labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def test_start_welcomes_a_new_chat(db):
    chat = FakeChat()

    asyncio.run(bot_module.start(FakeUpdate(chat), None))

    text, markup = chat.messages[0]
    assert text == bot_module.WELCOME
    assert markup is not None
    assert store.is_subscribed(1, db) is True


def test_start_on_an_existing_chat_says_so(db):
    store.subscribe(1, db_path=db)
    chat = FakeChat()

    asyncio.run(bot_module.start(FakeUpdate(chat), None))

    assert chat.messages[0][0] == bot_module.ALREADY_SUBSCRIBED


def test_parar_on_a_non_subscriber(db):
    chat = FakeChat()

    asyncio.run(bot_module.parar(FakeUpdate(chat), None))

    assert chat.messages[0][0] == bot_module.NOT_SUBSCRIBED


def test_parar_confirms_for_a_subscriber(db):
    store.subscribe(1, db_path=db)
    chat = FakeChat()

    asyncio.run(bot_module.parar(FakeUpdate(chat), None))

    assert chat.messages[0][0] == bot_module.GOODBYE


def test_produtos_requires_a_subscription(db):
    chat = FakeChat()

    asyncio.run(bot_module.produtos(FakeUpdate(chat), None))

    assert chat.messages[0][0] == bot_module.NEED_SUBSCRIPTION


def test_ajuda_reflects_subscription_state(db):
    chat = FakeChat()

    asyncio.run(bot_module.ajuda(FakeUpdate(chat), None))
    assert "não inscrito" in chat.messages[0][0]

    store.subscribe(1, db_path=db)
    store.toggle_filter(1, "Yoga", db)
    asyncio.run(bot_module.ajuda(FakeUpdate(chat), None))
    assert "Você acompanha" in chat.messages[1][0]
    assert "Yoga" in chat.messages[1][0]


def test_unknown_command_is_answered(db):
    chat = FakeChat()

    asyncio.run(bot_module.unknown(FakeUpdate(chat, text="/nope"), None))

    assert chat.messages[0][0] == bot_module.UNKNOWN_COMMAND


def test_menu_marks_active_lines(db):
    store.subscribe(1, db_path=db)
    store.toggle_filter(1, "Yoga", db)

    labels = button_labels(bot_module._menu_markup(1))

    assert "✅ Yoga" in labels
    assert "▫️ ThinkPad" in labels


def test_menu_click_toggles_a_line(db):
    store.subscribe(1, db_path=db)
    query = FakeQuery("tog:Yoga")

    asyncio.run(bot_module.on_menu_click(FakeUpdate(FakeChat(), query), None))

    assert store.get_filters(1, db) == ["Yoga"]
    assert query.answers[0][0] == "Seguindo: Yoga"
    assert query.edited_markup is True


def test_menu_click_all_clears_every_filter(db):
    store.subscribe(1, db_path=db)
    store.toggle_filter(1, "Yoga", db)
    query = FakeQuery("all")

    asyncio.run(bot_module.on_menu_click(FakeUpdate(FakeChat(), query), None))

    assert store.get_filters(1, db) == []


def test_menu_click_done_closes_with_a_summary(db):
    store.subscribe(1, db_path=db)
    store.toggle_filter(1, "Yoga", db)
    query = FakeQuery("done")

    asyncio.run(bot_module.on_menu_click(FakeUpdate(FakeChat(), query), None))

    assert "Yoga" in query.edited_text


def test_menu_click_requires_a_subscription(db):
    query = FakeQuery("tog:Yoga")

    asyncio.run(bot_module.on_menu_click(FakeUpdate(FakeChat(), query), None))

    assert query.answers[0] == (bot_module.NEED_SUBSCRIPTION, True)
    assert store.get_filters(1, db) == []


def test_identical_keyboard_edit_is_swallowed(db):
    # Telegram rejects an edit that would produce the same keyboard, which is
    # a normal outcome of double-tapping and must not surface as an error.
    store.subscribe(1, db_path=db)
    query = FakeQuery("tog:Yoga", edit_error=BadRequest("Message is not modified"))

    asyncio.run(bot_module.on_menu_click(FakeUpdate(FakeChat(), query), None))

    assert store.get_filters(1, db) == ["Yoga"]


def test_build_application_requires_a_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")

    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        bot_module.build_application()
