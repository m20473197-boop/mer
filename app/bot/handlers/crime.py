"""Telegram translation layer for the fictional 🕳️ خلاف system."""

from __future__ import annotations

import logging
import re
from secrets import token_hex

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler

from app.bot.context import get_services
from app.bot.keyboards import (
    build_crime_cancel,
    build_crime_history,
    build_crime_menu,
    build_document_menu,
    build_shoti_vehicle_menu,
    callbacks,
)
from app.bot.messages import crime as crime_messages
from app.bot.messages import errors as error_messages
from app.core import constants
from app.game.admin.parsing import parse_admin_int
from app.game.crime.errors import (
    CrimeActiveMissionError,
    CrimeCooldownError,
    CrimeDuplicateDocumentError,
    CrimeError,
    CrimeInsufficientFundsError,
    CrimeInvalidAmountError,
    CrimeInvalidDocumentTypeError,
    CrimeInvalidTargetError,
    CrimeNoEligibleVehicleError,
    CrimeTargetBankAccountError,
    CrimeVehicleNotOwnedError,
)
from app.game.shared.errors import DomainError, PlayerNotFoundError

logger = logging.getLogger(__name__)

CRIME_TARGET_STATE: int = 1
CRIME_AMOUNT_STATE: int = 2
_CRIME_PENDING_KEY: str = "crime_pending_operation"

CRIME_TEXT_PATTERN: str = "^(?:" + "|".join(
    re.escape(item) for item in constants.CRIME_TEXT_TRIGGER_ALIASES
) + ")$"


async def _player_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    user = update.effective_user
    if user is None:
        return None
    return await get_services(context).players.resolve_player_id(user.id)


async def _edit_safely(query, text: str, reply_markup=None) -> None:
    try:
        await query.edit_message_text(text=text, reply_markup=reply_markup)
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise
        logger.debug("Ignored identical crime message edit")


def _error_text(exc: Exception) -> str:
    if isinstance(exc, CrimeCooldownError):
        return crime_messages.cooldown(exc.remaining_seconds)
    if isinstance(exc, CrimeInvalidTargetError):
        return crime_messages.invalid_target()
    if isinstance(exc, CrimeTargetBankAccountError):
        return crime_messages.target_without_bank()
    if isinstance(exc, (CrimeInvalidAmountError,)):
        return crime_messages.invalid_amount()
    if isinstance(exc, CrimeInsufficientFundsError):
        return crime_messages.insufficient_wallet()
    if isinstance(exc, CrimeDuplicateDocumentError):
        return crime_messages.duplicate_document()
    if isinstance(exc, CrimeInvalidDocumentTypeError):
        return crime_messages.invalid_document()
    if isinstance(exc, CrimeNoEligibleVehicleError):
        return crime_messages.shoti_no_vehicle()
    if isinstance(exc, CrimeVehicleNotOwnedError):
        return crime_messages.vehicle_not_owned()
    if isinstance(exc, CrimeActiveMissionError):
        return crime_messages.active_mission()
    if isinstance(exc, PlayerNotFoundError):
        return crime_messages.not_registered()
    if isinstance(exc, (CrimeError, DomainError)):
        return crime_messages.generic_error()
    return error_messages.GENERIC


async def crime_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text(crime_messages.menu_text(), reply_markup=build_crime_menu())


async def show_crime_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.CRIME_MENU:
        return
    await query.answer()
    await _edit_safely(query, crime_messages.menu_text(), build_crime_menu())


# ---------------------------------------------------------------------------
# Target and amount conversations
# ---------------------------------------------------------------------------


async def start_information(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    await query.answer()
    context.user_data[_CRIME_PENDING_KEY] = {
        "kind": "information",
        "operation_key": f"ui-info-{token_hex(16)}",
    }
    await _edit_safely(query, crime_messages.target_prompt("information"), build_crime_cancel())
    return CRIME_TARGET_STATE


async def start_bank_hack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    await query.answer()
    context.user_data[_CRIME_PENDING_KEY] = {
        "kind": "hack",
        "operation_key": f"ui-hack-{token_hex(16)}",
    }
    await _edit_safely(query, crime_messages.target_prompt("hack"), build_crime_cancel())
    return CRIME_TARGET_STATE


async def target_input_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    if message is None:
        return CRIME_TARGET_STATE
    pending = context.user_data.get(_CRIME_PENDING_KEY)
    if not pending or pending.get("kind") not in {"information", "hack"}:
        return ConversationHandler.END
    replied = message.reply_to_message
    if replied is None or replied.from_user is None or replied.from_user.is_bot:
        await message.reply_text(crime_messages.invalid_target(), reply_markup=build_crime_cancel())
        return CRIME_TARGET_STATE
    services = get_services(context)
    actor_id = await _player_id(update, context)
    if actor_id is None:
        await message.reply_text(crime_messages.not_registered())
        context.user_data.pop(_CRIME_PENDING_KEY, None)
        return ConversationHandler.END
    target_id = await services.players.resolve_player_id(replied.from_user.id)
    if target_id is None:
        await message.reply_text(crime_messages.invalid_target(), reply_markup=build_crime_cancel())
        return CRIME_TARGET_STATE
    try:
        if pending["kind"] == "information":
            result = await services.crime.sell_information(
                actor_id, target_id, operation_key=pending["operation_key"]
            )
            text = crime_messages.information_result(result)
        else:
            result = await services.crime.hack_bank_account(
                actor_id, target_id, operation_key=pending["operation_key"]
            )
            text = crime_messages.hack_result(result)
    except Exception as exc:  # noqa: BLE001 - player-facing boundary
        text = _error_text(exc)
        if isinstance(exc, (CrimeInvalidTargetError, CrimeTargetBankAccountError)):
            await message.reply_text(text, reply_markup=build_crime_cancel())
            if isinstance(exc, CrimeInvalidTargetError):
                return CRIME_TARGET_STATE
            context.user_data.pop(_CRIME_PENDING_KEY, None)
            return ConversationHandler.END
        context.user_data.pop(_CRIME_PENDING_KEY, None)
        await message.reply_text(text, reply_markup=build_crime_menu())
        return ConversationHandler.END
    context.user_data.pop(_CRIME_PENDING_KEY, None)
    await message.reply_text(text, reply_markup=build_crime_menu())
    return ConversationHandler.END


async def start_laundering(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    await query.answer()
    config = get_services(context).crime.config
    context.user_data[_CRIME_PENDING_KEY] = {
        "kind": "laundering",
        "operation_key": f"ui-launder-{token_hex(16)}",
    }
    await _edit_safely(
        query,
        crime_messages.laundering_prompt(
            config.laundering_min_amount, config.laundering_max_amount
        ),
        build_crime_cancel(),
    )
    return CRIME_AMOUNT_STATE


async def amount_input_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    if message is None:
        return CRIME_AMOUNT_STATE
    pending = context.user_data.get(_CRIME_PENDING_KEY)
    if not pending or pending.get("kind") != "laundering":
        return ConversationHandler.END
    amount = parse_admin_int(message.text or "")
    if amount is None:
        await message.reply_text(crime_messages.invalid_amount(), reply_markup=build_crime_cancel())
        return CRIME_AMOUNT_STATE
    actor_id = await _player_id(update, context)
    if actor_id is None:
        await message.reply_text(crime_messages.not_registered())
        context.user_data.pop(_CRIME_PENDING_KEY, None)
        return ConversationHandler.END
    try:
        result = await get_services(context).crime.start_laundering(
            actor_id, amount, operation_key=pending["operation_key"]
        )
    except Exception as exc:  # noqa: BLE001
        text = _error_text(exc)
        await message.reply_text(text, reply_markup=build_crime_cancel())
        if isinstance(exc, (CrimeCooldownError, CrimeInsufficientFundsError)):
            context.user_data.pop(_CRIME_PENDING_KEY, None)
            return ConversationHandler.END
        return CRIME_AMOUNT_STATE
    context.user_data.pop(_CRIME_PENDING_KEY, None)
    await message.reply_text(crime_messages.laundering_started(result), reply_markup=build_crime_menu())
    return ConversationHandler.END


async def cancel_crime_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is not None:
        await query.answer()
        await _edit_safely(query, crime_messages.menu_text(), build_crime_menu())
    context.user_data.pop(_CRIME_PENDING_KEY, None)
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


async def show_documents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.CRIME_DOCUMENTS:
        return
    await query.answer()
    try:
        player_id = await _player_id(update, context)
        if player_id is None:
            await _edit_safely(query, crime_messages.not_registered())
            return
        service = get_services(context).crime
        rows = await service.list_documents(player_id)
        active = {row.document_type for row in rows if row.status == "active"}
        await _edit_safely(
            query,
            crime_messages.documents_menu(rows),
            build_document_menu(service.config.fake_documents, active),
        )
    except Exception as exc:  # noqa: BLE001
        await _edit_safely(query, _error_text(exc), build_crime_menu())


async def issue_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not (query.data or "").startswith(callbacks.CRIME_DOCUMENT_PREFIX):
        return
    await query.answer()
    code = (query.data or "")[len(callbacks.CRIME_DOCUMENT_PREFIX) :]
    player_id = await _player_id(update, context)
    if player_id is None:
        await _edit_safely(query, crime_messages.not_registered(), build_crime_menu())
        return
    try:
        document = await get_services(context).crime.issue_fake_document(
            player_id, code, operation_key=f"ui-doc-{token_hex(16)}"
        )
        await _edit_safely(query, crime_messages.document_issued(document), build_crime_menu())
    except Exception as exc:  # noqa: BLE001
        await _edit_safely(query, _error_text(exc), build_crime_menu())


# ---------------------------------------------------------------------------
# شوتی and history
# ---------------------------------------------------------------------------


async def show_shoti(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.CRIME_SHOTI:
        return
    await query.answer()
    player_id = await _player_id(update, context)
    if player_id is None:
        await _edit_safely(query, crime_messages.not_registered(), build_crime_menu())
        return
    try:
        service = get_services(context).crime
        vehicles = await service.get_eligible_vehicles(player_id)
        if not vehicles:
            await _edit_safely(query, crime_messages.shoti_no_vehicle(), build_crime_menu())
            return
        await _edit_safely(query, crime_messages.shoti_vehicle_prompt(), build_shoti_vehicle_menu(vehicles))
    except Exception as exc:  # noqa: BLE001
        await _edit_safely(query, _error_text(exc), build_crime_menu())


async def start_shoti_vehicle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    data = query.data or ""
    if not data.startswith(callbacks.CRIME_SHOTI_VEHICLE_PREFIX):
        return
    await query.answer()
    raw = data[len(callbacks.CRIME_SHOTI_VEHICLE_PREFIX) :]
    player_id = await _player_id(update, context)
    if player_id is None or not raw.isdigit():
        await _edit_safely(query, crime_messages.vehicle_not_owned(), build_crime_menu())
        return
    try:
        mission = await get_services(context).crime.start_shoti_mission(
            player_id,
            int(raw),
            operation_key=f"ui-shoti-{token_hex(16)}",
        )
        await _edit_safely(query, crime_messages.shoti_started(mission), build_crime_menu())
    except Exception as exc:  # noqa: BLE001
        await _edit_safely(query, _error_text(exc), build_crime_menu())


async def show_shoti_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.CRIME_SHOTI_HISTORY:
        return
    await query.answer()
    player_id = await _player_id(update, context)
    if player_id is None:
        await _edit_safely(query, crime_messages.not_registered(), build_crime_menu())
        return
    try:
        rows = await get_services(context).crime.get_shoti_missions(player_id)
        await _edit_safely(query, crime_messages.shoti_history(rows), build_crime_history())
    except Exception as exc:  # noqa: BLE001
        await _edit_safely(query, _error_text(exc), build_crime_menu())


async def show_laundering_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.CRIME_LAUNDERING_HISTORY:
        return
    await query.answer()
    player_id = await _player_id(update, context)
    if player_id is None:
        await _edit_safely(query, crime_messages.not_registered(), build_crime_menu())
        return
    try:
        rows = await get_services(context).crime.get_laundering_history(player_id)
        await _edit_safely(query, crime_messages.laundering_history(rows), build_crime_history())
    except Exception as exc:  # noqa: BLE001
        await _edit_safely(query, _error_text(exc), build_crime_menu())


async def show_crime_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.CRIME_HISTORY:
        return
    await query.answer()
    player_id = await _player_id(update, context)
    if player_id is None:
        await _edit_safely(query, crime_messages.not_registered(), build_crime_menu())
        return
    try:
        rows, total, _page, _page_size = await get_services(context).crime.get_history(player_id)
        await _edit_safely(query, crime_messages.history_text(rows, total), build_crime_history())
    except Exception as exc:  # noqa: BLE001
        await _edit_safely(query, _error_text(exc), build_crime_menu())
