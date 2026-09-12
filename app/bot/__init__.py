"""Bot layer: handlers, keyboards, messages and middleware (Telegram only)."""

from __future__ import annotations

from telegram.ext import Application

from app.bot import handlers, middleware


def setup_bot(application: Application) -> None:
    """Attach middleware, route handlers and the error handler to the app."""
    middleware.register_middleware(application)
    handlers.register_handlers(application)


__all__ = ["setup_bot"]
