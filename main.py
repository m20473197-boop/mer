"""Iran Life Bot — entry point.

Startup order:
1. Load configuration (fail fast and clearly if BOT_TOKEN is missing).
2. Set up secret-safe logging.
3. Build the Telegram application with services + database in ``bot_data``.
4. Initialize the database (create missing tables only — data is kept).
5. Start polling.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, ApplicationBuilder

from app.bot import setup_bot
from app.core.config import ConfigError, Settings, load_settings
from app.core.logging import setup_logging
from app.database.database import Database
from app.services import ServiceRegistry

logger = logging.getLogger("main")


def build_application(
    settings: Settings, database: Database, services: ServiceRegistry
) -> Application:
    """Assemble the PTB application with its lifecycle hooks and handlers."""

    async def on_startup(application: Application) -> None:
        await database.create_all()
        logger.info("Database initialized (missing tables created, data kept)")
        # Initialize the four-asset Iranian market and make one automatic
        # first-data attempt. The recurring scheduler is independent of the
        # Telegram handlers and uses the persisted three-day cursor.
        try:
            market_result = await services.market.ensure_initial_state()
            if market_result is not None:
                logger.info(
                    "Iran market initial attempt: successful=%s attempted=%s",
                    market_result.successful,
                    market_result.attempted,
                )
        except Exception as exc:
            logger.warning("Could not initialize the Iran market: %s", type(exc).__name__)
        services.market.start_scheduler()
        # Seed initial jobs for Job and Income System
        try:
            jobs = await services.jobs.ensure_initial_jobs()
            logger.info("Initial jobs ensured: %s jobs active", len(jobs))
        except Exception as exc:
            logger.warning("Could not seed initial jobs: %s", exc)
        # Seed the starter houses for the Housing system
        try:
            houses = await services.housing.ensure_initial_houses()
            logger.info("Initial houses ensured: %s houses on the market", len(houses))
        except Exception as exc:
            logger.warning("Could not seed initial houses: %s", exc)
        # Seed the starter lands for the Land/Construction system
        try:
            lands = await services.realestate.ensure_initial_lands()
            logger.info("Initial lands ensured: %s lands on the market", len(lands))
        except Exception as exc:
            logger.warning("Could not seed initial lands: %s", exc)
        # Seed the fixed حاج ممد vehicle catalog. Existing model rows are
        # preserved so future configured prices/availability survive restarts.
        try:
            vehicles = await services.vehicles.ensure_catalog()
            logger.info("Vehicle catalog ensured: %s models", len(vehicles))
        except Exception as exc:
            logger.warning("Could not seed the vehicle catalog: %s", type(exc).__name__)
        # Seed the admin-panel economy catalog and refresh the runtime cache
        # (market conditions, inflation, events, reward settings, flags).
        try:
            await services.admin.ensure_economy_seeded()
            factor = await services.admin.refresh_runtime()
            logger.info("Economy ensured (effective market factor %.4f)", factor)
        except Exception as exc:
            logger.warning("Could not seed the economy catalog: %s", exc)

    async def on_shutdown(application: Application) -> None:
        await services.market.stop_scheduler()
        await database.dispose()
        logger.info("Database connections closed — bot shut down")

    application = (
        ApplicationBuilder()
        .token(settings.bot_token)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )

    application.bot_data["database"] = database
    application.bot_data["services"] = services
    application.bot_data["admin_ids"] = settings.admin_ids
    services.attach_database(database)
    services.admin.set_admin_ids(settings.admin_ids)
    setup_bot(application)
    return application


def main() -> None:
    try:
        settings = load_settings()
    except ConfigError as exc:
        # No token — nothing sensible can run. Fail clearly (no secrets here).
        raise SystemExit(f"[config] {exc}") from exc

    setup_logging(settings.log_level, secrets=(settings.bot_token,))
    logger.info("Starting Iran Life Bot ...")

    database = Database(settings.database_url)
    services = ServiceRegistry(database.session_factory)
    application = build_application(settings, database, services)

    logger.info("Bot is up — starting polling")
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as exc:
        # e.g. an invalid token: PTB embeds the token in its error message,
        # so the exception is logged (secret-redacted) instead of letting the
        # interpreter print it raw with the token inside.
        logger.error("Bot terminated with an error: %s", exc)
        raise SystemExit(1) from None
    logger.info("Iran Life Bot stopped")


if __name__ == "__main__":
    main()
