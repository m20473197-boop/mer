"""Lightweight update logging.

Privacy-aware by design: only the update type and the Telegram user id are
logged — never message content or other user data.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, ContextTypes, TypeHandler

logger = logging.getLogger(__name__)


async def log_update(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log every incoming update before any handler runs (group -1)."""
    if isinstance(update, Update):
        user = update.effective_user
        logger.debug(
            "Update received: type=%s user_id=%s",
            type(update).__name__,
            user.id if user is not None else None,
        )
    else:
        logger.debug("Update received: %s", type(update).__name__)


def register_middleware(application: Application) -> None:
    """Register middleware in group ``-1`` so it runs before all handlers."""
    application.add_handler(TypeHandler(Update, log_update), group=-1)
