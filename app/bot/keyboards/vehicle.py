"""Inline keyboards for 🚗 نمایشگاه ماشین حاج ممد."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards import callbacks
from app.bot.keyboards.main_menu import BUTTON_BACK_TO_MAIN
from app.bot.messages.formatters import money
from app.game.vehicle.catalog import VEHICLE_MODEL_AVAILABLE
from app.game.vehicle.dto import VehicleModelData, VehicleOwnershipData

BUTTON_VEHICLE_BACK: str = "🔙 نمایشگاه ماشین"
BUTTON_VEHICLE_BUY: str = "🚘 خرید ماشین"
BUTTON_VEHICLE_MY_CARS: str = "🚗 ماشین‌های من"


def build_vehicle_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    BUTTON_VEHICLE_BUY, callback_data=callbacks.VEHICLE_CATALOG
                ),
                InlineKeyboardButton(
                    BUTTON_VEHICLE_MY_CARS, callback_data=callbacks.VEHICLE_MY_CARS
                ),
            ],
            [InlineKeyboardButton(BUTTON_BACK_TO_MAIN, callback_data=callbacks.BACK_TO_MAIN)],
        ]
    )


def build_vehicle_catalog(
    models: list[VehicleModelData], *, page: int, page_size: int
) -> InlineKeyboardMarkup:
    safe_size = max(1, page_size)
    total_pages = max(1, (len(models) + safe_size - 1) // safe_size)
    safe_page = max(0, min(page, total_pages - 1))
    start = safe_page * safe_size
    current = models[start : start + safe_size]
    rows: list[list[InlineKeyboardButton]] = []
    for model in current:
        if model.availability_status == VEHICLE_MODEL_AVAILABLE:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"{model.name} — {money(model.purchase_price)}",
                        callback_data=f"{callbacks.VEHICLE_MODEL_PREFIX}{model.model_id}",
                    )
                ]
            )
        else:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"🔒 {model.name} — فعلاً موجود نیست",
                        callback_data=callbacks.VEHICLE_CATALOG,
                    )
                ]
            )

    navigation: list[InlineKeyboardButton] = []
    if safe_page > 0:
        navigation.append(
            InlineKeyboardButton(
                "⬅️ صفحه قبل",
                callback_data=f"{callbacks.VEHICLE_PAGE_PREFIX}{safe_page - 1}",
            )
        )
    if safe_page < total_pages - 1:
        navigation.append(
            InlineKeyboardButton(
                "➡️ صفحه بعد",
                callback_data=f"{callbacks.VEHICLE_PAGE_PREFIX}{safe_page + 1}",
            )
        )
    if navigation:
        rows.append(navigation)
    rows.extend(
        [
            [InlineKeyboardButton(BUTTON_VEHICLE_BACK, callback_data=callbacks.VEHICLE_MENU)],
            [InlineKeyboardButton(BUTTON_BACK_TO_MAIN, callback_data=callbacks.BACK_TO_MAIN)],
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_vehicle_model_detail(
    model: VehicleModelData, *, catalog_page: int
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if model.is_available:
        rows.append(
            [
                InlineKeyboardButton(
                    BUTTON_VEHICLE_BUY,
                    callback_data=f"{callbacks.VEHICLE_CONFIRM_PREFIX}{model.model_id}",
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    "🔙 فهرست ماشین‌ها",
                    callback_data=f"{callbacks.VEHICLE_PAGE_PREFIX}{max(0, catalog_page)}",
                )
            ],
            [InlineKeyboardButton(BUTTON_VEHICLE_BACK, callback_data=callbacks.VEHICLE_MENU)],
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_vehicle_confirmation(model: VehicleModelData) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ خرید",
                    callback_data=f"{callbacks.VEHICLE_CONFIRM_PREFIX}{model.model_id}:ok",
                ),
                InlineKeyboardButton(
                    "❌ انصراف",
                    callback_data=f"{callbacks.VEHICLE_MODEL_PREFIX}{model.model_id}",
                ),
            ],
            [InlineKeyboardButton(BUTTON_VEHICLE_BACK, callback_data=callbacks.VEHICLE_MENU)],
        ]
    )


def build_owned_vehicles(vehicles: list[VehicleOwnershipData]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for vehicle in vehicles:
        rows.append(
            [
                InlineKeyboardButton(
                    f"{vehicle.model.name} — {money(vehicle.purchase_price)}",
                    callback_data=f"{callbacks.VEHICLE_OWNED_PREFIX}{vehicle.ownership_id}",
                )
            ]
        )
    rows.extend(
        [
            [InlineKeyboardButton(BUTTON_VEHICLE_BUY, callback_data=callbacks.VEHICLE_CATALOG)],
            [InlineKeyboardButton(BUTTON_VEHICLE_BACK, callback_data=callbacks.VEHICLE_MENU)],
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_owned_vehicle_detail() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔙 ماشین‌های من", callback_data=callbacks.VEHICLE_MY_CARS)],
            [InlineKeyboardButton(BUTTON_VEHICLE_BACK, callback_data=callbacks.VEHICLE_MENU)],
        ]
    )
