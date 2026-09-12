"""Main-menu callback handlers: profile, status, back, unknown fallback."""

from __future__ import annotations

import logging

from telegram import CallbackQuery, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.bot.context import get_services
from app.bot.keyboards import build_back_to_main, build_main_menu, callbacks
from app.bot.messages import common, errors as message_errors
from app.bot.messages import player as player_messages

logger = logging.getLogger(__name__)


async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render the player's profile."""
    query = update.callback_query
    if query is None or query.data != callbacks.PROFILE:
        return
    await query.answer()

    services = get_services(context)
    profile = await services.players.get_profile(query.from_user.id)
    if profile is None:
        await _edit_safely(query, message_errors.NOT_REGISTERED, reply_markup=None)
        return

    await _edit_safely(
        query, player_messages.profile_text(profile), build_back_to_main()
    )


async def show_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render the player's basic game state."""
    query = update.callback_query
    if query is None or query.data != callbacks.STATUS:
        return
    await query.answer()

    services = get_services(context)
    status = await services.players.get_status(query.from_user.id)
    if status is None:
        await _edit_safely(query, message_errors.NOT_REGISTERED, reply_markup=None)
        return

    await _edit_safely(query, player_messages.status_text(status), build_back_to_main())


async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return to the main menu."""
    query = update.callback_query
    if query is None or query.data != callbacks.BACK_TO_MAIN:
        return
    await query.answer()
    await _edit_safely(query, common.MAIN_MENU, build_main_menu())


async def unknown_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fallback for stale or unknown callback data — never crash on it."""
    query = update.callback_query
    if query is None:
        return
    logger.warning("Unknown callback data received: %.100r", query.data)
    await query.answer(text=message_errors.UNKNOWN_ACTION, show_alert=True)


async def _edit_safely(
    query: CallbackQuery, text: str, reply_markup: object
) -> None:
    """Edit the menu message, tolerating harmless no-op edits."""
    try:
        await query.edit_message_text(text=text, reply_markup=reply_markup)
    except BadRequest as exc:
        # Editing to identical content is a normal UI race — ignore it.
        if "not modified" in str(exc).lower():
            logger.debug("Ignored identical message edit")
        else:
            raise
