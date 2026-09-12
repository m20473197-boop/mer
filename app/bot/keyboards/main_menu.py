"""Inline keyboard builders.

Keyboard construction lives here — never inside handlers — so menus stay
easy to reshape as new systems (jobs, market, ...) come online.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards import callbacks
from app.bot.messages.formatters import fa_int
from app.core import constants
from app.game.admin import runtime as admin_runtime

BUTTON_PROFILE: str = "👤 پروفایل"
BUTTON_STATUS: str = "📊 وضعیت"
BUTTON_JOBS: str = f"💼 {constants.JOBS_SYSTEM_NAME}"
BUTTON_BUSINESS: str = "🏪 کسب‌وکار"
BUTTON_IRAN_MARKET: str = f"📈 {constants.IRAN_MARKET_SYSTEM_NAME}"
BUTTON_DIVAR: str = f"🧱 {constants.DIVAR_SYSTEM_NAME}"
BUTTON_VEHICLE_DEALERSHIP: str = f"🚗 {constants.VEHICLE_DEALERSHIP_NAME}"
BUTTON_HOUSING: str = "🏠 خانه"
BUTTON_BACK_TO_MAIN: str = "🔙 منوی اصلی"


def build_main_menu() -> InlineKeyboardMarkup:
    """The main menu — only features that actually exist, nothing fake.

    Systems the admin switched off in ⚙️ Bot Settings are hidden as well
    (their handlers refuse access too, so stale buttons stay safe).
    """
    rows = [
        [
            InlineKeyboardButton(BUTTON_PROFILE, callback_data=callbacks.PROFILE),
            InlineKeyboardButton(BUTTON_STATUS, callback_data=callbacks.STATUS),
        ],
    ]
    if admin_runtime.feature_enabled("jobs"):
        rows.append(
            [
                InlineKeyboardButton(BUTTON_JOBS, callback_data=callbacks.JOBS_MENU),
            ]
        )
    # Business availability is controlled per predefined catalog entry; the
    # system itself is always visible because it has no arbitrary creation
    # path and no separate admin feature flag.
    rows.append(
        [
            InlineKeyboardButton(
                BUTTON_BUSINESS, callback_data=callbacks.BUSINESS_MENU
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                BUTTON_IRAN_MARKET, callback_data=callbacks.MARKET_MENU
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                BUTTON_DIVAR, callback_data=callbacks.DIVAR_MENU
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                BUTTON_VEHICLE_DEALERSHIP, callback_data=callbacks.VEHICLE_MENU
            ),
        ]
    )
    if admin_runtime.feature_enabled("housing"):
        rows.append(
            [
                InlineKeyboardButton(
                    BUTTON_HOUSING, callback_data=callbacks.HOUSING_MENU
                ),
            ]
        )
    return InlineKeyboardMarkup(rows)


def build_back_to_main() -> InlineKeyboardMarkup:
    """A single button that returns to the main menu."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    BUTTON_BACK_TO_MAIN, callback_data=callbacks.BACK_TO_MAIN
                )
            ]
        ]
    )


# --- Job keyboards ---------------------------------------------------------

BUTTON_JOBS_LIST: str = "📋 لیست کارها"
BUTTON_JOBS_MY_JOB: str = "👔 کار من"
BUTTON_JOBS_SETTLE: str = "💰 تسویه با صاحبکار"
BUTTON_JOBS_LEAVE: str = "🚪 ترک کار"
BUTTON_JOBS_HISTORY: str = "📜 تاریخچه تسویه‌ها"


def build_jobs_menu() -> InlineKeyboardMarkup:
    """Jobs main menu."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    BUTTON_JOBS_LIST, callback_data=callbacks.JOBS_LIST
                ),
                InlineKeyboardButton(
                    BUTTON_JOBS_MY_JOB, callback_data=callbacks.JOBS_MY_JOB
                ),
            ],
            [
                InlineKeyboardButton(
                    BUTTON_JOBS_SETTLE, callback_data=callbacks.JOBS_SETTLE
                ),
                InlineKeyboardButton(
                    BUTTON_JOBS_LEAVE, callback_data=callbacks.JOBS_LEAVE
                ),
            ],
            [
                InlineKeyboardButton(
                    BUTTON_JOBS_HISTORY, callback_data=callbacks.JOBS_HISTORY
                ),
            ],
            [
                InlineKeyboardButton(
                    BUTTON_BACK_TO_MAIN, callback_data=callbacks.BACK_TO_MAIN
                ),
            ],
        ]
    )


def build_jobs_list(jobs) -> InlineKeyboardMarkup:
    """Build list of available jobs with apply buttons."""
    rows = []
    for job in jobs:
        # job is JobData
        # Persian digits + the live hourly rate, same layout as before.
        btn_text = (
            f"{job.name} - {fa_int(job.hourly_salary)} تومان/ساعت "
            f"(لول {fa_int(job.required_level)})"
        )
        # Use callback with job id
        rows.append(
            [
                InlineKeyboardButton(
                    btn_text, callback_data=f"{callbacks.JOBS_APPLY_PREFIX}{job.id}"
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                f"🔙 بازگشت به منوی {constants.JOBS_SYSTEM_NAME}",
                callback_data=callbacks.JOBS_MENU,
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                BUTTON_BACK_TO_MAIN, callback_data=callbacks.BACK_TO_MAIN
            )
        ]
    )
    return InlineKeyboardMarkup(rows)
