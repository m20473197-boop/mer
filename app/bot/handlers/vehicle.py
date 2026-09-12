"""Telegram handlers for 🚗 نمایشگاه ماشین حاج ممد.

Handlers only translate Telegram callbacks into VehicleService calls. Model
ids, prices, ownership and wallet changes are all validated in the service.
"""

from __future__ import annotations

import logging
import re

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.bot.context import get_services
from app.bot.keyboards import (
    build_back_to_main,
    build_owned_vehicle_detail,
    build_owned_vehicles,
    build_vehicle_catalog,
    build_vehicle_confirmation,
    build_vehicle_menu,
    build_vehicle_model_detail,
    callbacks,
)
from app.bot.messages import errors as error_messages
from app.bot.messages import vehicle as vehicle_messages
from app.core import constants
from app.game.shared.errors import DomainError, InsufficientFundsError, PlayerNotFoundError
from app.services.vehicle_service import (
    VehicleAlreadyOwnedError,
    VehicleInvalidPriceError,
    VehicleModelNotFoundError,
    VehicleNotOwnedError,
    VehicleOwnershipLimitReachedError,
    VehiclePurchaseError,
    VehicleUnavailableError,
)

logger = logging.getLogger(__name__)

VEHICLE_TEXT_TRIGGERS: tuple[str, ...] = constants.VEHICLE_TEXT_TRIGGER_ALIASES
VEHICLE_TEXT_PATTERN: str = "^(?:" + "|".join(
    re.escape(item) for item in VEHICLE_TEXT_TRIGGERS
) + ")$"
_VEHICLE_PAGE_KEY: str = "vehicle_catalog_page"


async def _resolve_player_id(services, telegram_user_id: int) -> int | None:
    return await services.players.resolve_player_id(telegram_user_id)


async def _edit(query, text: str, markup=None) -> None:
    try:
        await query.edit_message_text(text=text, reply_markup=markup)
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise
        logger.debug("Ignored identical vehicle-dealership edit")


def _error_text(exc: DomainError) -> str:
    mapping = {
        VehicleModelNotFoundError: vehicle_messages.vehicle_model_not_found_text,
        VehicleUnavailableError: vehicle_messages.vehicle_unavailable_text,
        VehicleInvalidPriceError: vehicle_messages.vehicle_invalid_price_text,
        VehicleAlreadyOwnedError: vehicle_messages.vehicle_already_owned_text,
        VehicleOwnershipLimitReachedError: vehicle_messages.vehicle_limit_text,
        VehicleNotOwnedError: vehicle_messages.vehicle_not_owned_text,
        VehiclePurchaseError: vehicle_messages.vehicle_purchase_error_text,
        InsufficientFundsError: vehicle_messages.vehicle_insufficient_funds_text,
        PlayerNotFoundError: lambda: error_messages.NOT_REGISTERED,
    }
    factory = mapping.get(type(exc))
    return factory() if factory else error_messages.GENERIC


def _parse_positive_id(raw: str) -> int | None:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


async def vehicle_text_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Open the dealership from its Persian text trigger."""
    if update.message is None or update.effective_user is None:
        return
    if (update.message.text or "").strip() not in VEHICLE_TEXT_TRIGGERS:
        return
    await update.message.reply_text(
        vehicle_messages.vehicle_menu_text(), reply_markup=build_vehicle_menu()
    )


async def show_vehicle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.VEHICLE_MENU:
        return
    await query.answer()
    await _edit(query, vehicle_messages.vehicle_menu_text(), build_vehicle_menu())


async def _render_catalog(
    query, context: ContextTypes.DEFAULT_TYPE, *, page: int
) -> None:
    services = get_services(context)
    models = await services.vehicles.get_catalog(include_unavailable=True)
    safe_page = max(0, page)
    context.user_data[_VEHICLE_PAGE_KEY] = safe_page
    await _edit(
        query,
        vehicle_messages.vehicle_catalog_text(
            models, page=safe_page, page_size=constants.VEHICLE_PAGE_SIZE
        ),
        build_vehicle_catalog(
            models, page=safe_page, page_size=constants.VEHICLE_PAGE_SIZE
        ),
    )


async def show_vehicle_catalog(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.VEHICLE_CATALOG:
        return
    await query.answer()
    try:
        await _render_catalog(query, context, page=0)
    except Exception as exc:  # noqa: BLE001 — player must never see internals
        logger.error("Vehicle catalog screen failed: %s", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_vehicle_menu())


async def show_vehicle_catalog_page(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.VEHICLE_PAGE_PREFIX):
        return
    await query.answer()
    page = _parse_positive_id(query.data[len(callbacks.VEHICLE_PAGE_PREFIX) :])
    # Page zero is valid; malformed/negative values are rejected server-side.
    if page is None:
        raw = query.data[len(callbacks.VEHICLE_PAGE_PREFIX) :]
        if raw != "0":
            await _edit(query, error_messages.UNKNOWN_ACTION, build_vehicle_menu())
            return
        page = 0
    try:
        await _render_catalog(query, context, page=page)
    except Exception as exc:  # noqa: BLE001
        logger.error("Vehicle catalog pagination failed: %s", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_vehicle_menu())


async def show_vehicle_model(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.VEHICLE_MODEL_PREFIX):
        return
    await query.answer()
    model_id = _parse_positive_id(query.data[len(callbacks.VEHICLE_MODEL_PREFIX) :])
    if model_id is None:
        await _edit(query, error_messages.UNKNOWN_ACTION, build_vehicle_menu())
        return
    try:
        model = await get_services(context).vehicles.get_model(model_id)
        page = max(0, int(context.user_data.get(_VEHICLE_PAGE_KEY, 0)))
        await _edit(
            query,
            vehicle_messages.vehicle_model_detail_text(model),
            build_vehicle_model_detail(model, catalog_page=page),
        )
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_vehicle_menu())
    except Exception as exc:  # noqa: BLE001
        logger.error("Vehicle model detail failed: %s", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_vehicle_menu())


async def show_vehicle_confirmation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.VEHICLE_CONFIRM_PREFIX):
        return
    await query.answer()
    raw = query.data[len(callbacks.VEHICLE_CONFIRM_PREFIX) :]
    model_id = _parse_positive_id(raw)
    if model_id is None:
        # The execute callback contains :ok and is handled separately.
        return
    try:
        model = await get_services(context).vehicles.get_model(model_id)
        if not model.is_available:
            raise VehicleUnavailableError(model.name)
        await _edit(
            query,
            vehicle_messages.purchase_confirmation_text(model),
            build_vehicle_confirmation(model),
        )
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_vehicle_menu())
    except Exception as exc:  # noqa: BLE001
        logger.error("Vehicle purchase confirmation failed: %s", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_vehicle_menu())


async def confirm_vehicle_purchase(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.VEHICLE_CONFIRM_PREFIX):
        return
    await query.answer()
    raw = query.data[len(callbacks.VEHICLE_CONFIRM_PREFIX) :]
    if not raw.endswith(":ok"):
        return
    model_id = _parse_positive_id(raw[:-3])
    if model_id is None:
        await _edit(query, error_messages.UNKNOWN_ACTION, build_vehicle_menu())
        return
    services = get_services(context)
    try:
        player_id = await _resolve_player_id(services, query.from_user.id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Vehicle player resolution failed: %s", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_back_to_main())
        return
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return
    try:
        result = await services.vehicles.purchase(player_id, model_id)
        await _edit(
            query,
            vehicle_messages.purchase_success_text(result),
            build_vehicle_menu(),
        )
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_vehicle_menu())
    except Exception as exc:  # noqa: BLE001
        logger.error("Vehicle purchase failed: %s", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_vehicle_menu())


async def show_my_cars(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.VEHICLE_MY_CARS:
        return
    await query.answer()
    services = get_services(context)
    try:
        player_id = await _resolve_player_id(services, query.from_user.id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Vehicle player resolution failed: %s", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_back_to_main())
        return
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return
    try:
        vehicles = await services.vehicles.get_owned_vehicles(player_id)
        await _edit(
            query,
            vehicle_messages.my_cars_text(vehicles),
            build_owned_vehicles(vehicles),
        )
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_vehicle_menu())
    except Exception as exc:  # noqa: BLE001
        logger.error("Owned vehicles screen failed: %s", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_vehicle_menu())


async def show_owned_vehicle(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.VEHICLE_OWNED_PREFIX):
        return
    await query.answer()
    ownership_id = _parse_positive_id(query.data[len(callbacks.VEHICLE_OWNED_PREFIX) :])
    if ownership_id is None:
        await _edit(query, error_messages.UNKNOWN_ACTION, build_vehicle_menu())
        return
    services = get_services(context)
    try:
        player_id = await _resolve_player_id(services, query.from_user.id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Vehicle player resolution failed: %s", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_back_to_main())
        return
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return
    try:
        vehicle = await services.vehicles.get_owned_vehicle(player_id, ownership_id)
        await _edit(
            query,
            vehicle_messages.owned_vehicle_detail_text(vehicle),
            build_owned_vehicle_detail(),
        )
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_vehicle_menu())
    except Exception as exc:  # noqa: BLE001
        logger.error("Owned vehicle detail failed: %s", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_vehicle_menu())
