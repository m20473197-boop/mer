"""Inline keyboards for the predefined Business System."""

from __future__ import annotations

from app.bot.keyboards import callbacks
from app.bot.keyboards.main_menu import BUTTON_BACK_TO_MAIN
from app.bot.messages.formatters import fa_int
from app.game.business.dto import BusinessData, BusinessDefinitionData
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

BUTTON_BUSINESS_LIST: str = "📋 کسب‌وکارهای موجود"
BUTTON_BUSINESS_MY: str = "🏪 کسب‌وکارهای من"
BUTTON_BUSINESS_INCOME: str = "💰 درآمد امروز"
BUTTON_BACK_TO_BUSINESS: str = "🔙 منوی کسب‌وکار"


def build_business_menu() -> InlineKeyboardMarkup:
    """The Business System landing screen."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    BUTTON_BUSINESS_LIST, callback_data=callbacks.BUSINESS_LIST
                ),
                InlineKeyboardButton(
                    BUTTON_BUSINESS_MY, callback_data=callbacks.BUSINESS_MY
                ),
            ],
            [
                InlineKeyboardButton(
                    BUTTON_BUSINESS_INCOME,
                    callback_data=callbacks.BUSINESS_INCOME,
                ),
            ],
            [
                InlineKeyboardButton(
                    BUTTON_BACK_TO_MAIN, callback_data=callbacks.BACK_TO_MAIN
                )
            ],
        ]
    )


def build_business_list(
    businesses: list[BusinessDefinitionData],
) -> InlineKeyboardMarkup:
    """Show one start button for each available predefined business."""
    rows: list[list[InlineKeyboardButton]] = []
    for business in businesses:
        if business.is_available:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"شروع «{business.name}» — {fa_int(business.startup_cost)} تومان",
                        callback_data=(
                            f"{callbacks.BUSINESS_START_PREFIX}{business.key}"
                        ),
                    )
                ]
            )
        else:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"🔒 «{business.name}» — فعلاً بسته",
                        callback_data=callbacks.BUSINESS_LIST,
                    )
                ]
            )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    BUTTON_BACK_TO_BUSINESS, callback_data=callbacks.BUSINESS_MENU
                )
            ],
            [
                InlineKeyboardButton(
                    BUTTON_BACK_TO_MAIN, callback_data=callbacks.BACK_TO_MAIN
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_owned_businesses(
    businesses: list[BusinessData],
) -> InlineKeyboardMarkup:
    """Owned-business screen actions."""
    rows: list[list[InlineKeyboardButton]] = []
    if businesses:
        rows.append(
            [
                InlineKeyboardButton(
                    BUTTON_BUSINESS_INCOME,
                    callback_data=callbacks.BUSINESS_INCOME,
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    BUTTON_BUSINESS_LIST, callback_data=callbacks.BUSINESS_LIST
                )
            ],
            [
                InlineKeyboardButton(
                    BUTTON_BACK_TO_BUSINESS, callback_data=callbacks.BUSINESS_MENU
                )
            ],
            [
                InlineKeyboardButton(
                    BUTTON_BACK_TO_MAIN, callback_data=callbacks.BACK_TO_MAIN
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(rows)
