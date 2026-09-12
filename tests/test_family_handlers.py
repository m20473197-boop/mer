"""Marriage and Family handler tests — Telegram layer simulated, stack real.

Also pins the two hard constraints of this feature: it is driven **only** by
text commands (no inline keyboards anywhere in the family flow) and it does not
touch the existing menus.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Chat, InlineKeyboardMarkup, Message, Update, User

from app.bot.handlers import family, main_menu
from app.bot.handlers import register_handlers
from app.bot.keyboards import callbacks
from app.core import constants
from app.database.models.marriage import Marriage

# === Helpers =================================================================


def make_user(tg_id: int, name: str = "علی") -> User:
    return User(id=tg_id, first_name=name, is_bot=False, username=f"u{tg_id}")


def make_chat(chat_id: int, chat_type: str = Chat.GROUP) -> Chat:
    return Chat(id=chat_id, type=chat_type)


def make_message_update(
    user: User,
    text: str,
    *,
    chat: Chat | None = None,
    reply_to: User | None = None,
) -> Update:
    replied = None
    if reply_to is not None:
        replied = Message(
            message_id=7,
            date=datetime.now(),
            chat=chat or make_chat(user.id),
            from_user=reply_to,
            text="سلام بچه‌ها",
        )
    message = Message(
        message_id=1,
        date=datetime.now(),
        chat=chat or make_chat(user.id),
        from_user=user,
        text=text,
        reply_to_message=replied,
    )
    return Update(update_id=1, message=message)


@pytest.fixture
def tg(monkeypatch):
    """Capture every outbound message: group replies and private pushes."""
    reply, send = AsyncMock(), AsyncMock()
    monkeypatch.setattr(Message, "reply_text", reply)
    return SimpleNamespace(reply=reply, send=send)


@pytest.fixture
def context(services, tg):
    ctx = MagicMock()
    ctx.application.bot_data = {"services": services, "admin_ids": ()}
    ctx.bot = MagicMock()
    ctx.bot.send_message = tg.send
    ctx.user_data = {}
    return ctx


async def make_couple(services, db):
    """Two registered, eligible players (tg ids 9101 / 9102)."""
    a = await services.players.register_or_get(
        telegram_user_id=9101, username="a", display_name="امیر"
    )
    b = await services.players.register_or_get(
        telegram_user_id=9102, username="b", display_name="سارا"
    )
    await services.levels.set_level(a.player_id, 5)
    await services.levels.set_level(b.player_id, 5)
    await services.money.add_money(a.player_id, 80_000_000)
    await services.money.add_money(b.player_id, 80_000_000)
    return a, b


def last_reply_text(tg) -> str:
    return tg.reply.await_args.args[0]


# === Command wiring ==========================================================


async def test_family_commands_are_registered_as_text_messages(services, db):
    """Handlers exist for every trigger and use text, never a button."""
    from telegram.ext import ApplicationBuilder, CallbackQueryHandler, MessageHandler

    application = ApplicationBuilder().token("123456:TEST").build()
    # A bare Application has no group-0 key until something is registered.
    before = len(application.handlers.get(0, []))
    register_handlers(application)
    handlers = application.handlers[0]
    assert len(handlers) > before
    # The family triggers live in MessageHandler registrations only.
    family_texts = [
        constants.MARRIAGE_TRIGGER,
        constants.MARRIAGE_ACCEPT_TRIGGER,
        constants.MARRIAGE_REJECT_TRIGGER,
        constants.DIVORCE_TRIGGER,
        constants.CHEATING_TRIGGER,
        constants.RELATIONSHIP_TRIGGER,
        constants.FAMILY_TRIGGER,
    ]
    pattern_hits = {t: 0 for t in family_texts}
    for handler in handlers:
        if isinstance(handler, CallbackQueryHandler):
            assert "famil" not in str(getattr(handler, "patterns", ""))
        if isinstance(handler, MessageHandler):
            text = str(getattr(handler, "filters", ""))
            for trigger in family_texts:
                if trigger in text:
                    pattern_hits[trigger] += 1
    assert all(count >= 1 for count in pattern_hits.values()), pattern_hits


async def test_existing_main_menu_keyboard_is_untouched(services, db, monkeypatch):
    """No family button was added to any existing menu."""
    from app.bot.keyboards.main_menu import build_main_menu

    markup = build_main_menu()
    data = {b.callback_data for row in markup.inline_keyboard for b in row}
    assert data == {
        callbacks.PROFILE,
        callbacks.STATUS,
        callbacks.JOBS_MENU,
        callbacks.BUSINESS_MENU,
        callbacks.MARKET_MENU,
        callbacks.BANK_MENU,
        callbacks.CRIME_MENU,
        callbacks.DIVAR_MENU,
        callbacks.VEHICLE_MENU,
        callbacks.HOUSING_MENU,
    }


# === Marriage ================================================================


async def test_marriage_command_on_a_reply_opens_a_request(services, db, tg, context):
    a, b = await make_couple(services, db)

    update = make_message_update(
        make_user(9101, "امیر"),
        constants.MARRIAGE_TRIGGER,
        reply_to=make_user(9102, "سارا"),
    )
    await family.marriage_text_handler(update, context)

    assert "درخواست ازدواج" in last_reply_text(tg)
    # The target is reached privately with the accept/reject instructions.
    context.bot.send_message.assert_awaited_once()
    sent = context.bot.send_message.await_args.kwargs
    assert sent["chat_id"] == 9102
    assert constants.MARRIAGE_ACCEPT_TRIGGER in sent["text"]
    assert constants.MARRIAGE_REJECT_TRIGGER in sent["text"]

    pending = await services.family.get_pending_request_for(b.player_id)
    assert pending is not None and pending.proposer_player_id == a.player_id


async def test_marriage_command_without_a_reply_asks_for_one(services, db, tg, context):
    await make_couple(services, db)
    update = make_message_update(make_user(9101), constants.MARRIAGE_TRIGGER)

    await family.marriage_text_handler(update, context)

    assert "ریپلای" in last_reply_text(tg)
    assert context.bot.send_message.await_count == 0


async def test_marriage_command_again_an_unregistered_player_is_safe(services, db, tg, context):
    await make_couple(services, db)
    update = make_message_update(
        make_user(9101), constants.MARRIAGE_TRIGGER, reply_to=make_user(999999, "غریبه")
    )

    await family.marriage_text_handler(update, context)

    assert "ثبت‌نام" in last_reply_text(tg)


async def test_accept_command_marries_both_players(services, db, tg, context):
    a, b = await make_couple(services, db)
    await services.family.create_request(proposer_player_id=a.player_id, target_player_id=b.player_id)

    update = make_message_update(make_user(9102, "سارا"), constants.MARRIAGE_ACCEPT_TRIGGER, chat=make_chat(9102, Chat.PRIVATE))
    await family.accept_marriage_handler(update, context)

    text = last_reply_text(tg)
    assert "تبریک" in text and "ثبت شد" in text
    assert await services.family.get_marriage(b.player_id) is not None


async def test_reject_command_closes_the_request(services, db, tg, context):
    a, b = await make_couple(services, db)
    await services.family.create_request(proposer_player_id=a.player_id, target_player_id=b.player_id)

    update = make_message_update(make_user(9102), constants.MARRIAGE_REJECT_TRIGGER, chat=make_chat(9102, Chat.PRIVATE))
    await family.reject_marriage_handler(update, context)

    assert "رد شد" in last_reply_text(tg)
    assert await services.family.get_pending_request_for(b.player_id) is None
    # The proposer is told privately.
    assert context.bot.send_message.await_args.kwargs["chat_id"] == 9101


async def test_accept_without_request_does_not_crash(services, db, tg, context):
    await make_couple(services, db)
    update = make_message_update(make_user(9102), constants.MARRIAGE_ACCEPT_TRIGGER, chat=make_chat(9102, Chat.PRIVATE))

    await family.accept_marriage_handler(update, context)

    assert "پاسخ" in last_reply_text(tg) or "درخواست" in last_reply_text(tg)


async def test_married_player_gets_the_already_married_message(services, db, tg, context):
    a, b = await make_couple(services, db)
    await services.family.create_request(proposer_player_id=a.player_id, target_player_id=b.player_id)
    await services.family.accept_request(b.player_id)

    update = make_message_update(
        make_user(9101), constants.MARRIAGE_TRIGGER, reply_to=make_user(9102, "سارا")
    )
    await family.marriage_text_handler(update, context)

    assert "متأهل" in last_reply_text(tg)


# === Divorce =================================================================


async def test_divorce_command_charges_mahriyeh(services, db, tg, context):
    a, b = await make_couple(services, db)
    result = await services.family.create_request(proposer_player_id=a.player_id, target_player_id=b.player_id)
    await services.family.accept_request(b.player_id)

    update = make_message_update(make_user(9101), constants.DIVORCE_TRIGGER, chat=make_chat(9101, Chat.PRIVATE))
    await family.divorce_handler(update, context)

    text = last_reply_text(tg)
    assert "تموم شد" in text
    assert f"{result.mahriyeh_amount:,}".replace(",", "٬") in text.replace("٬", "٬") or "مهریه" in text
    assert (await services.family.get_marriage(a.player_id)) is None


async def test_divorce_command_shows_the_missing_amount(services, db, tg, context):
    a, b = await make_couple(services, db)
    marriage = await services.family.create_request(proposer_player_id=a.player_id, target_player_id=b.player_id)
    await services.family.accept_request(b.player_id)
    # Drain the payer's wallet below the Mahriyeh.
    await services.money.remove_money(a.player_id, 80_000_000)

    update = make_message_update(make_user(9101), constants.DIVORCE_TRIGGER, chat=make_chat(9101, Chat.PRIVATE))
    await family.divorce_handler(update, context)

    text = last_reply_text(tg)
    assert "کافی نیست" in text
    assert "مبلغ لازم" in text and "موجودی تو" in text
    assert (await services.family.get_marriage(a.player_id)) is not None
    assert marriage is not None


async def test_divorce_command_for_a_single_player(services, db, tg, context):
    await make_couple(services, db)
    update = make_message_update(make_user(9101), constants.DIVORCE_TRIGGER, chat=make_chat(9101, Chat.PRIVATE))

    await family.divorce_handler(update, context)

    assert "متأهل نیستی" in last_reply_text(tg)


# === Cheating (must stay hidden) =============================================


async def test_cheating_is_answered_privately_in_a_group(services, db, tg, context):
    a, b = await make_couple(services, db)
    await services.family.create_request(proposer_player_id=a.player_id, target_player_id=b.player_id)
    await services.family.accept_request(b.player_id)
    services.family._roll = lambda: 0.99  # not discovered, but it happened

    group = make_chat(-100123, Chat.GROUP)
    update = make_message_update(make_user(9101), constants.CHEATING_TRIGGER, chat=group)
    await family.cheating_handler(update, context)

    # Nothing was said in the group thread; the answer went to a DM.
    tg.reply.assert_not_awaited()
    assert context.bot.send_message.await_args.kwargs["chat_id"] == 9101
    assert "🤫" not in context.bot.send_message.await_args.kwargs["text"]


async def test_cheating_discovery_notifies_the_spouse(services, db, tg, context):
    a, b = await make_couple(services, db)
    await services.family.create_request(proposer_player_id=a.player_id, target_player_id=b.player_id)
    await services.family.accept_request(b.player_id)
    services.family._roll = lambda: 0.0  # always discovered

    private = make_chat(9101, Chat.PRIVATE)
    update = make_message_update(make_user(9101), constants.CHEATING_TRIGGER, chat=private)
    await family.cheating_handler(update, context)

    assert "فاش شد" in last_reply_text(tg)
    # The spouse gets exactly one warning.
    assert context.bot.send_message.await_count == 1
    notify = context.bot.send_message.await_args.kwargs
    assert notify["chat_id"] == 9102 and "خیانت" in notify["text"]

    async with services.family._session_factory() as session:  # noqa: SLF001
        from sqlalchemy import select

        marriage = (await session.execute(select(Marriage))).scalars().one()
    assert marriage.cheating_strikes == 1


async def test_cheating_command_for_a_single_player(services, db, tg, context):
    await make_couple(services, db)
    private = make_chat(9101, Chat.PRIVATE)
    update = make_message_update(make_user(9101), constants.CHEATING_TRIGGER, chat=private)

    await family.cheating_handler(update, context)

    assert "متأهل نیستی" in last_reply_text(tg)


# === Relationship + birth announcement =======================================


async def test_relationship_command_on_spouse_reply(services, db, tg, context):
    a, b = await make_couple(services, db)
    await services.family.create_request(proposer_player_id=a.player_id, target_player_id=b.player_id)
    await services.family.accept_request(b.player_id)
    services.family._roll = lambda: 0.0  # pregnancy rolls under the chance

    update = make_message_update(
        make_user(9101, "امیر"),
        constants.RELATIONSHIP_TRIGGER,
        chat=make_chat(9101, Chat.PRIVATE),
        reply_to=make_user(9102, "سارا"),
    )
    await family.relationship_handler(update, context)

    text = last_reply_text(tg)
    assert "رابطه" in text or "💞" in text
    assert "بارداری" in text or "خبر بزرگ" in text


async def test_relationship_command_replying_to_a_stranger_is_refused(services, db, tg, context):
    a, b = await make_couple(services, db)
    await services.family.create_request(proposer_player_id=a.player_id, target_player_id=b.player_id)
    await services.family.accept_request(b.player_id)
    stranger = await services.players.register_or_get(
        telegram_user_id=9103, username="c", display_name="غریبه"
    )
    assert stranger.player_id is not None

    update = make_message_update(
        make_user(9101),
        constants.RELATIONSHIP_TRIGGER,
        chat=make_chat(9101, Chat.PRIVATE),
        reply_to=make_user(9103, "غریبه"),
    )
    await family.relationship_handler(update, context)

    assert "همسر" in last_reply_text(tg)


async def test_birth_is_announced_to_both_parents_privately(services, db, tg, context):
    a, b = await make_couple(services, db)
    await services.family.create_request(proposer_player_id=a.player_id, target_player_id=b.player_id)
    await services.family.accept_request(b.player_id)
    services.family._roll = lambda: 0.0
    await services.family.relationship(a.player_id)

    from sqlalchemy import select

    async with services.family._session_factory() as session:  # noqa: SLF001
        marriage = (await session.execute(select(Marriage))).scalars().one()
        from datetime import timedelta, timezone

        marriage.pregnant_due_at = datetime.now(timezone.utc) - timedelta(days=1)
        await session.commit()

    tg.send.reset_mock()
    update = make_message_update(make_user(9101), constants.FAMILY_TRIGGER, chat=make_chat(9101, Chat.PRIVATE))
    await family.family_info_handler(update, context)

    delivered = {call.kwargs["chat_id"] for call in context.bot.send_message.await_args_list}
    assert delivered == {9101, 9102}  # both parents told, nobody else
    # The congratulations are DMs (hidden by design); the family screen itself
    # reports the new child.
    notices = [c.kwargs["text"] for c in context.bot.send_message.await_args_list]
    assert all("تبریک" in text for text in notices)
    assert "تعداد فرزندان: ۱" in last_reply_text(tg)


# === Info screens ============================================================


async def test_family_info_command_reports_marriage(services, db, tg, context):
    a, b = await make_couple(services, db)
    await services.family.create_request(proposer_player_id=a.player_id, target_player_id=b.player_id)
    await services.family.accept_request(b.player_id)

    update = make_message_update(make_user(9101), constants.FAMILY_TRIGGER, chat=make_chat(9101, Chat.PRIVATE))
    await family.family_info_handler(update, context)

    text = last_reply_text(tg)
    for label in ("وضعیت ازدواج", "همسر", "تاریخ ازدواج", "تعداد فرزندان", "مهریه"):
        assert label in text, label
    assert "سارا" in text


async def test_children_and_history_commands(services, db, tg, context):
    a, b = await make_couple(services, db)
    await services.family.create_request(proposer_player_id=a.player_id, target_player_id=b.player_id)
    await services.family.accept_request(b.player_id)

    await family.children_handler(
        make_message_update(make_user(9101), constants.CHILDREN_TRIGGER, chat=make_chat(9101, Chat.PRIVATE)),
        context,
    )
    assert "فرزندنداری" in last_reply_text(tg)

    await family.family_history_handler(
        make_message_update(
            make_user(9101), constants.FAMILY_HISTORY_TRIGGER, chat=make_chat(9101, Chat.PRIVATE)
        ),
        context,
    )
    assert "تاریخچه" in last_reply_text(tg) and "ازدواج" in last_reply_text(tg)


async def test_help_command_lists_only_text_commands(services, db, tg, context):
    update = make_message_update(make_user(9101), constants.FAMILY_HELP_TRIGGER, chat=make_chat(9101, Chat.PRIVATE))

    await family.family_help_handler(update, context)

    text = last_reply_text(tg)
    assert constants.MARRIAGE_TRIGGER in text and constants.DIVORCE_TRIGGER in text
    assert "بدون منو" in text


async def test_unregistered_sender_is_redirected_to_start(services, db, tg, context):
    for handler, trigger in (
        (family.divorce_handler, constants.DIVORCE_TRIGGER),
        (family.family_info_handler, constants.FAMILY_TRIGGER),
        (family.relationship_handler, constants.RELATIONSHIP_TRIGGER),
        (family.marriage_text_handler, constants.MARRIAGE_TRIGGER),
    ):
        tg.reply.reset_mock()
        await handler(
            make_message_update(make_user(555555, "ناشناس"), trigger, chat=make_chat(555555, Chat.PRIVATE)),
            context,
        )
        assert "ثبت‌نام" in last_reply_text(tg), trigger


async def test_no_family_handler_returns_a_keyboard(services, db, tg, context):
    """Every family reply is plain text — reply_markup is never sent."""
    a, b = await make_couple(services, db)
    await services.family.create_request(proposer_player_id=a.player_id, target_player_id=b.player_id)
    await services.family.accept_request(b.player_id)

    for handler, trigger in (
        (family.family_info_handler, constants.FAMILY_TRIGGER),
        (family.children_handler, constants.CHILDREN_TRIGGER),
        (family.family_history_handler, constants.FAMILY_HISTORY_TRIGGER),
        (family.family_help_handler, constants.FAMILY_HELP_TRIGGER),
    ):
        await handler(
            make_message_update(make_user(9101), trigger, chat=make_chat(9101, Chat.PRIVATE)),
            context,
        )
        for call in tg.reply.await_args_list:
            assert "reply_markup" not in call.kwargs
            assert not isinstance(
                call.kwargs.get("reply_markup"), InlineKeyboardMarkup
            )


async def test_profile_screen_shows_the_family_block(services, db, monkeypatch):
    """The existing profile command gained marriage data — and nothing else."""
    a, b = await make_couple(services, db)
    await services.family.create_request(proposer_player_id=a.player_id, target_player_id=b.player_id)
    await services.family.accept_request(b.player_id)

    answer, edit = AsyncMock(), AsyncMock()
    monkeypatch.setattr("telegram.CallbackQuery.answer", answer)
    monkeypatch.setattr("telegram.CallbackQuery.edit_message_text", edit)
    from telegram import CallbackQuery

    query = CallbackQuery(id="p", from_user=make_user(9101), chat_instance="ci", data=callbacks.PROFILE)
    context = MagicMock()
    context.application.bot_data = {"services": services}

    await main_menu.show_profile(Update(update_id=1, callback_query=query), context)

    text = edit.await_args.kwargs["text"]
    assert "وضعیت ازدواج: متأهل" in text
    assert "همسر: سارا" in text
    assert "تاریخ ازدواج" in text
    assert "فرزندان" in text


async def test_marriage_note_after_the_trigger_is_kept(services, db, tg, context):
    """«ازدواج» plus a free-text note (even multi-line) still opens a request."""
    a, b = await make_couple(services, db)
    update = make_message_update(
        make_user(9101),
        f"{constants.MARRIAGE_TRIGGER}\nسلام، میشیم؟",
        chat=make_chat(-100999, Chat.GROUP),
        reply_to=make_user(9102, "سارا"),
    )

    await family.marriage_text_handler(update, context)

    pending = await services.family.get_pending_request_for(b.player_id)
    assert pending is not None
    assert pending.proposer_player_id == a.player_id
    assert "میشیم" in pending.message
