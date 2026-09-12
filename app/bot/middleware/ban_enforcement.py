"""Ban enforcement — banned players are stopped before any handler runs.

Registered as a ``TypeHandler`` in group ``-2`` (before the activity logger
and every feature handler). When the author of a message / callback query is
banned, they get a short notice and ``ApplicationHandlerStop`` prevents any
later handler from processing the update.

Cost: admins skip the database entirely (bot_data lookup); everyone else
costs one indexed ``players`` row read, and unregistered users pass through
so ``/start`` keeps working.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, ApplicationHandlerStop, ContextTypes, TypeHandler

from app.bot.messages import admin as admin_messages
from app.game.admin import auth as admin_auth

logger = logging.getLogger(__name__)


async def enforce_ban(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stop banned users before any other handler sees the update."""
    if not isinstance(update, Update):
        return
    user = update.effective_user
    if user is None or user.is_bot:
        return
    if update.message is None and update.callback_query is None:
        return

    bot_data = context.application.bot_data
    services = bot_data.get("services")
    if services is None:  # pragma: no cover — startup always injects services
        return
    if admin_auth.is_admin(user.id, bot_data.get("admin_ids", ())):
        return

    try:
        banned = await services.admin.is_user_banned(user.id)
    except Exception:  # noqa: BLE001 — a DB hiccup must never lock users out
        logger.exception("Ban check failed for user %s", user.id)
        return
    if not banned:
        return

    logger.info("Blocked banned user %s", user.id)
    query = update.callback_query
    if query is not None:
        await query.answer(text=admin_messages.BANNED_TEXT, show_alert=True)
    if update.message is not None:
        await update.message.reply_text(admin_messages.BANNED_TEXT)
    raise ApplicationHandlerStop


def register_ban_enforcement(application: Application) -> None:
    """Register the guard in group ``-2`` so it runs before everything."""
    application.add_handler(TypeHandler(Update, enforce_ban), group=-2)
