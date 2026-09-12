"""Inline keyboards for ``🏦 بانک ایران``."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards import callbacks
from app.bot.keyboards.main_menu import BUTTON_BACK_TO_MAIN
from app.game.bank.dto import BankTransferPreview

BUTTON_BANK_BALANCE: str = "💰 موجودی بانک"
BUTTON_BANK_CARD: str = "💳 شماره کارت"
BUTTON_BANK_DEPOSIT: str = "💵 سپرده‌گذاری"
BUTTON_BANK_WITHDRAW: str = "💸 برداشت"
BUTTON_BANK_TRANSFER: str = "💳 انتقال وجه"
BUTTON_BANK_HISTORY: str = "📜 تاریخچه تراکنش‌ها"
BUTTON_BANK_CANCEL: str = "❌ لغو"
BUTTON_BANK_TRANSFER_CONTINUE: str = "✅ ادامه"
BUTTON_BANK_TRANSFER_CONFIRM: str = "✅ تأیید انتقال"


def build_bank_menu() -> InlineKeyboardMarkup:
    """The six requested bank actions plus a main-menu escape."""

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(BUTTON_BANK_BALANCE, callback_data=callbacks.BANK_BALANCE),
                InlineKeyboardButton(BUTTON_BANK_CARD, callback_data=callbacks.BANK_CARD),
            ],
            [
                InlineKeyboardButton(BUTTON_BANK_DEPOSIT, callback_data=callbacks.BANK_DEPOSIT),
                InlineKeyboardButton(BUTTON_BANK_WITHDRAW, callback_data=callbacks.BANK_WITHDRAW),
            ],
            [
                InlineKeyboardButton(BUTTON_BANK_TRANSFER, callback_data=callbacks.BANK_TRANSFER),
                InlineKeyboardButton(BUTTON_BANK_HISTORY, callback_data=callbacks.BANK_HISTORY),
            ],
            [
                InlineKeyboardButton(BUTTON_BACK_TO_MAIN, callback_data=callbacks.BACK_TO_MAIN),
            ],
        ]
    )


def build_bank_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(BUTTON_BANK_CANCEL, callback_data=callbacks.BANK_CANCEL)]]
    )


def build_transfer_recipient_confirmation(preview: BankTransferPreview) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    BUTTON_BANK_TRANSFER_CONTINUE,
                    callback_data=callbacks.BANK_TRANSFER_RECIPIENT_OK,
                ),
                InlineKeyboardButton(BUTTON_BANK_CANCEL, callback_data=callbacks.BANK_CANCEL),
            ]
        ]
    )


def build_transfer_confirmation() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    BUTTON_BANK_TRANSFER_CONFIRM,
                    callback_data=callbacks.BANK_TRANSFER_CONFIRM,
                ),
                InlineKeyboardButton(BUTTON_BANK_CANCEL, callback_data=callbacks.BANK_CANCEL),
            ]
        ]
    )


def build_bank_history(page: int, has_previous: bool, has_next: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    navigation: list[InlineKeyboardButton] = []
    if has_previous:
        navigation.append(
            InlineKeyboardButton(
                "⬅️ قبلی",
                callback_data=f"{callbacks.BANK_HISTORY_PAGE_PREFIX}{page - 1}",
            )
        )
    if has_next:
        navigation.append(
            InlineKeyboardButton(
                "بعدی ➡️",
                callback_data=f"{callbacks.BANK_HISTORY_PAGE_PREFIX}{page + 1}",
            )
        )
    if navigation:
        rows.append(navigation)
    rows.append(
        [
            InlineKeyboardButton("🔙 بانک ایران", callback_data=callbacks.BANK_MENU),
            InlineKeyboardButton(BUTTON_BACK_TO_MAIN, callback_data=callbacks.BACK_TO_MAIN),
        ]
    )
    return InlineKeyboardMarkup(rows)
