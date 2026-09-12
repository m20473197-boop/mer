"""Inline keyboards for the Persian 🕳️ خلاف screens."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards import callbacks


def build_crime_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🕵️ اطلاعات‌فروشی", callback_data=callbacks.CRIME_INFORMATION),
                InlineKeyboardButton("💰 پول‌شویی", callback_data=callbacks.CRIME_LAUNDERING),
            ],
            [
                InlineKeyboardButton("🪪 مدارک جعلی", callback_data=callbacks.CRIME_DOCUMENTS),
                InlineKeyboardButton("🏎️ شوتی", callback_data=callbacks.CRIME_SHOTI),
            ],
            [
                InlineKeyboardButton(
                    "💻 هک و نفوذ به حساب بانکی کاربران",
                    callback_data=callbacks.CRIME_BANK_HACK,
                )
            ],
            [
                InlineKeyboardButton("📜 تاریخچه خلاف", callback_data=callbacks.CRIME_HISTORY),
                InlineKeyboardButton("🔙 منوی اصلی", callback_data=callbacks.BACK_TO_MAIN),
            ],
        ]
    )


def build_crime_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ انصراف", callback_data=callbacks.CRIME_CANCEL)]]
    )


def build_document_menu(definitions, active_types: set[str] | None = None) -> InlineKeyboardMarkup:
    active_types = active_types or set()
    rows = []
    for definition in definitions:
        suffix = " ✅" if definition.code in active_types else ""
        rows.append(
            [
                InlineKeyboardButton(
                    f"{definition.name}{suffix}",
                    callback_data=f"{callbacks.CRIME_DOCUMENT_PREFIX}{definition.code}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton("🔙 بازگشت به خلاف", callback_data=callbacks.CRIME_MENU)]
    )
    return InlineKeyboardMarkup(rows)


def build_shoti_vehicle_menu(vehicles) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"{vehicle.model.name} · شناسه {vehicle.ownership_id}",
                callback_data=f"{callbacks.CRIME_SHOTI_VEHICLE_PREFIX}{vehicle.ownership_id}",
            )
        ]
        for vehicle in vehicles
    ]
    rows.append(
        [InlineKeyboardButton("📜 وضعیت مأموریت‌ها", callback_data=callbacks.CRIME_SHOTI_HISTORY)]
    )
    rows.append(
        [InlineKeyboardButton("🔙 بازگشت به خلاف", callback_data=callbacks.CRIME_MENU)]
    )
    return InlineKeyboardMarkup(rows)


def build_crime_history() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("💰 وضعیت پول‌شویی", callback_data=callbacks.CRIME_LAUNDERING_HISTORY),
                InlineKeyboardButton("🏎️ وضعیت شوتی", callback_data=callbacks.CRIME_SHOTI_HISTORY),
            ],
            [InlineKeyboardButton("🔙 بازگشت به خلاف", callback_data=callbacks.CRIME_MENU)],
        ]
    )
