"""Telegram handlers for the read-only/listing/purchase Divar UI.

Handlers translate Telegram events only. Ownership, search SQL, wallet
movement and sale transactions live in ``DivarService``.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import replace

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler

from app.bot.context import get_services
from app.bot.keyboards import (
    build_divar_categories,
    build_divar_city_filters,
    build_divar_filters,
    build_divar_listing_detail,
    build_divar_menu,
    build_divar_my_listings,
    build_divar_owned_assets,
    build_divar_results,
    callbacks,
)
from app.bot.messages import divar as messages
from app.bot.messages import errors as error_messages
from app.core import constants
from app.game.admin.parsing import parse_admin_float, parse_admin_int
from app.game.housing.catalog import CITY_BASE_PRICE_PER_SQM
from app.game.marketplace.catalog import ASSET_TYPE_CAR, ASSET_TYPE_HOUSE, ASSET_TYPE_LAND
from app.game.marketplace.dto import MarketplaceFilterState, MarketplaceSearchCriteria
from app.game.marketplace.search import (
    merge_search_with_filters,
    normalize_persian,
    parse_range_input,
    parse_search_query,
)
from app.game.shared.errors import DomainError, InsufficientFundsError, PlayerNotFoundError
from app.services.divar_service import (
    MarketplaceAssetNotFoundError,
    MarketplaceAssetNotOwnedError,
    MarketplaceAssetNotTransferableError,
    MarketplaceCannotBuyOwnListingError,
    MarketplaceInvalidPriceError,
    MarketplaceListingAlreadyExistsError,
    MarketplaceListingNotActiveError,
    MarketplaceListingNotFoundError,
    MarketplaceListingNotOwnerError,
)

logger = logging.getLogger(__name__)

DIVAR_INPUT_STATE: int = 1
_PENDING_KEY: str = "divar_pending_input"
_STATE_KEY: str = "divar_current_state"
_STATES_KEY: str = "divar_query_states"

DIVAR_TEXT_TRIGGERS: tuple[str, ...] = constants.DIVAR_TEXT_TRIGGER_ALIASES
DIVAR_TEXT_PATTERN: str = "^(?:" + "|".join(
    re.escape(item) for item in DIVAR_TEXT_TRIGGERS
) + ")$"


def _current_state(context: ContextTypes.DEFAULT_TYPE) -> MarketplaceFilterState:
    value = context.user_data.get(_STATE_KEY)
    if isinstance(value, MarketplaceFilterState):
        return value
    return MarketplaceFilterState()


def _set_state(context: ContextTypes.DEFAULT_TYPE, state: MarketplaceFilterState) -> None:
    context.user_data[_STATE_KEY] = state


def _save_state(context: ContextTypes.DEFAULT_TYPE, state: MarketplaceFilterState) -> str:
    token = uuid.uuid4().hex[:10]
    states = context.user_data.setdefault(_STATES_KEY, {})
    states[token] = state
    context.user_data[_STATE_KEY] = state
    context.user_data["divar_current_token"] = token
    while len(states) > constants.DIVAR_MAX_SEARCH_STATE_COUNT:
        states.pop(next(iter(states)))
    return token


def _state_for_token(
    context: ContextTypes.DEFAULT_TYPE, token: str
) -> MarketplaceFilterState:
    states = context.user_data.get(_STATES_KEY, {})
    state = states.get(token)
    if isinstance(state, MarketplaceFilterState):
        context.user_data[_STATE_KEY] = state
        context.user_data["divar_current_token"] = token
        return state
    return _current_state(context)


async def _player_id(services, telegram_user_id: int) -> int | None:
    return await services.players.resolve_player_id(telegram_user_id)


async def _edit(query, text: str, markup=None) -> None:
    try:
        await query.edit_message_text(text=text, reply_markup=markup)
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise
        logger.debug("Ignored identical Divar message edit")


def _error_text(exc: DomainError) -> str:
    mapping = {
        MarketplaceListingNotFoundError: messages.listing_not_found_text,
        MarketplaceListingNotActiveError: messages.listing_not_active_text,
        MarketplaceListingNotOwnerError: messages.listing_not_owner_text,
        MarketplaceAssetNotFoundError: messages.asset_not_found_text,
        MarketplaceAssetNotOwnedError: messages.asset_not_owned_text,
        MarketplaceAssetNotTransferableError: messages.asset_not_transferable_text,
        MarketplaceListingAlreadyExistsError: messages.listing_exists_text,
        MarketplaceInvalidPriceError: messages.invalid_price_text,
        MarketplaceCannotBuyOwnListingError: messages.own_listing_text,
        InsufficientFundsError: messages.insufficient_balance_text,
        PlayerNotFoundError: lambda: error_messages.NOT_REGISTERED,
    }
    factory = mapping.get(type(exc))
    return factory() if factory else error_messages.GENERIC


def _money_from_input(raw: str) -> int | None:
    integer = parse_admin_int(raw)
    if integer is not None and integer > 0:
        return integer
    value = parse_admin_float(raw)
    if value is None or value <= 0 or not value.is_integer():
        return None
    return int(value)


async def _render_results_message(
    services,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    state: MarketplaceFilterState,
    page: int,
    reply_target=None,
    edit_query=None,
    token: str | None = None,
) -> None:
    result = await services.divar.search(
        state.criteria, page=page, page_size=constants.DIVAR_PAGE_SIZE
    )
    context.user_data["divar_current_page"] = max(0, page)
    if token is None:
        token = _save_state(context, state)
    else:
        states = context.user_data.setdefault(_STATES_KEY, {})
        states[token] = state
        context.user_data[_STATE_KEY] = state
        context.user_data["divar_current_token"] = token
    text = messages.results_text(result, state)
    markup = build_divar_results(result, state_token=token)
    if edit_query is not None:
        await _edit(edit_query, text, markup)
    elif reply_target is not None:
        await reply_target.reply_text(text, reply_markup=markup)


# --- Entry screens ---------------------------------------------------------


async def divar_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    if (update.message.text or "").strip() not in DIVAR_TEXT_TRIGGERS:
        return
    await update.message.reply_text(messages.divar_menu_text(), reply_markup=build_divar_menu())


async def show_divar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.DIVAR_MENU:
        return
    await query.answer()
    await _edit(query, messages.divar_menu_text(), build_divar_menu())


async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.DIVAR_CATEGORIES:
        return
    await query.answer()
    await _edit(query, messages.categories_text(), build_divar_categories())


async def show_category_results(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.DIVAR_CATEGORY_PREFIX):
        return
    await query.answer()
    category = query.data[len(callbacks.DIVAR_CATEGORY_PREFIX) :]
    state = MarketplaceFilterState(
        criteria=MarketplaceSearchCriteria(asset_type=category)
    )
    try:
        await _render_results_message(
            get_services(context), context, state=state, page=0, edit_query=query
        )
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_divar_categories())
    except Exception as exc:  # noqa: BLE001
        logger.error("Divar category screen failed (%s)", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_divar_menu())


async def show_all_results(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.DIVAR_SHOW_ALL:
        return
    await query.answer()
    state = MarketplaceFilterState()
    try:
        await _render_results_message(
            get_services(context), context, state=state, page=0, edit_query=query
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Divar all-listings screen failed (%s)", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_divar_menu())


async def show_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.DIVAR_PAGE_PREFIX):
        return
    await query.answer()
    payload = query.data[len(callbacks.DIVAR_PAGE_PREFIX) :]
    token, _, raw_page = payload.rpartition("_")
    try:
        page = int(raw_page)
    except ValueError:
        await _edit(query, error_messages.UNKNOWN_ACTION, build_divar_menu())
        return
    state = _state_for_token(context, token)
    try:
        await _render_results_message(
            get_services(context),
            context,
            state=state,
            page=max(0, page),
            edit_query=query,
            token=token,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Divar pagination failed (%s)", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_divar_menu())


async def show_listing_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.DIVAR_DETAIL_PREFIX):
        return
    await query.answer()
    try:
        listing_id = int(query.data[len(callbacks.DIVAR_DETAIL_PREFIX) :])
    except ValueError:
        await _edit(query, error_messages.UNKNOWN_ACTION, build_divar_menu())
        return
    services = get_services(context)
    viewer_id = await _player_id(services, query.from_user.id)
    try:
        listing = await services.divar.get_listing(
            listing_id, viewer_player_id=viewer_id
        )
        token = context.user_data.get("divar_current_token")
        current_page = int(context.user_data.get("divar_current_page", 0))
        back_callback = callbacks.DIVAR_FILTERS
        if token:
            back_callback = f"{callbacks.DIVAR_PAGE_PREFIX}{token}_{current_page}"
        await _edit(
            query,
            messages.listing_detail_text(listing),
            build_divar_listing_detail(
                listing,
                viewer_player_id=viewer_id,
                back_callback_data=back_callback,
            ),
        )
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_divar_menu())
    except Exception as exc:  # noqa: BLE001
        logger.error("Divar listing detail failed (%s)", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_divar_menu())


async def show_my_listings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.DIVAR_MY_LISTINGS:
        return
    await query.answer()
    services = get_services(context)
    player_id = await _player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_divar_menu())
        return
    try:
        listings = await services.divar.list_my_listings(player_id)
        await _edit(
            query,
            messages.my_listings_text(listings),
            build_divar_my_listings(listings),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Divar own-listings screen failed (%s)", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_divar_menu())


async def show_owned_assets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.DIVAR_CREATE:
        return
    await query.answer()
    services = get_services(context)
    player_id = await _player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_divar_menu())
        return
    try:
        assets = await services.divar.get_owned_assets(player_id)
        await _edit(query, messages.owned_assets_text(assets), build_divar_owned_assets(assets))
    except Exception as exc:  # noqa: BLE001
        logger.error("Divar owned-assets screen failed (%s)", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_divar_menu())


# --- Filter UI -------------------------------------------------------------


async def show_filters(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.DIVAR_FILTERS:
        return
    await query.answer()
    await _edit(query, messages.filters_text(_current_state(context)), build_divar_filters(_current_state(context)))


async def show_city_filters(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    if query.data == callbacks.DIVAR_FILTER_CITY_MENU:
        await query.answer()
        await _edit(
            query,
            "📍 شهر را انتخاب کن:",
            build_divar_city_filters(list(CITY_BASE_PRICE_PER_SQM)),
        )
        return
    if not query.data.startswith(callbacks.DIVAR_FILTER_CITY_PREFIX):
        return
    await query.answer()
    raw = query.data[len(callbacks.DIVAR_FILTER_CITY_PREFIX) :]
    if raw == "all":
        city = None
    else:
        try:
            city = list(CITY_BASE_PRICE_PER_SQM)[int(raw)]
        except (ValueError, IndexError):
            await _edit(query, error_messages.UNKNOWN_ACTION, build_divar_filters(_current_state(context)))
            return
    state = _current_state(context)
    _set_state(context, replace(state, criteria=replace(state.criteria, city=city)))
    await _edit(query, messages.filters_text(_current_state(context)), build_divar_filters(_current_state(context)))


async def show_filter_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.DIVAR_FILTER_CATEGORY_PREFIX):
        return
    await query.answer()
    category = query.data[len(callbacks.DIVAR_FILTER_CATEGORY_PREFIX) :]
    if category not in (ASSET_TYPE_HOUSE, ASSET_TYPE_LAND, ASSET_TYPE_CAR):
        await _edit(query, error_messages.UNKNOWN_ACTION, build_divar_filters(_current_state(context)))
        return
    state = _current_state(context)
    _set_state(context, replace(state, criteria=replace(state.criteria, asset_type=category)))
    await _edit(query, messages.filters_text(_current_state(context)), build_divar_filters(_current_state(context)))


async def clear_filters(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.DIVAR_FILTER_CLEAR:
        return
    await query.answer()
    state = _current_state(context)
    _set_state(context, MarketplaceFilterState(search_query=state.search_query))
    await _edit(query, messages.filters_text(_current_state(context)), build_divar_filters(_current_state(context)))


async def apply_filters(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.DIVAR_FILTER_APPLY:
        return
    await query.answer()
    try:
        await _render_results_message(
            get_services(context), context, state=_current_state(context), page=0, edit_query=query
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Divar filter application failed (%s)", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_divar_menu())


# --- Input conversation ----------------------------------------------------


async def _start_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str, prompt: str
) -> int:
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    await query.answer()
    context.user_data[_PENDING_KEY] = {"mode": mode}
    await _edit(query, prompt, build_divar_input_cancel())
    return DIVAR_INPUT_STATE


async def start_search_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _start_input(update, context, "search", messages.search_prompt_text())


async def start_price_filter_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _start_input(update, context, "price_filter", messages.filter_prompt_text("price"))


async def start_area_filter_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _start_input(update, context, "area_filter", messages.filter_prompt_text("area"))


async def start_neighborhood_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _start_input(update, context, "neighborhood_filter", messages.filter_prompt_text("neighborhood"))


async def start_listing_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    data = query.data or ""
    if data.startswith(callbacks.DIVAR_SELL_HOUSE_PREFIX):
        asset_type = ASSET_TYPE_HOUSE
        raw_id = data[len(callbacks.DIVAR_SELL_HOUSE_PREFIX) :]
    elif data.startswith(callbacks.DIVAR_SELL_LAND_PREFIX):
        asset_type = ASSET_TYPE_LAND
        raw_id = data[len(callbacks.DIVAR_SELL_LAND_PREFIX) :]
    elif data.startswith(callbacks.DIVAR_SELL_CAR_PREFIX):
        asset_type = ASSET_TYPE_CAR
        raw_id = data[len(callbacks.DIVAR_SELL_CAR_PREFIX) :]
    else:
        return ConversationHandler.END
    try:
        asset_id = int(raw_id)
    except ValueError:
        await query.answer(text=messages.asset_not_found_text(), show_alert=True)
        return ConversationHandler.END
    await query.answer()
    services = get_services(context)
    player_id = await _player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_divar_menu())
        return ConversationHandler.END
    try:
        assets = await services.divar.get_owned_assets(player_id)
        selected = next(
            (asset for asset in assets if asset.asset_type == asset_type and asset.asset_id == asset_id),
            None,
        )
        if selected is None:
            raise MarketplaceAssetNotOwnedError(str(asset_id))
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_divar_menu())
        return ConversationHandler.END
    context.user_data[_PENDING_KEY] = {
        "mode": "listing_price",
        "asset_type": asset_type,
        "asset_id": asset_id,
        "label": selected.label,
    }
    await _edit(query, messages.price_prompt_text(selected.label), build_divar_input_cancel())
    return DIVAR_INPUT_STATE


async def input_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None or update.effective_user is None:
        return ConversationHandler.END
    pending = context.user_data.get(_PENDING_KEY, {})
    mode = pending.get("mode")
    raw = (update.message.text or "").strip()
    services = get_services(context)
    if not mode:
        return ConversationHandler.END

    if mode == "listing_price":
        price = _money_from_input(raw)
        if price is None:
            await update.message.reply_text(messages.invalid_price_text())
            return DIVAR_INPUT_STATE
        player_id = await _player_id(services, update.effective_user.id)
        if player_id is None:
            context.user_data.pop(_PENDING_KEY, None)
            await update.message.reply_text(error_messages.NOT_REGISTERED)
            return ConversationHandler.END
        try:
            result = await services.divar.create_listing(
                player_id,
                pending["asset_type"],
                int(pending["asset_id"]),
                price,
            )
            context.user_data.pop(_PENDING_KEY, None)
            await update.message.reply_text(
                messages.created_text(result.listing),
                reply_markup=build_divar_listing_detail(result.listing, viewer_player_id=player_id),
            )
            return ConversationHandler.END
        except DomainError as exc:
            await update.message.reply_text(_error_text(exc))
            context.user_data.pop(_PENDING_KEY, None)
            return ConversationHandler.END
        except Exception as exc:  # noqa: BLE001
            logger.error("Divar listing creation failed (%s)", type(exc).__name__)
            await update.message.reply_text(error_messages.GENERIC)
            context.user_data.pop(_PENDING_KEY, None)
            return ConversationHandler.END

    state = _current_state(context)
    if mode == "search":
        parsed = parse_search_query(raw)
        state = MarketplaceFilterState(
            criteria=merge_search_with_filters(state.criteria, parsed), search_query=raw
        )
    elif mode == "price_filter":
        low, high = parse_range_input(raw)
        if low is None:
            await update.message.reply_text(messages.filter_prompt_text("price"))
            return DIVAR_INPUT_STATE
        state = replace(
            state,
            criteria=replace(state.criteria, min_price=low, max_price=high),
        )
    elif mode == "area_filter":
        low, high = parse_range_input(raw)
        if low is None:
            await update.message.reply_text(messages.filter_prompt_text("area"))
            return DIVAR_INPUT_STATE
        state = replace(
            state,
            criteria=replace(state.criteria, min_area_sqm=low, max_area_sqm=high),
        )
    elif mode == "neighborhood_filter":
        neighborhood = normalize_persian(raw)
        parsed = parse_search_query(raw)
        if not neighborhood:
            await update.message.reply_text(messages.filter_prompt_text("neighborhood"))
            return DIVAR_INPUT_STATE
        state = replace(
            state,
            criteria=replace(
                state.criteria,
                neighborhood=parsed.neighborhood or raw.strip(),
                city=parsed.city or state.criteria.city,
            ),
        )
    else:
        context.user_data.pop(_PENDING_KEY, None)
        return ConversationHandler.END

    context.user_data.pop(_PENDING_KEY, None)
    _set_state(context, state)
    try:
        await _render_results_message(
            services, context, state=state, page=0, reply_target=update.message
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Divar text search/filter failed (%s)", type(exc).__name__)
        await update.message.reply_text(error_messages.GENERIC)
    return ConversationHandler.END


async def cancel_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    context.user_data.pop(_PENDING_KEY, None)
    if query is not None:
        await query.answer()
        await _edit(query, messages.input_cancelled_text(), build_divar_menu())
    return ConversationHandler.END


def build_divar_input_cancel():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ لغو", callback_data=callbacks.DIVAR_INPUT_CANCEL)]]
    )


# --- Purchase/cancellation -------------------------------------------------


async def buy_listing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.DIVAR_BUY_PREFIX):
        return
    await query.answer()
    try:
        listing_id = int(query.data[len(callbacks.DIVAR_BUY_PREFIX) :])
    except ValueError:
        await _edit(query, error_messages.UNKNOWN_ACTION, build_divar_menu())
        return
    services = get_services(context)
    buyer_id = await _player_id(services, query.from_user.id)
    if buyer_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_divar_menu())
        return
    try:
        result = await services.divar.purchase(buyer_id, listing_id)
        await _edit(
            query,
            messages.purchased_text(result),
            build_divar_menu(),
        )
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_divar_menu())
    except Exception as exc:  # noqa: BLE001
        logger.error("Divar purchase failed (%s)", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_divar_menu())


async def cancel_listing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.DIVAR_CANCEL_PREFIX):
        return
    await query.answer()
    try:
        listing_id = int(query.data[len(callbacks.DIVAR_CANCEL_PREFIX) :])
    except ValueError:
        await _edit(query, error_messages.UNKNOWN_ACTION, build_divar_menu())
        return
    services = get_services(context)
    seller_id = await _player_id(services, query.from_user.id)
    if seller_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_divar_menu())
        return
    try:
        result = await services.divar.cancel_listing(seller_id, listing_id)
        await _edit(query, messages.cancelled_text(result), build_divar_menu())
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_divar_menu())
    except Exception as exc:  # noqa: BLE001
        logger.error("Divar listing cancellation failed (%s)", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_divar_menu())
