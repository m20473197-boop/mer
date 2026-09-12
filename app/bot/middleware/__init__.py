"""Cross-cutting middleware applied to every update."""

from telegram.ext import Application

from app.bot.middleware.activity_logging import (
    register_middleware as register_activity_logging,
)
from app.bot.middleware.ban_enforcement import register_ban_enforcement


def register_middleware(application: Application) -> None:
    """Register all middleware (ban guard first, then activity logging)."""
    register_ban_enforcement(application)
    register_activity_logging(application)


__all__ = ["register_middleware"]
