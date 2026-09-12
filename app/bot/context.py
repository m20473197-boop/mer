"""Access to application-wide dependencies inside handlers."""

from __future__ import annotations

from telegram.ext import ContextTypes

from app.services import ServiceRegistry


def get_services(context: ContextTypes.DEFAULT_TYPE) -> ServiceRegistry:
    """Fetch the service registry created at startup.

    Raises:
        RuntimeError: If the registry was never injected (startup bug).
    """
    services = context.application.bot_data.get("services")
    if services is None:
        raise RuntimeError("ServiceRegistry is not initialized in bot_data")
    return services
