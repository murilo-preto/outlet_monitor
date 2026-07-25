from app.report import MAX_MESSAGE_CHARS, build_messages, format_brl
from app.schemas import NotifyRequest


def make_payload(*changes: dict, title: str | None = None) -> NotifyRequest:
    return NotifyRequest(changes=list(changes), title=title)


def only_message(*changes: dict, title: str | None = None) -> str:
    messages = build_messages(make_payload(*changes, title=title))
    assert len(messages) == 1
    return messages[0]


DROP = {"name": "Yoga Slim 7i", "old_price": 5999.00, "new_price": 4999.00,
        "url": "https://x/yoga", "category": "Yoga", "event": "price"}
NEW = {"name": "ThinkPad T14", "new_price": 4200.00, "url": "https://x/t14",
       "category": "ThinkPad", "event": "new"}
RELISTED = {"name": "Legion 5i", "new_price": 6199.00, "url": "https://x/legion",
            "category": "Legion", "event": "relisted"}


def test_format_brl_uses_pt_br_separators():
    assert format_brl(1234.5) == "R$ 1.234,50"
    assert format_brl(0) == "R$ 0,00"
    assert format_brl(1234567.89) == "R$ 1.234.567,89"


def test_price_drop_shows_both_prices_and_the_delta():
    message = only_message(DROP)

    assert "📉" in message
    assert "<s>R$ 5.999,00</s> → <b>R$ 4.999,00</b>" in message
    assert "(-16,7% · -R$ 1.000,00)" in message


def test_price_rise_flips_the_arrow_and_the_sign():
    message = only_message({**DROP, "old_price": 4999.00, "new_price": 5999.00})

    assert "📈" in message
    assert "(+20,0% · +R$ 1.000,00)" in message


def test_new_listing_has_no_previous_price():
    message = only_message(NEW)

    assert "🆕" in message
    assert "R$ 4.200,00" in message
    assert "→" not in message


def test_relisted_product_is_marked_as_returning_stock():
    message = only_message(RELISTED)

    assert "🔁" in message
    assert "De volta ao outlet · R$ 6.199,00" in message
    # A relist must not read as a first-ever listing.
    assert "🆕" not in message


def test_event_is_inferred_when_the_caller_omits_it():
    # Payload shape from before `event` existed: a rolling restart can leave an
    # older api container posting these, and they still have to render.
    drop = only_message({"name": "Yoga", "old_price": 5999.00, "new_price": 4999.00})
    listing = only_message({"name": "Yoga", "new_price": 4999.00})

    assert "📉" in drop
    assert "🆕" in listing


def test_explicit_event_beats_the_old_price_inference():
    # No old_price, but the caller knows this one has been listed before.
    assert "🔁" in only_message({"name": "Yoga", "new_price": 4999.00, "event": "relisted"})


def test_summary_counts_each_kind_of_change():
    message = only_message(DROP, NEW, RELISTED,
                           {**DROP, "old_price": 4000.00, "new_price": 4500.00})

    assert "1 queda(s), 1 alta(s), 1 novo(s), 1 de volta" in message


def test_summary_omits_kinds_with_no_changes():
    message = only_message(NEW)

    assert "1 novo(s)" in message
    assert "queda" not in message
    assert "de volta" not in message


def test_summary_falls_back_when_nothing_is_countable():
    # Same price on both sides: neither a drop nor a rise, and not a listing.
    message = only_message({"name": "Yoga", "old_price": 4999.00, "new_price": 4999.00})

    assert "1 atualização(ões)" in message


def test_default_title_is_used_when_none_is_given():
    assert "<b>Alerta de preços — Lenovo Outlet</b>" in only_message(NEW)


def test_custom_title_replaces_the_default():
    message = only_message(NEW, title="Resumo diário")

    assert "<b>Resumo diário</b>" in message
    assert "Alerta de preços" not in message


def test_product_name_is_html_escaped():
    message = only_message({**NEW, "name": 'ThinkPad <b>"E14"</b> & Cia'})

    assert "&lt;b&gt;" in message
    assert "&amp; Cia" in message
    # The only real tag on the line is the link wrapping the name.
    assert "<b>ThinkPad" not in message


def test_title_is_html_escaped():
    assert "&lt;script&gt;" in only_message(NEW, title="<script>")


def test_url_is_escaped_with_quotes_inside_the_href():
    message = only_message({**NEW, "url": 'https://x/t14?a="1"&b=2'})

    assert 'href="https://x/t14?a=&quot;1&quot;&amp;b=2"' in message


def test_name_is_bold_when_there_is_no_url():
    message = only_message({"name": "Sem link", "new_price": 10.0})

    assert "<b>Sem link</b>" in message
    assert "<a href" not in message


def test_zero_old_price_does_not_divide_by_zero():
    message = only_message({"name": "Grátis", "old_price": 0.0, "new_price": 100.0})

    assert "0,0%" in message


def test_long_report_is_split_into_messages_within_telegram_limit():
    changes = [{**NEW, "name": f"ThinkPad T14 Gen {i}"} for i in range(200)]

    messages = build_messages(make_payload(*changes))

    assert len(messages) > 1
    assert all(len(m) <= MAX_MESSAGE_CHARS for m in messages)


def test_every_chunk_repeats_the_header():
    changes = [{**NEW, "name": f"ThinkPad T14 Gen {i}"} for i in range(200)]

    messages = build_messages(make_payload(*changes))

    assert all(m.startswith("<b>Alerta de preços — Lenovo Outlet</b>") for m in messages)


def test_no_change_is_dropped_when_splitting():
    changes = [{**NEW, "name": f"ThinkPad T14 Gen {i}"} for i in range(200)]

    messages = build_messages(make_payload(*changes))

    joined = "\n".join(messages)
    assert all(f"ThinkPad T14 Gen {i}" in joined for i in range(200))


def test_a_single_change_produces_exactly_one_message():
    assert len(build_messages(make_payload(NEW))) == 1
