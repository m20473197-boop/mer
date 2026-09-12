"""Global error handler.

Logs everything (with traceback, in the logs only) and shows the player a
friendly Persian message. Normal user-interaction errors must never crash
the bot and must never leak internals to the chat.
"""

from __future__ import annotations

import logging

from sqlalchemy.exc import SQLAlchemyError
from telegram import Update
from telegram.ext import ContextTypes

from app.bot.messages import errors as message_errors

logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Top-level safety net for every handler exception."""
    error = context.error
    if error is None:
        logger.warning("Error handler triggered without an exception attached")
        return

    if isinstance(error, SQLAlchemyError):
        logger.error("Database error while processing an update", exc_info=error)
        text = message_errors.DATABASE
    else:
        logger.error("Unexpected exception while processing an update", exc_info=error)
        text = message_errors.GENERIC

    try:
        await _notify_user(update, context, text)
    except Exception:  # noqa: BLE001 — notifying the user must never raise
        logger.warning("Could not deliver the error message to the user", exc_info=True)


async def _notify_user(
    update: object, context: ContextTypes.DEFAULT_TYPE, text: str
) -> None:
    """Best-effort friendly notification depending on the update kind."""
    if not isinstance(update, Update):
        return
    if update.callback_query is not None:
        await update.callback_query.answer(text=text, show_alert=True)
    elif update.effective_chat is not None:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
