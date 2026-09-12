"""/start — registration (idempotent) and the main menu."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.context import get_services
from app.bot.keyboards import build_main_menu
from app.bot.messages import player as player_messages

logger = logging.getLogger(__name__)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Register the player on first contact, then greet and show the menu."""
    if update.message is None or update.effective_user is None:
        return  # Not a normal user message — nothing to do.

    services = get_services(context)
    user = update.effective_user

    result = await services.players.register_or_get(
        telegram_user_id=user.id,
        username=user.username,
        display_name=user.full_name,
    )

    if result.created:
        text = player_messages.welcome_new_player(result.profile)
    else:
        text = player_messages.welcome_back_player(result.profile)

    await update.message.reply_text(text, reply_markup=build_main_menu())
