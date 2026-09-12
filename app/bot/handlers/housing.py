"""Housing system handlers — menu, market, buying, selling, renting.

All business logic lives in HousingService; these handlers only translate
between Telegram objects and service calls, exactly like the job handlers.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.context import get_services
from app.bot.handlers.guards import requires_feature
from app.bot.keyboards import (
    build_back_to_main,
    build_buy_confirmation,
    build_house_info,
    build_housing_menu,
    build_market_list,
    build_my_houses,
    build_my_rents,
    build_rent_confirmation,
    build_rent_options,
    build_rentals_list,
    build_sale_price_options,
    callbacks,
)
from app.bot.messages import errors as error_messages
from app.bot.messages import housing as housing_messages
from app.game.shared.errors import (
    DomainError,
    InsufficientFundsError,
)
from app.services.housing_service import (
    AlreadyRentingError,
    CannotBuyOwnHouseError,
    CannotRentOwnHouseError,
    ContractNotFoundError,
    HouseAlreadyListedError,
    HouseNotAvailableError,
    HouseNotFoundError,
    HouseRentedOutError,
    NotContractPartyError,
    NotHouseOwnerError,
    NotListedForRentError,
    NotListedForSaleError,
    PriceOutOfBoundsError,
)

logger = logging.getLogger(__name__)

HOUSING_TEXT_TRIGGER = "خانه"
HOUSING_MENU_TEXT_TRIGGER = "مسکن"


async def _resolve_player_id(services, tg_id: int) -> int | None:
    """Map a Telegram user id to the internal player id (None if unregistered)."""
    from app.database.repositories.player_repository import PlayerRepository

    async with services.players._session_factory() as session:  # type: ignore[attr-defined]
        player = await PlayerRepository(session).get_by_telegram_user_id(tg_id)
        return player.id if player is not None else None


async def _edit(query, text: str, markup=None) -> None:
    """Edit a callback message, tolerating harmless no-op edits."""
    from telegram.error import BadRequest

    try:
        await query.edit_message_text(text=text, reply_markup=markup)
    except BadRequest as exc:
        if "not modified" in str(exc).lower():
            logger.debug("Ignored identical message edit")
        else:
            raise


def _parse_id(raw: str) -> int | None:
    try:
        return int(raw)
    except ValueError:
        return None


def _error_text(exc: DomainError) -> str:
    """Translate a housing domain error into its friendly Persian text."""
    mapping = {
        HouseNotFoundError: housing_messages.house_not_found_text,
        NotHouseOwnerError: housing_messages.not_owner_text,
        HouseNotAvailableError: housing_messages.house_not_available_text,
        NotListedForSaleError: housing_messages.not_listed_for_sale_text,
        NotListedForRentError: housing_messages.not_listed_for_rent_text,
        HouseAlreadyListedError: housing_messages.already_listed_text,
        HouseRentedOutError: housing_messages.rented_out_text,
        PriceOutOfBoundsError: housing_messages.price_out_of_bounds_text,
        CannotBuyOwnHouseError: housing_messages.cannot_buy_own_text,
        CannotRentOwnHouseError: housing_messages.cannot_rent_own_text,
        AlreadyRentingError: housing_messages.already_renting_text,
        ContractNotFoundError: housing_messages.contract_not_found_text,
        NotContractPartyError: housing_messages.not_contract_party_text,
        InsufficientFundsError: housing_messages.insufficient_funds_text,
    }
    factory = mapping.get(type(exc))
    return factory() if factory else error_messages.GENERIC


# --- Menu ------------------------------------------------------------------------


@requires_feature("housing")
async def show_housing_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.HOUSING_MENU:
        return
    await query.answer()
    await _edit(query, housing_messages.housing_menu_text(), build_housing_menu())


# --- Lists ------------------------------------------------------------------------


@requires_feature("housing")
async def show_my_houses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.HOUSES_MY:
        return
    await query.answer()

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    # Lazy completion: finish any construction/renovation that is due so the
    # asset screen always shows the current state.
    try:
        await services.realestate.settle_due()
    except Exception:  # noqa: BLE001 — settlement is best-effort here
        logger.warning("settle_due failed in show_my_houses", exc_info=True)

    try:
        assets = await services.housing.get_player_assets(player_id)
    except Exception as exc:
        logger.error("show_my_houses failed for %s", query.from_user.id, exc_info=exc)
        await _edit(query, error_messages.GENERIC, build_housing_menu())
        return

    await _edit(
        query,
        housing_messages.my_houses_text(assets),
        build_my_houses(assets),
    )


@requires_feature("housing")
async def show_market(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.HOUSES_MARKET:
        return
    await query.answer()

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    try:
        entries = await services.housing.get_available_houses_for_sale(player_id)
    except Exception as exc:
        logger.error("show_market failed for %s", query.from_user.id, exc_info=exc)
        await _edit(query, error_messages.GENERIC, build_housing_menu())
        return

    await _edit(query, housing_messages.market_text(entries), build_market_list(entries))


@requires_feature("housing")
async def show_rentals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.HOUSES_RENTALS:
        return
    await query.answer()

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    try:
        entries = await services.housing.get_available_rentals(player_id)
    except Exception as exc:
        logger.error("show_rentals failed for %s", query.from_user.id, exc_info=exc)
        await _edit(query, error_messages.GENERIC, build_housing_menu())
        return

    await _edit(query, housing_messages.rentals_text(entries), build_rentals_list(entries))


@requires_feature("housing")
async def show_my_rents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.HOUSES_MY_RENTS:
        return
    await query.answer()

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        contracts = await services.housing.get_my_rental_contracts(player_id)
    except Exception as exc:
        logger.error("show_my_rents failed for %s", query.from_user.id, exc_info=exc)
        await _edit(query, error_messages.GENERIC, build_housing_menu())
        return

    await _edit(
        query,
        housing_messages.my_rents_text(contracts),
        build_my_rents(contracts),
    )


# --- House information --------------------------------------------------------------


@requires_feature("housing")
async def show_house_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.HOUSE_INFO_PREFIX):
        return
    await query.answer()

    house_id = _parse_id(query.data[len(callbacks.HOUSE_INFO_PREFIX):])
    if house_id is None:
        await query.answer(text=housing_messages.house_not_found_text(), show_alert=True)
        return

    services = get_services(context)
    viewer_id = await _resolve_player_id(services, query.from_user.id)
    try:
        await services.realestate.settle_due()
    except Exception:  # noqa: BLE001 — settlement is best-effort here
        logger.warning("settle_due failed in show_house_info", exc_info=True)
    try:
        info = await services.housing.get_house_info(house_id, viewer_id)
    except HouseNotFoundError:
        await _edit(query, housing_messages.house_not_found_text(), build_housing_menu())
        return
    except Exception as exc:
        logger.error("show_house_info failed for %s", query.from_user.id, exc_info=exc)
        await _edit(query, error_messages.GENERIC, build_housing_menu())
        return

    await _edit(
        query,
        housing_messages.house_info_text(info),
        build_house_info(info, viewer_id),
    )


# --- Buying ---------------------------------------------------------------------------


@requires_feature("housing")
async def show_buy_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.HOUSE_BUY_PREFIX):
        return
    await query.answer()

    house_id = _parse_id(query.data[len(callbacks.HOUSE_BUY_PREFIX):])
    if house_id is None:
        return

    services = get_services(context)
    viewer_id = await _resolve_player_id(services, query.from_user.id)
    if viewer_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        info = await services.housing.get_house_info(house_id, viewer_id)
    except HouseNotFoundError:
        await _edit(query, housing_messages.house_not_found_text(), build_housing_menu())
        return

    await _edit(
        query,
        housing_messages.buy_confirmation_text(info),
        build_buy_confirmation(house_id),
    )


@requires_feature("housing")
async def confirm_buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Execute the purchase (market or player listing — service decides)."""
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.HOUSE_BUY_CONFIRM_PREFIX):
        return
    await query.answer()

    house_id = _parse_id(query.data[len(callbacks.HOUSE_BUY_CONFIRM_PREFIX):])
    if house_id is None:
        return

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        result = await services.housing.buy_from_player(player_id, house_id)
    except NotListedForSaleError:
        # Not a player listing — fall back to the system market purchase.
        try:
            result = await services.housing.buy_from_market(player_id, house_id)
        except DomainError as exc:
            await _edit(query, _error_text(exc), build_housing_menu())
            return
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_housing_menu())
        return
    except Exception as exc:
        logger.error("confirm_buy failed for %s", query.from_user.id, exc_info=exc)
        await _edit(query, error_messages.GENERIC, build_housing_menu())
        return

    await _edit(
        query,
        housing_messages.purchased_text(result),
        build_house_info(
            await services.housing.get_house_info(house_id, player_id), player_id
        ),
    )


# --- Selling (owner side) ---------------------------------------------------------------


@requires_feature("housing")
async def show_sale_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.HOUSE_SELL_OPTIONS_PREFIX):
        return
    await query.answer()

    house_id = _parse_id(query.data[len(callbacks.HOUSE_SELL_OPTIONS_PREFIX):])
    if house_id is None:
        return

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        options = await services.housing.get_sale_options(house_id, player_id)
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_housing_menu())
        return

    await _edit(
        query,
        housing_messages.sale_options_text(options),
        build_sale_price_options(options),
    )


@requires_feature("housing")
async def confirm_sell(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List the house at the chosen preset price (per-mille of market value)."""
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.HOUSE_SELL_SET_PREFIX):
        return
    await query.answer()

    payload = query.data[len(callbacks.HOUSE_SELL_SET_PREFIX):]
    try:
        house_str, per_mille_str = payload.rsplit("_", 1)
        house_id, per_mille = int(house_str), int(per_mille_str)
    except ValueError:
        await query.answer(text=housing_messages.house_not_found_text(), show_alert=True)
        return

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        options = await services.housing.get_sale_options(house_id, player_id)
        price = dict(options.price_options).get(per_mille)
        if price is None:
            await _edit(query, housing_messages.price_out_of_bounds_text(), build_housing_menu())
            return
        result = await services.housing.list_house_for_sale(player_id, house_id, price)
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_housing_menu())
        return
    except Exception as exc:
        logger.error("confirm_sell failed for %s", query.from_user.id, exc_info=exc)
        await _edit(query, error_messages.GENERIC, build_housing_menu())
        return

    await _edit(
        query,
        housing_messages.listed_for_sale_text(result),
        build_housing_menu(),
    )


@requires_feature("housing")
async def cancel_sale(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.HOUSE_SELL_CANCEL_PREFIX):
        return
    await query.answer()

    house_id = _parse_id(query.data[len(callbacks.HOUSE_SELL_CANCEL_PREFIX):])
    if house_id is None:
        return

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        await services.housing.cancel_sale_listing(player_id, house_id)
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_housing_menu())
        return
    except Exception as exc:
        logger.error("cancel_sale failed for %s", query.from_user.id, exc_info=exc)
        await _edit(query, error_messages.GENERIC, build_housing_menu())
        return

    info = await services.housing.get_house_info(house_id, player_id)
    await _edit(
        query,
        housing_messages.listing_cancelled_text("sale", info.house),
        build_house_info(info, player_id),
    )


# --- Renting out (owner side) --------------------------------------------------------------


@requires_feature("housing")
async def show_rentout_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.HOUSE_RENTOUT_OPTIONS_PREFIX):
        return
    await query.answer()

    house_id = _parse_id(query.data[len(callbacks.HOUSE_RENTOUT_OPTIONS_PREFIX):])
    if house_id is None:
        return

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        options = await services.housing.get_rent_options(house_id, player_id)
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_housing_menu())
        return

    await _edit(
        query,
        housing_messages.rent_options_text(options),
        build_rent_options(options),
    )


@requires_feature("housing")
async def confirm_rent_out(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List the house for rent with the chosen deposit preset."""
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.HOUSE_RENT_SET_PREFIX):
        return
    await query.answer()

    payload = query.data[len(callbacks.HOUSE_RENT_SET_PREFIX):]
    try:
        house_str, deposit_percent_str = payload.rsplit("_", 1)
        house_id, deposit_percent = int(house_str), int(deposit_percent_str)
    except ValueError:
        await query.answer(text=housing_messages.house_not_found_text(), show_alert=True)
        return

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        options = await services.housing.get_rent_options(house_id, player_id)
        match = next(
            (
                (deposit, rent)
                for percent, deposit, rent in options.options
                if percent == deposit_percent
            ),
            None,
        )
        if match is None:
            await _edit(query, housing_messages.price_out_of_bounds_text(), build_housing_menu())
            return
        deposit, monthly_rent = match
        result = await services.housing.list_house_for_rent(
            player_id, house_id, monthly_rent, deposit
        )
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_housing_menu())
        return
    except Exception as exc:
        logger.error("confirm_rent_out failed for %s", query.from_user.id, exc_info=exc)
        await _edit(query, error_messages.GENERIC, build_housing_menu())
        return

    await _edit(
        query,
        housing_messages.listed_for_rent_text(result),
        build_housing_menu(),
    )


@requires_feature("housing")
async def cancel_rent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.HOUSE_RENT_CANCEL_PREFIX):
        return
    await query.answer()

    house_id = _parse_id(query.data[len(callbacks.HOUSE_RENT_CANCEL_PREFIX):])
    if house_id is None:
        return

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        await services.housing.cancel_rent_listing(player_id, house_id)
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_housing_menu())
        return
    except Exception as exc:
        logger.error("cancel_rent failed for %s", query.from_user.id, exc_info=exc)
        await _edit(query, error_messages.GENERIC, build_housing_menu())
        return

    info = await services.housing.get_house_info(house_id, player_id)
    await _edit(
        query,
        housing_messages.listing_cancelled_text("rent", info.house),
        build_house_info(info, player_id),
    )


# --- Renting (tenant side) ------------------------------------------------------------------


@requires_feature("housing")
async def show_rent_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.RENT_CONFIRM_PREFIX):
        return
    await query.answer()

    house_id = _parse_id(query.data[len(callbacks.RENT_CONFIRM_PREFIX):])
    if house_id is None:
        return

    services = get_services(context)
    viewer_id = await _resolve_player_id(services, query.from_user.id)
    if viewer_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        rentals = await services.housing.get_available_rentals(viewer_id)
        entry = next((e for e in rentals if e.house.id == house_id), None)
        if entry is None:
            await _edit(query, housing_messages.not_listed_for_rent_text(), build_housing_menu())
            return
    except Exception as exc:
        logger.error("show_rent_confirmation failed for %s", query.from_user.id, exc_info=exc)
        await _edit(query, error_messages.GENERIC, build_housing_menu())
        return

    await _edit(
        query,
        housing_messages.rent_confirmation_text(entry),
        build_rent_confirmation(house_id),
    )


@requires_feature("housing")
async def confirm_rent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sign the rental contract (pays the deposit, creates the contract)."""
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.RENT_CONFIRM_PREFIX):
        return
    await query.answer()

    house_id = _parse_id(query.data[len(callbacks.RENT_CONFIRM_PREFIX):])
    if house_id is None:
        return

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        contract = await services.housing.rent_house(player_id, house_id)
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_housing_menu())
        return
    except Exception as exc:
        logger.error("confirm_rent failed for %s", query.from_user.id, exc_info=exc)
        await _edit(query, error_messages.GENERIC, build_housing_menu())
        return

    await _edit(
        query,
        (
            "🎉 قرارداد اجاره امضا شد!\n"
            "━━━━━━━━━━━━━━━\n"
            + housing_messages.contract_text(contract, viewer_is_tenant=True)
            + "\n\nاجاره ماهانه رو با دکمه «💵 پرداخت اجاره» پرداخت کن."
        ),
        build_my_rents([contract]),
    )


@requires_feature("housing")
async def pay_rent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.RENT_PAY_PREFIX):
        return
    await query.answer()

    contract_id = _parse_id(query.data[len(callbacks.RENT_PAY_PREFIX):])
    if contract_id is None:
        return

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        result = await services.housing.pay_rent(player_id, contract_id)
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_housing_menu())
        return
    except Exception as exc:
        logger.error("pay_rent failed for %s", query.from_user.id, exc_info=exc)
        await _edit(query, error_messages.GENERIC, build_housing_menu())
        return

    contracts = await services.housing.get_my_rental_contracts(player_id)
    await _edit(
        query,
        housing_messages.rent_paid_text(result),
        build_my_rents(contracts),
    )


@requires_feature("housing")
async def end_rent_contract(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.RENT_END_PREFIX):
        return
    await query.answer()

    contract_id = _parse_id(query.data[len(callbacks.RENT_END_PREFIX):])
    if contract_id is None:
        return

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        result = await services.housing.end_rental_contract(player_id, contract_id)
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_housing_menu())
        return
    except Exception as exc:
        logger.error("end_rent_contract failed for %s", query.from_user.id, exc_info=exc)
        await _edit(query, error_messages.GENERIC, build_housing_menu())
        return

    house = await services.housing.get_house(result.house_id)
    await _edit(
        query,
        housing_messages.contract_ended_text(result, housing_messages.house_card(house)),
        build_housing_menu(),
    )


# --- Text triggers ---------------------------------------------------------------------------


@requires_feature("housing")
async def housing_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle «خانه» / «مسکن» — open the housing menu."""
    if update.message is None or update.effective_user is None:
        return
    text = (update.message.text or "").strip()
    if text not in (HOUSING_TEXT_TRIGGER, HOUSING_MENU_TEXT_TRIGGER):
        return

    services = get_services(context)
    player_id = await _resolve_player_id(services, update.effective_user.id)
    if player_id is None:
        await update.message.reply_text(error_messages.NOT_REGISTERED)
        return

    await update.message.reply_text(
        text=housing_messages.housing_menu_text(),
        reply_markup=build_housing_menu(),
    )
