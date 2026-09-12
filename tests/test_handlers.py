"""Handler-level integration tests (Telegram layer simulated, real services).

The Telegram API is not reachable in tests, so the PTB Update/Context objects
are simulated and the handlers are invoked directly — but the full real
service/repository/database stack runs underneath.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select
from telegram import (
    CallbackQuery,
    Chat,
    InlineKeyboardMarkup,
    Message,
    Update,
    User,
)

from app.bot.handlers import main_menu, start
from app.bot.keyboards import callbacks
from app.database.models.player import Player


# --- Telegram-object simulation helpers -------------------------------------


def make_user(tg_id: int, first_name: str = "علی", username: str | None = "ali") -> User:
    return User(id=tg_id, first_name=first_name, is_bot=False, username=username)


def make_update_message(user: User, text: str = "/start") -> Update:
    message = Message(
        message_id=1,
        date=datetime.now(),
        chat=Chat(id=user.id, type=Chat.PRIVATE),
        from_user=user,
        text=text,
    )
    return Update(update_id=1, message=message)


def make_context(services) -> MagicMock:
    context = MagicMock()
    context.application.bot_data = {"services": services}
    return context


# --- /start ------------------------------------------------------------------


async def test_start_registers_player_and_shows_main_menu(
    services, db, monkeypatch
):
    reply_mock = AsyncMock()
    monkeypatch.setattr(Message, "reply_text", reply_mock)

    update = make_update_message(make_user(7001))
    await start.start_handler(update, make_context(services))

    reply_mock.assert_awaited_once()
    text = reply_mock.await_args.args[0]
    assert "خوش اومدی" in text  # friendly Persian welcome

    markup = reply_mock.await_args.kwargs["reply_markup"]
    assert isinstance(markup, InlineKeyboardMarkup)
    callback_data = {b.callback_data for row in markup.inline_keyboard for b in row}
    assert callbacks.PROFILE in callback_data
    assert callbacks.STATUS in callback_data

    # The player really exists in the database with the starting values.
    profile = await services.players.get_profile(7001)
    assert profile is not None
    assert (profile.level, profile.xp, profile.money) == (1, 0, 0)


async def test_second_start_reuses_player_and_does_not_duplicate(
    services, db, monkeypatch
):
    reply_mock = AsyncMock()
    monkeypatch.setattr(Message, "reply_text", reply_mock)
    user = make_user(7002)

    await start.start_handler(make_update_message(user), make_context(services))
    await start.start_handler(make_update_message(user), make_context(services))

    assert reply_mock.await_count == 2
    second_text = reply_mock.await_args_list[1].args[0]
    assert "خوش برگشتی" in second_text  # returning-player greeting

    async with db.session_factory() as session:
        rows = (await session.execute(select(Player))).scalars().all()
    assert len(rows) == 1  # exactly one profile for one Telegram user


# --- Profile / Status / Back callbacks ----------------------------------------


async def test_profile_callback_renders_profile(services, register, monkeypatch):
    await register(tg_id=7003)
    answer_mock, edit_mock = AsyncMock(), AsyncMock()
    monkeypatch.setattr(CallbackQuery, "answer", answer_mock)
    monkeypatch.setattr(CallbackQuery, "edit_message_text", edit_mock)

    query = CallbackQuery(
        id="q1", from_user=make_user(7003), chat_instance="ci", data="profile"
    )
    await main_menu.show_profile(
        Update(update_id=1, callback_query=query), make_context(services)
    )

    answer_mock.assert_awaited_once()
    text = edit_mock.await_args.kwargs["text"]
    assert "پروفایل" in text
    assert "لول" in text and "موجودی" in text
    markup = edit_mock.await_args.kwargs["reply_markup"]
    assert (
        callbacks.BACK_TO_MAIN
        in {b.callback_data for row in markup.inline_keyboard for b in row}
    )


async def test_status_callback_renders_status(services, register, monkeypatch):
    await register(tg_id=7004)
    answer_mock, edit_mock = AsyncMock(), AsyncMock()
    monkeypatch.setattr(CallbackQuery, "answer", answer_mock)
    monkeypatch.setattr(CallbackQuery, "edit_message_text", edit_mock)

    query = CallbackQuery(
        id="q2", from_user=make_user(7004), chat_instance="ci", data="status"
    )
    await main_menu.show_status(
        Update(update_id=1, callback_query=query), make_context(services)
    )

    text = edit_mock.await_args.kwargs["text"]
    assert "وضعیت" in text
    assert "لول" in text and "XP" in text and "تومان" in text


async def test_back_to_main_callback_restores_menu(services, monkeypatch):
    answer_mock, edit_mock = AsyncMock(), AsyncMock()
    monkeypatch.setattr(CallbackQuery, "answer", answer_mock)
    monkeypatch.setattr(CallbackQuery, "edit_message_text", edit_mock)

    query = CallbackQuery(
        id="q3", from_user=make_user(7005), chat_instance="ci", data="back_main"
    )
    await main_menu.back_to_main(
        Update(update_id=1, callback_query=query), make_context(services)
    )

    markup = edit_mock.await_args.kwargs["reply_markup"]
    data = {b.callback_data for row in markup.inline_keyboard for b in row}
    assert {callbacks.PROFILE, callbacks.STATUS} <= data


async def test_unknown_callback_gets_friendly_alert(services, monkeypatch):
    answer_mock = AsyncMock()
    monkeypatch.setattr(CallbackQuery, "answer", answer_mock)

    query = CallbackQuery(
        id="q4", from_user=make_user(7006), chat_instance="ci", data="hack_the_bot"
    )
    await main_menu.unknown_callback(
        Update(update_id=1, callback_query=query), make_context(services)
    )

    answer_mock.assert_awaited_once()
    assert "نمی‌شناسم" in answer_mock.await_args.kwargs["text"]
    assert answer_mock.await_args.kwargs["show_alert"] is True


async def test_profile_callback_for_unregistered_user_is_safe(
    services, monkeypatch
):
    answer_mock, edit_mock = AsyncMock(), AsyncMock()
    monkeypatch.setattr(CallbackQuery, "answer", answer_mock)
    monkeypatch.setattr(CallbackQuery, "edit_message_text", edit_mock)

    query = CallbackQuery(
        id="q5", from_user=make_user(7007), chat_instance="ci", data="profile"
    )
    await main_menu.show_profile(
        Update(update_id=1, callback_query=query), make_context(services)
    )

    text = edit_mock.await_args.kwargs["text"]
    assert "ثبت‌نام" in text  # friendly guidance instead of a crash
