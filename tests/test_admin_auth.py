"""Admin authentication, input parsing, پنل access and the ban guard."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import CallbackQuery, Chat, Message, Update, User
from telegram.ext import ApplicationHandlerStop, ConversationHandler

from app.bot.handlers import admin_panel
from app.bot.keyboards import callbacks
from app.bot.middleware.ban_enforcement import enforce_ban
from app.core import constants
from app.game.admin import auth as admin_auth
from app.game.admin.parsing import parse_admin_float, parse_admin_int

ADMIN_ID = 8154313073


def make_user(tg_id: int) -> User:
    return User(id=tg_id, first_name="Test", is_bot=False, username="test")


def make_message_update(user: User, text: str = "پنل") -> Update:
    message = Message(
        message_id=1, date=datetime.now(), chat=Chat(id=user.id, type=Chat.PRIVATE),
        from_user=user, text=text,
    )
    return Update(update_id=1, message=message)


def make_query(user: User, data: str) -> CallbackQuery:
    return CallbackQuery(id="q", from_user=user, chat_instance="ci", data=data)


def make_context(services, admin_ids=(ADMIN_ID,)) -> MagicMock:
    context = MagicMock()
    context.application.bot_data = {"services": services, "admin_ids": admin_ids}
    context.user_data = {}
    return context


# --- is_admin --------------------------------------------------------------------

def test_owner_id_is_admin():
    assert admin_auth.is_admin(ADMIN_ID, (ADMIN_ID,)) is True
    assert admin_auth.is_admin(ADMIN_ID, constants.ADMIN_TELEGRAM_IDS) is True


def test_other_users_are_blocked():
    assert admin_auth.is_admin(123456789, (ADMIN_ID,)) is False
    assert admin_auth.is_admin(ADMIN_ID, ()) is False
    assert admin_auth.is_admin(ADMIN_ID, None) is False


def test_is_admin_rejects_garbage():
    assert admin_auth.is_admin(None, (ADMIN_ID,)) is False
    assert admin_auth.is_admin("not-an-int", (ADMIN_ID,)) is False
    assert admin_auth.is_admin(ADMIN_ID, ("junk",)) is False


def test_config_falls_back_to_owner_id(tmp_path, monkeypatch):
    from app.core.config import load_settings

    monkeypatch.setenv("BOT_TOKEN", "123456:ABC-test")
    monkeypatch.delenv("ADMIN_IDS", raising=False)
    settings = load_settings(env_file=tmp_path / "nonexistent.env")
    assert ADMIN_ID in settings.admin_ids


# --- Parsing ---------------------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1000", 1000),
        ("۱٬۵۰۰٬۰۰۰", 1_500_000),
        ("1,000", 1000),
        ("10m", 10_000_000),
        ("۱۰ میلیون", 10_000_000),
        ("2k", 2000),
        ("۵ هزار", 5000),
        ("1b", 1_000_000_000),
        ("۰", 0),
    ],
)
def test_parse_admin_int_accepts_persian_and_suffixes(raw, expected):
    assert parse_admin_int(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "12.5", "۱.۵m تومان اضافه", "--5"])
def test_parse_admin_int_rejects_garbage(raw):
    assert parse_admin_int(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.2", 1.2),
        ("۱/۲", 1.2),
        ("12%", 12.0),
        ("٪۱۲", 12.0),
        ("0.1", 0.1),
    ],
)
def test_parse_admin_float(raw, expected):
    assert parse_admin_float(raw) == pytest.approx(expected)


def test_parse_admin_float_rejects_garbage():
    assert parse_admin_float("abc") is None
    assert parse_admin_float("") is None


# --- پنل trigger --------------------------------------------------------------------

async def test_admin_command_opens_panel_for_admin(services, monkeypatch):
    reply_mock = AsyncMock()
    monkeypatch.setattr(Message, "reply_text", reply_mock)

    result = await admin_panel.admin_command(
        make_message_update(make_user(ADMIN_ID)), make_context(services)
    )

    assert result == ConversationHandler.END
    reply_mock.assert_awaited_once()
    assert "پنل مدیریت" in reply_mock.await_args.args[0]
    markup = reply_mock.await_args.kwargs["reply_markup"]
    data = {b.callback_data for row in markup.inline_keyboard for b in row}
    assert callbacks.ADM_DASH in data
    assert callbacks.ADM_ECON in data
    assert callbacks.ADM_SETTINGS in data


async def test_admin_command_blocks_non_admin(services, monkeypatch):
    reply_mock = AsyncMock()
    monkeypatch.setattr(Message, "reply_text", reply_mock)

    result = await admin_panel.admin_command(
        make_message_update(make_user(999)), make_context(services)
    )

    assert result == ConversationHandler.END
    assert "ادمین" in reply_mock.await_args.args[0]


def _panel_opener():
    """Return the registered handler that opens the admin panel."""
    from telegram.ext import ApplicationBuilder, MessageHandler

    from app.bot.handlers import register_handlers

    application = ApplicationBuilder().token("123456:ABC-test").build()
    register_handlers(application)
    for handler in application.handlers[0]:
        if (
            isinstance(handler, MessageHandler)
            and handler.callback is admin_panel.admin_command
        ):
            return handler
    raise AssertionError("no registered handler opens the admin panel")


async def test_panel_text_trigger_opens_panel_for_admin(services, monkeypatch):
    reply_mock = AsyncMock()
    monkeypatch.setattr(Message, "reply_text", reply_mock)

    opener = _panel_opener()
    update = make_message_update(make_user(ADMIN_ID), text="پنل")
    assert opener.check_update(update)

    result = await opener.callback(update, make_context(services))

    assert result == ConversationHandler.END
    assert "پنل مدیریت" in reply_mock.await_args.args[0]


async def test_panel_text_trigger_blocks_normal_user(services, monkeypatch):
    reply_mock = AsyncMock()
    monkeypatch.setattr(Message, "reply_text", reply_mock)

    opener = _panel_opener()
    update = make_message_update(make_user(999), text="پنل")
    assert opener.check_update(update)

    result = await opener.callback(update, make_context(services))

    assert result == ConversationHandler.END
    assert "ادمین" in reply_mock.await_args.args[0]


async def test_old_admin_slash_command_is_gone():
    from telegram.ext import ApplicationBuilder, CommandHandler

    from app.bot.handlers import register_handlers

    application = ApplicationBuilder().token("123456:ABC-test").build()
    register_handlers(application)
    for handler in application.handlers[0]:
        if isinstance(handler, CommandHandler):
            assert "admin" not in handler.commands


async def test_admin_router_blocks_non_admin(services, monkeypatch):
    answer_mock, edit_mock = AsyncMock(), AsyncMock()
    monkeypatch.setattr(CallbackQuery, "answer", answer_mock)
    monkeypatch.setattr(CallbackQuery, "edit_message_text", edit_mock)

    result = await admin_panel.admin_callback(
        Update(update_id=1, callback_query=make_query(make_user(999), "adm_dash")),
        make_context(services),
    )

    assert result == ConversationHandler.END
    assert "ادمین" in answer_mock.await_args.kwargs["text"]
    edit_mock.assert_not_awaited()


async def test_admin_input_entry_blocks_non_admin(services, monkeypatch):
    answer_mock = AsyncMock()
    monkeypatch.setattr(CallbackQuery, "answer", answer_mock)

    result = await admin_panel.admin_input_entry(
        Update(update_id=1, callback_query=make_query(make_user(999), "adm_in_mkt")),
        make_context(services),
    )

    assert result == ConversationHandler.END
    answer_mock.assert_awaited_once()


async def test_admin_input_received_blocks_non_admin(services, monkeypatch):
    reply_mock = AsyncMock()
    monkeypatch.setattr(Message, "reply_text", reply_mock)
    context = make_context(services)
    context.user_data[admin_panel.PENDING_KEY] = {"code": "mkt"}

    result = await admin_panel.admin_input_received(
        make_message_update(make_user(999), "1.5"), context
    )

    assert result == ConversationHandler.END
    assert "ادمین" in reply_mock.await_args.args[0]


# --- Ban guard ---------------------------------------------------------------------

async def test_ban_guard_stops_banned_users(services, register, monkeypatch):
    reply_mock = AsyncMock()
    monkeypatch.setattr(Message, "reply_text", reply_mock)
    target = await register(tg_id=6101)
    await services.admin.ban_user(ADMIN_ID, target.player_id)

    with pytest.raises(ApplicationHandlerStop):
        await enforce_ban(
            make_message_update(make_user(6101), "خانه"), make_context(services)
        )
    assert "مسدود" in reply_mock.await_args.args[0]


async def test_ban_guard_passes_regular_users(services, register):
    await register(tg_id=6102)
    # No exception → the update continues to normal handlers.
    await enforce_ban(
        make_message_update(make_user(6102), "خانه"), make_context(services)
    )


async def test_ban_guard_passes_unregistered_users(services):
    await enforce_ban(
        make_message_update(make_user(6103), "/start"), make_context(services)
    )


async def test_ban_guard_answers_banned_callbacks(services, register, monkeypatch):
    answer_mock = AsyncMock()
    monkeypatch.setattr(CallbackQuery, "answer", answer_mock)
    target = await register(tg_id=6104)
    await services.admin.ban_user(ADMIN_ID, target.player_id)

    with pytest.raises(ApplicationHandlerStop):
        await enforce_ban(
            Update(
                update_id=1,
                callback_query=make_query(make_user(6104), "profile"),
            ),
            make_context(services),
        )
    assert "مسدود" in answer_mock.await_args.kwargs["text"]
