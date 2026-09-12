"""Telegram handlers for ``📈 بازار ایران`` and its asset purchases."""

from __future__ import annotations

import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler

from app.bot.context import get_services
from app.bot.keyboards import (
    build_back_to_main,
    build_iran_market_detail,
    build_iran_market_menu,
    callbacks,
)
from app.bot.messages import errors as error_messages
from app.bot.messages import iran_market as market_messages
from app.core import constants
from app.game.admin.parsing import parse_admin_int
from app.game.market.catalog import COIN_CODE, GOLD_CODE, USD_CODE
from app.game.shared.errors import DomainError, InsufficientFundsError, PlayerNotFoundError
from app.services.iran_market_service import (
    IranMarketAssetNotFoundError,
    IranMarketInvalidQuantityError,
    IranMarketPurchaseError,
    IranMarketPurchaseNotAllowedError,
)

logger = logging.getLogger(__name__)

IRAN_MARKET_INPUT_STATE: int = 1
_MARKET_PENDING_KEY: str = "iran_market_pending_purchase"
IRAN_MARKET_TEXT_TRIGGERS: tuple[str, ...] = constants.IRAN_MARKET_TEXT_TRIGGER_ALIASES
IRAN_MARKET_TEXT_PATTERN: str = "^(?:" + "|".join(
    re.escape(item) for item in IRAN_MARKET_TEXT_TRIGGERS
) + ")$"
MARKET_PURCHASE_PATTERN: str = (
    r"^خرید(?:\s+دلار(?:\s|$)|\s+طلا(?:\s|$)|\s+سکه(?:\s|$)"
    r"|\s+\S+\s+گرم(?:\s+طلا)?(?:\s|$)|\s+\S+\s+سکه(?:\s|$)).*$"
)

_FA_AR_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "0123456789" * 2
)


def _normalize_purchase_text(raw: str) -> str:
    return " ".join((raw or "").translate(_FA_AR_DIGITS).strip().split())


def _parse_direct_purchase(raw: str) -> tuple[str, int] | None:
    """Parse only the requested natural Persian command forms."""
    text = _normalize_purchase_text(raw)
    patterns = (
        (r"خرید دلار (.+)", USD_CODE),
        (r"خرید (.+) گرم طلا", GOLD_CODE),
        (r"خرید طلا (.+) گرم", GOLD_CODE),
        (r"خرید (.+) سکه", COIN_CODE),
    )
    for pattern, code in patterns:
        match = re.fullmatch(pattern, text)
        if match is None:
            continue
        quantity = parse_admin_int(match.group(1))
        if quantity is None or quantity <= 0:
            return code, 0
        return code, quantity
    return None


def _error_text(exc: DomainError) -> str:
    mapping = {
        IranMarketAssetNotFoundError: market_messages.market_asset_not_found_text,
        IranMarketInvalidQuantityError: market_messages.purchase_invalid_quantity_text,
        IranMarketPurchaseNotAllowedError: market_messages.purchase_not_allowed_text,
        IranMarketPurchaseError: market_messages.purchase_error_text,
        InsufficientFundsError: market_messages.insufficient_balance_text,
        PlayerNotFoundError: lambda: error_messages.NOT_REGISTERED,
    }
    factory = mapping.get(type(exc))
    return factory() if factory else error_messages.GENERIC


async def _edit(query, text: str, markup=None) -> None:
    try:
        await query.edit_message_text(text=text, reply_markup=markup)
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise
        logger.debug("Ignored identical Iran market edit")


async def _resolve_player_id(services, telegram_user_id: int) -> int | None:
    return await services.players.resolve_player_id(telegram_user_id)


async def iran_market_text_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Open the stored market snapshot from «بازار ایران»/«بازار»."""
    if update.message is None or update.effective_user is None:
        return
    if (update.message.text or "").strip() not in IRAN_MARKET_TEXT_TRIGGERS:
        return
    services = get_services(context)
    try:
        snapshot = await services.market.get_snapshot()
        await update.message.reply_text(
            market_messages.iran_market_menu_text(snapshot),
            reply_markup=build_iran_market_menu(snapshot.assets),
        )
    except Exception as exc:  # noqa: BLE001 — no traceback to a player
        logger.error("Iran market text screen failed (%s)", type(exc).__name__)
        await update.message.reply_text(error_messages.GENERIC)


async def show_iran_market_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.MARKET_MENU:
        return
    await query.answer()
    services = get_services(context)
    try:
        snapshot = await services.market.get_snapshot()
        await _edit(
            query,
            market_messages.iran_market_menu_text(snapshot),
            build_iran_market_menu(snapshot.assets),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Iran market menu failed (%s)", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_back_to_main())


async def show_iran_market_asset(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None:
        return
    data = query.data or ""
    if not data.startswith(callbacks.MARKET_ASSET_PREFIX):
        return
    await query.answer()
    code = data[len(callbacks.MARKET_ASSET_PREFIX) :]
    services = get_services(context)
    try:
        asset = await services.market.get_asset(code)
        await _edit(
            query,
            market_messages.iran_market_detail_text(asset),
            build_iran_market_detail(asset),
        )
    except IranMarketAssetNotFoundError:
        await _edit(
            query,
            market_messages.market_asset_not_found_text(),
            build_back_to_main(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Iran market detail failed (%s)", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_back_to_main())


async def purchase_command_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle the exact direct purchase commands requested by the game UI."""
    if update.message is None or update.effective_user is None:
        return
    parsed = _parse_direct_purchase(update.message.text or "")
    if parsed is None:
        await update.message.reply_text(market_messages.purchase_invalid_quantity_text())
        return
    asset_code, quantity = parsed
    if quantity <= 0:
        await update.message.reply_text(market_messages.purchase_invalid_quantity_text())
        return
    services = get_services(context)
    try:
        player_id = await _resolve_player_id(services, update.effective_user.id)
        if player_id is None:
            await update.message.reply_text(error_messages.NOT_REGISTERED)
            return
        result = await services.market.purchase_asset(player_id, asset_code, quantity)
        await update.message.reply_text(
            market_messages.purchase_command_success_text(result)
        )
    except DomainError as exc:
        await update.message.reply_text(_error_text(exc))
    except Exception as exc:  # noqa: BLE001 — no traceback to a player
        logger.error("Iran market direct purchase failed (%s)", type(exc).__name__)
        await update.message.reply_text(error_messages.GENERIC)


async def start_purchase_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    await query.answer()
    code = (query.data or "")[len(callbacks.MARKET_BUY_PREFIX) :]
    services = get_services(context)
    try:
        asset = await services.market.get_asset(code)
        if asset.category == "housing":
            raise IranMarketPurchaseNotAllowedError(code)
        context.user_data[_MARKET_PENDING_KEY] = code
        await _edit(
            query,
            market_messages.purchase_quantity_prompt(asset),
            _build_purchase_cancel_keyboard(),
        )
        return IRAN_MARKET_INPUT_STATE
    except DomainError as exc:
        await _edit(query, _error_text(exc), build_iran_market_detail())
        return ConversationHandler.END
    except Exception as exc:  # noqa: BLE001
        logger.error("Iran market purchase prompt failed (%s)", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_back_to_main())
        return ConversationHandler.END


async def purchase_input_received(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.message is None or update.effective_user is None:
        return ConversationHandler.END
    code = context.user_data.get(_MARKET_PENDING_KEY)
    quantity = parse_admin_int(update.message.text or "")
    if not isinstance(code, str):
        return ConversationHandler.END
    if quantity is None or quantity <= 0:
        await update.message.reply_text(market_messages.purchase_invalid_quantity_text())
        return IRAN_MARKET_INPUT_STATE
    services = get_services(context)
    try:
        player_id = await _resolve_player_id(services, update.effective_user.id)
        if player_id is None:
            await update.message.reply_text(error_messages.NOT_REGISTERED)
            return ConversationHandler.END
        result = await services.market.purchase_asset(player_id, code, quantity)
        await update.message.reply_text(market_messages.purchase_success_text(result))
    except DomainError as exc:
        await update.message.reply_text(_error_text(exc))
    except Exception as exc:  # noqa: BLE001
        logger.error("Iran market input purchase failed (%s)", type(exc).__name__)
        await update.message.reply_text(error_messages.GENERIC)
    finally:
        context.user_data.pop(_MARKET_PENDING_KEY, None)
    return ConversationHandler.END


async def cancel_purchase_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    context.user_data.pop(_MARKET_PENDING_KEY, None)
    query = update.callback_query
    if query is not None:
        await query.answer()
        await _edit(query, "خرید لغو شد.", build_iran_market_detail())
    return ConversationHandler.END


def _build_purchase_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "❌ لغو", callback_data=callbacks.MARKET_INPUT_CANCEL
                )
            ]
        ]
    )
