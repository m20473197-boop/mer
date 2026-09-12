"""Telegram flows for the separate ``🏦 بانک ایران`` ledger."""

from __future__ import annotations

import logging
import re
from secrets import token_hex

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler

from app.bot.context import get_services
from app.bot.keyboards import (
    build_bank_cancel,
    build_bank_history,
    build_bank_menu,
    build_back_to_main,
    build_transfer_confirmation,
    build_transfer_recipient_confirmation,
    callbacks,
)
from app.bot.messages import bank as bank_messages
from app.bot.messages import errors as error_messages
from app.core import constants
from app.game.admin.parsing import parse_admin_int
from app.game.shared.errors import DomainError, InsufficientFundsError, PlayerNotFoundError
from app.services.bank_service import (
    BankAccountNotFoundError,
    BankError,
    BankInsufficientBalanceError,
    BankInvalidAmountError,
    BankInvalidCardError,
    BankRecipientNotFoundError,
    BankSelfTransferError,
)

logger = logging.getLogger(__name__)

BANK_AMOUNT_STATE: int = 1
BANK_TRANSFER_CARD_STATE: int = 2
BANK_TRANSFER_RECIPIENT_STATE: int = 3
BANK_TRANSFER_AMOUNT_STATE: int = 4
BANK_TRANSFER_CONFIRM_STATE: int = 5
_BANK_PENDING_KEY: str = "iran_bank_pending_operation"

BANK_TEXT_TRIGGERS: tuple[str, ...] = constants.BANK_TEXT_TRIGGER_ALIASES
BANK_TEXT_PATTERN: str = "^(?:" + "|".join(
    re.escape(item) for item in BANK_TEXT_TRIGGERS
) + ")$"


def _error_text(exc: Exception) -> str:
    if isinstance(exc, BankInvalidAmountError):
        return bank_messages.invalid_amount_text()
    if isinstance(exc, BankInvalidCardError):
        return bank_messages.invalid_card_text()
    if isinstance(exc, BankRecipientNotFoundError):
        return bank_messages.recipient_not_found_text()
    if isinstance(exc, BankSelfTransferError):
        return bank_messages.self_transfer_text()
    if isinstance(exc, BankInsufficientBalanceError):
        return bank_messages.insufficient_bank_text()
    if isinstance(exc, InsufficientFundsError):
        return bank_messages.insufficient_wallet_text()
    if isinstance(exc, PlayerNotFoundError) or isinstance(exc, BankAccountNotFoundError):
        return bank_messages.not_registered_text()
    if isinstance(exc, BankError):
        return bank_messages.operation_error_text()
    if isinstance(exc, DomainError):
        return bank_messages.operation_error_text()
    return error_messages.GENERIC


async def _edit_safely(query, text: str, reply_markup=None) -> None:
    try:
        await query.edit_message_text(text=text, reply_markup=reply_markup)
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise
        logger.debug("Ignored identical bank message edit")


async def _player_id(services, telegram_user_id: int) -> int | None:
    return await services.players.resolve_player_id(telegram_user_id)


async def _show_bank_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    player_id = await _player_id(services, update.effective_user.id)
    if player_id is None:
        if update.callback_query is not None:
            await _edit_safely(update.callback_query, bank_messages.not_registered_text())
        elif update.message is not None:
            await update.message.reply_text(bank_messages.not_registered_text())
        return
    interest = await services.bank.process_interest_for_player(player_id)
    account = await services.bank.get_account(player_id, process_interest=False)
    text = bank_messages.bank_menu_text(account)
    notice = bank_messages.interest_notice(interest)
    if notice:
        text += f"\n\n{notice}"
    if update.callback_query is not None:
        await _edit_safely(update.callback_query, text, build_bank_menu())
    elif update.message is not None:
        await update.message.reply_text(text, reply_markup=build_bank_menu())


async def bank_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Open the bank from «بانک ایران» or the shorter «بانک» text."""

    if update.message is None or update.effective_user is None:
        return
    try:
        await _show_bank_menu(update, context)
    except Exception as exc:  # noqa: BLE001 - player-facing boundary
        logger.error("Bank text menu failed (%s)", type(exc).__name__)
        await update.message.reply_text(_error_text(exc))


async def show_bank_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.BANK_MENU:
        return
    await query.answer()
    try:
        await _show_bank_menu(update, context)
    except Exception as exc:  # noqa: BLE001
        logger.error("Bank menu failed (%s)", type(exc).__name__)
        await _edit_safely(query, _error_text(exc), build_back_to_main())


async def show_bank_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.BANK_BALANCE:
        return
    await query.answer()
    services = get_services(context)
    try:
        player_id = await _player_id(services, query.from_user.id)
        if player_id is None:
            await _edit_safely(query, bank_messages.not_registered_text())
            return
        interest = await services.bank.process_interest_for_player(player_id)
        account = await services.bank.get_account(player_id, process_interest=False)
        text = bank_messages.balance_text(account)
        notice = bank_messages.interest_notice(interest)
        if notice:
            text += f"\n\n{notice}"
        await _edit_safely(query, text, build_bank_menu())
    except Exception as exc:  # noqa: BLE001
        logger.error("Bank balance failed (%s)", type(exc).__name__)
        await _edit_safely(query, _error_text(exc), build_bank_menu())


async def show_bank_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.BANK_CARD:
        return
    await query.answer()
    services = get_services(context)
    try:
        player_id = await _player_id(services, query.from_user.id)
        if player_id is None:
            await _edit_safely(query, bank_messages.not_registered_text())
            return
        interest = await services.bank.process_interest_for_player(player_id)
        account = await services.bank.get_account(player_id, process_interest=False)
        text = bank_messages.card_text(account)
        notice = bank_messages.interest_notice(interest)
        if notice:
            text += f"\n\n{notice}"
        await _edit_safely(query, text, build_bank_menu())
    except Exception as exc:  # noqa: BLE001
        logger.error("Bank card failed (%s)", type(exc).__name__)
        await _edit_safely(query, _error_text(exc), build_bank_menu())


async def show_bank_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.BANK_HISTORY:
        return
    await query.answer()
    await _show_history(query, context, 0)


async def show_bank_history_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    data = query.data or ""
    if not data.startswith(callbacks.BANK_HISTORY_PAGE_PREFIX):
        return
    await query.answer()
    raw_page = data[len(callbacks.BANK_HISTORY_PAGE_PREFIX) :]
    page = int(raw_page) if raw_page.isdigit() else 0
    await _show_history(query, context, page)


async def _show_history(query, context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    services = get_services(context)
    try:
        player_id = await _player_id(services, query.from_user.id)
        if player_id is None:
            await _edit_safely(query, bank_messages.not_registered_text())
            return
        transactions, total, page, page_size = await services.bank.get_history(
            player_id, page=page, page_size=constants.BANK_HISTORY_PAGE_SIZE
        )
        await _edit_safely(
            query,
            bank_messages.history_text(transactions, page, total),
            build_bank_history(
                page,
                has_previous=page > 0,
                has_next=(page + 1) * page_size < total,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Bank history failed (%s)", type(exc).__name__)
        await _edit_safely(query, _error_text(exc), build_bank_menu())


# ---------------------------------------------------------------------------
# ConversationHandler input flow
# ---------------------------------------------------------------------------

async def start_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _start_amount(update, context, "deposit", bank_messages.deposit_prompt())


async def start_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _start_amount(update, context, "withdraw", bank_messages.withdrawal_prompt())


async def _start_amount(
    update: Update, context: ContextTypes.DEFAULT_TYPE, kind: str, prompt: str
) -> int:
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    await query.answer()
    context.user_data[_BANK_PENDING_KEY] = {
        "kind": kind,
        "operation_id": f"UI-{token_hex(16)}",
    }
    await _edit_safely(query, prompt, build_bank_cancel())
    return BANK_AMOUNT_STATE


async def start_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    await query.answer()
    context.user_data[_BANK_PENDING_KEY] = {
        "kind": "transfer",
        "operation_id": f"UI-{token_hex(16)}",
    }
    await _edit_safely(query, bank_messages.transfer_card_prompt(), build_bank_cancel())
    return BANK_TRANSFER_CARD_STATE


async def amount_input_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None or update.effective_user is None:
        return ConversationHandler.END
    pending = context.user_data.get(_BANK_PENDING_KEY)
    if not isinstance(pending, dict) or pending.get("kind") not in {"deposit", "withdraw"}:
        return ConversationHandler.END
    amount = parse_admin_int(update.message.text or "")
    if amount is None or amount <= 0:
        await update.message.reply_text(bank_messages.invalid_amount_text(), reply_markup=build_bank_cancel())
        return BANK_AMOUNT_STATE
    if pending.get("processing"):
        await update.message.reply_text("⏳ این عملیات در حال انجام است؛ لطفاً کمی صبر کن.")
        return BANK_AMOUNT_STATE
    # Set before the first await so duplicate Telegram updates cannot execute
    # the same pending operation twice inside this process.
    pending["processing"] = True
    services = get_services(context)
    try:
        player_id = await _player_id(services, update.effective_user.id)
        if player_id is None:
            await update.message.reply_text(bank_messages.not_registered_text())
            return ConversationHandler.END
        if pending["kind"] == "deposit":
            result = await services.bank.deposit(
                player_id, amount, operation_id=pending.get("operation_id")
            )
            text = bank_messages.deposit_success(result)
        else:
            result = await services.bank.withdraw(
                player_id, amount, operation_id=pending.get("operation_id")
            )
            text = bank_messages.withdrawal_success(result)
        await update.message.reply_text(text, reply_markup=build_bank_menu())
    except Exception as exc:  # noqa: BLE001
        await update.message.reply_text(_error_text(exc), reply_markup=build_bank_menu())
    finally:
        context.user_data.pop(_BANK_PENDING_KEY, None)
    return ConversationHandler.END


async def transfer_card_input_received(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.message is None or update.effective_user is None:
        return ConversationHandler.END
    pending = context.user_data.get(_BANK_PENDING_KEY)
    if not isinstance(pending, dict) or pending.get("kind") != "transfer":
        return ConversationHandler.END
    services = get_services(context)
    player_id = await _player_id(services, update.effective_user.id)
    if player_id is None:
        await update.message.reply_text(bank_messages.not_registered_text())
        context.user_data.pop(_BANK_PENDING_KEY, None)
        return ConversationHandler.END
    try:
        preview = await services.bank.preview_transfer(player_id, update.message.text or "")
    except Exception as exc:  # noqa: BLE001
        await update.message.reply_text(_error_text(exc), reply_markup=build_bank_cancel())
        return BANK_TRANSFER_CARD_STATE
    pending["preview"] = preview
    pending["card_number"] = preview.recipient_card_number
    await update.message.reply_text(
        bank_messages.transfer_recipient_text(preview),
        reply_markup=build_transfer_recipient_confirmation(preview),
    )
    return BANK_TRANSFER_RECIPIENT_STATE


async def transfer_recipient_continue(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    pending = context.user_data.get(_BANK_PENDING_KEY)
    if query is None or not isinstance(pending, dict):
        return ConversationHandler.END
    await query.answer()
    preview = pending.get("preview")
    if preview is None:
        context.user_data.pop(_BANK_PENDING_KEY, None)
        await _edit_safely(query, bank_messages.cancelled_text(), build_bank_menu())
        return ConversationHandler.END
    await _edit_safely(query, bank_messages.transfer_amount_prompt(preview), build_bank_cancel())
    return BANK_TRANSFER_AMOUNT_STATE


async def transfer_amount_input_received(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.message is None or update.effective_user is None:
        return ConversationHandler.END
    pending = context.user_data.get(_BANK_PENDING_KEY)
    if not isinstance(pending, dict) or pending.get("preview") is None:
        return ConversationHandler.END
    amount = parse_admin_int(update.message.text or "")
    if amount is None or amount <= 0:
        await update.message.reply_text(bank_messages.invalid_amount_text(), reply_markup=build_bank_cancel())
        return BANK_TRANSFER_AMOUNT_STATE
    pending["amount"] = amount
    await update.message.reply_text(
        bank_messages.transfer_confirmation_text(pending["preview"], amount),
        reply_markup=build_transfer_confirmation(),
    )
    return BANK_TRANSFER_CONFIRM_STATE


async def confirm_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    pending = context.user_data.get(_BANK_PENDING_KEY)
    if query is None or not isinstance(pending, dict):
        return ConversationHandler.END
    if pending.get("processing"):
        await query.answer("⏳ این عملیات در حال انجام است؛ لطفاً کمی صبر کن.")
        return BANK_TRANSFER_CONFIRM_STATE
    await query.answer()
    pending["processing"] = True
    try:
        amount = pending.get("amount")
        card_number = pending.get("card_number")
        if not isinstance(amount, int) or not isinstance(card_number, str):
            raise BankInvalidAmountError("transfer confirmation expired")
        services = get_services(context)
        player_id = await _player_id(services, query.from_user.id)
        if player_id is None:
            raise PlayerNotFoundError("player not registered")
        # The service resolves the card and checks the sender balance again in
        # the same atomic transaction; the preview is never trusted as auth.
        result = await services.bank.transfer(
            player_id,
            card_number,
            amount,
            operation_id=pending.get("operation_id"),
        )
        await _edit_safely(query, bank_messages.transfer_success(result), build_bank_menu())
    except Exception as exc:  # noqa: BLE001
        await _edit_safely(query, _error_text(exc), build_bank_menu())
    finally:
        context.user_data.pop(_BANK_PENDING_KEY, None)
    return ConversationHandler.END


async def cancel_bank_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop(_BANK_PENDING_KEY, None)
    query = update.callback_query
    if query is not None:
        await query.answer()
        await _edit_safely(query, bank_messages.cancelled_text(), build_bank_menu())
    return ConversationHandler.END
