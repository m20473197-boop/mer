"""Telegram handlers for the predefined Business System."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.bot.context import get_services
from app.bot.keyboards import (
    build_back_to_main,
    build_business_list,
    build_business_menu,
    build_owned_businesses,
    callbacks,
)
from app.bot.messages import business as business_messages
from app.bot.messages import errors as error_messages
from app.core import constants
from app.game.shared.errors import DomainError, InsufficientFundsError
from app.services.business_service import (
    BusinessAlreadyOwnedError,
    BusinessInactiveError,
    BusinessLimitReachedError,
    BusinessNotFoundError,
    BusinessNotOwnedError,
    BusinessUnavailableError,
)

logger = logging.getLogger(__name__)

BUSINESS_TEXT_TRIGGERS: tuple[str, ...] = constants.BUSINESS_TEXT_TRIGGER_ALIASES
BUSINESS_TEXT_TRIGGER: str = constants.BUSINESS_TEXT_TRIGGER
BUSINESS_TEXT_PATTERN: str = "^(?:" + "|".join(BUSINESS_TEXT_TRIGGERS) + ")$"


async def _resolve_player_id(services, telegram_user_id: int) -> int | None:
    """Resolve Telegram identity through the PlayerService, not the database."""
    return await services.players.resolve_player_id(telegram_user_id)


async def _edit(query, text: str, markup=None) -> None:
    try:
        await query.edit_message_text(text=text, reply_markup=markup)
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise
        logger.debug("Ignored identical business-menu edit")


def _error_text(exc: DomainError) -> str:
    mapping = {
        BusinessNotFoundError: business_messages.business_not_found_text,
        BusinessUnavailableError: business_messages.business_unavailable_text,
        BusinessAlreadyOwnedError: business_messages.business_already_owned_text,
        BusinessLimitReachedError: business_messages.business_limit_text,
        BusinessNotOwnedError: business_messages.business_not_owned_text,
        BusinessInactiveError: business_messages.business_inactive_text,
        InsufficientFundsError: business_messages.business_insufficient_funds_text,
    }
    factory = mapping.get(type(exc))
    return factory() if factory else error_messages.GENERIC


async def business_text_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Open the business menu from the Persian text trigger."""
    if update.message is None or update.effective_user is None:
        return
    if (update.message.text or "").strip() not in BUSINESS_TEXT_TRIGGERS:
        return
    await update.message.reply_text(
        business_messages.business_menu_text(), reply_markup=build_business_menu()
    )


async def show_business_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.BUSINESS_MENU:
        return
    await query.answer()
    await _edit(query, business_messages.business_menu_text(), build_business_menu())


async def show_business_list(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.BUSINESS_LIST:
        return
    await query.answer()
    services = get_services(context)
    businesses = await services.businesses.get_available_businesses()
    await _edit(
        query,
        business_messages.business_list_text(businesses),
        build_business_list(businesses),
    )


async def show_owned_businesses(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.BUSINESS_MY:
        return
    await query.answer()

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        businesses = await services.businesses.get_owned_businesses(player_id)
        await _edit(
            query,
            business_messages.owned_businesses_text(businesses),
            build_owned_businesses(businesses),
        )
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_business_menu())
    except Exception as exc:  # noqa: BLE001 — Telegram must not leak tracebacks
        logger.error("show_owned_businesses failed", exc_info=exc)
        await _edit(query, error_messages.GENERIC, build_business_menu())


async def generate_business_income(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Generate today's balance credit for every owned active business."""
    query = update.callback_query
    if query is None or query.data != callbacks.BUSINESS_INCOME:
        return
    await query.answer()

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        results = await services.businesses.generate_all_daily_income(player_id)
        await _edit(
            query,
            business_messages.daily_income_text(results),
            build_business_menu(),
        )
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_business_menu())
    except Exception as exc:  # noqa: BLE001
        logger.error("generate_business_income failed", exc_info=exc)
        await _edit(query, error_messages.GENERIC, build_business_menu())


async def start_business_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Start only the catalog business named after the callback prefix."""
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.BUSINESS_START_PREFIX):
        return
    await query.answer()

    business_type = query.data[len(callbacks.BUSINESS_START_PREFIX) :]
    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        result = await services.businesses.start_business(player_id, business_type)
        await _edit(
            query,
            business_messages.business_started_text(result),
            build_business_menu(),
        )
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_business_list(
            await services.businesses.get_available_businesses()
        ))
    except Exception as exc:  # noqa: BLE001
        logger.error("start_business_callback failed", exc_info=exc)
        await _edit(query, error_messages.GENERIC, build_business_menu())
