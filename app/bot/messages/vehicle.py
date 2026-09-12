"""Persian player-facing texts for حاج ممد's car dealership."""

from __future__ import annotations

from datetime import datetime

from app.bot.messages.formatters import fa_int, money
from app.game.vehicle.catalog import VEHICLE_MODEL_AVAILABLE
from app.game.vehicle.dto import (
    VehicleModelData,
    VehicleOwnershipData,
    VehiclePurchaseResult,
)


def vehicle_menu_text() -> str:
    return (
        "🚗 نمایشگاه ماشین حاج ممد\n"
        "━━━━━━━━━━━━━━━\n"
        "اینجا می‌تونی از بین ماشین‌های آماده، ماشین مورد علاقه‌ات رو بخری.\n"
        "مدل جدید یا ماشین سفارشی توسط بازیکن ساخته نمی‌شه.\n\n"
        "یکی از گزینه‌های پایین رو انتخاب کن 👇"
    )


def vehicle_catalog_text(
    models: list[VehicleModelData], *, page: int, page_size: int
) -> str:
    safe_size = max(1, page_size)
    total_pages = max(1, (len(models) + safe_size - 1) // safe_size)
    safe_page = max(0, min(page, total_pages - 1))
    current = models[safe_page * safe_size : (safe_page + 1) * safe_size]
    lines = [
        "🚘 ماشین‌های موجود در نمایشگاه",
        "━━━━━━━━━━━━━━━",
        f"صفحه {fa_int(safe_page + 1)} از {fa_int(total_pages)}",
        "",
    ]
    if not current:
        lines.append("فعلاً مدلی برای نمایش وجود ندارد.")
    for model in current:
        status = "✅ موجود" if model.availability_status == VEHICLE_MODEL_AVAILABLE else "🔒 ناموجود"
        lines.append(f"🚗 {model.name} — {money(model.purchase_price)} — {status}")
    lines.append("")
    lines.append("برای دیدن جزئیات و ادامه خرید، روی مدل بزن 👇")
    return "\n".join(lines)


def vehicle_model_detail_text(model: VehicleModelData) -> str:
    status = "موجود ✅" if model.is_available else "فعلاً ناموجود 🔒"
    return (
        f"🚗 {model.name}\n"
        "━━━━━━━━━━━━━━━\n"
        f"💰 قیمت نمایشگاه: {money(model.purchase_price)}\n"
        f"📌 وضعیت: {status}\n\n"
        "این یک مدل از پیش تعریف‌شده نمایشگاه است."
    )


def purchase_confirmation_text(model: VehicleModelData) -> str:
    return (
        f"🚗 {model.name}\n\n"
        f"💰 قیمت: {money(model.purchase_price)}\n\n"
        "آیا مطمئنی که می‌خوای این ماشین رو بخری؟"
    )


def purchase_success_text(result: VehiclePurchaseResult) -> str:
    vehicle = result.ownership
    return (
        f"✅ خرید {vehicle.model.name} با موفقیت انجام شد!\n"
        "━━━━━━━━━━━━━━━\n"
        f"💰 مبلغ پرداخت‌شده: {money(vehicle.purchase_price)}\n"
        f"💳 موجودی فعلی کیف‌پول: {money(result.wallet_balance_after)}\n"
        "این ماشین به دارایی‌های تو اضافه شد. 🚗"
    )


def my_cars_text(vehicles: list[VehicleOwnershipData]) -> str:
    if not vehicles:
        return (
            "🚗 هنوز ماشینی نداری.\n\n"
            "از «🚘 خرید ماشین» یکی از مدل‌های نمایشگاه را انتخاب کن."
        )
    return (
        f"🚗 ماشین‌های من ({fa_int(len(vehicles))})\n"
        "━━━━━━━━━━━━━━━\n"
        "برای دیدن جزئیات هر ماشین روی آن بزن 👇"
    )


def owned_vehicle_detail_text(vehicle: VehicleOwnershipData) -> str:
    return (
        f"🚗 {vehicle.model.name}\n"
        "━━━━━━━━━━━━━━━\n"
        f"💰 قیمت خرید: {money(vehicle.purchase_price)}\n"
        f"📅 تاریخ خرید: {_format_datetime(vehicle.purchased_at)}\n"
        f"📌 وضعیت مالکیت: {'مالک هستی ✅' if vehicle.is_owned else 'غیرفعال'}"
    )


def _format_datetime(value: datetime) -> str:
    local = value
    return (
        f"{fa_int(local.year)}/{fa_int(local.month)}/{fa_int(local.day)} "
        f"{fa_int(local.hour)}:{fa_int(local.minute)}"
    )


def vehicle_model_not_found_text() -> str:
    return "این مدل ماشین معتبر نیست؛ فقط مدل‌های ثابت نمایشگاه قابل خرید هستند."


def vehicle_unavailable_text() -> str:
    return "این ماشین فعلاً در نمایشگاه موجود نیست."


def vehicle_invalid_price_text() -> str:
    return "قیمت این ماشین معتبر نیست؛ خرید انجام نشد."


def vehicle_already_owned_text() -> str:
    return "این مدل ماشین را از قبل داری؛ خرید تکراری انجام نشد."


def vehicle_limit_text() -> str:
    return "به سقف مالکیت ماشین رسیده‌ای و فعلاً ماشین بیشتری نمی‌توانی بخری."


def vehicle_not_owned_text() -> str:
    return "این ماشین متعلق به تو نیست یا دیگر فعال نیست."


def vehicle_purchase_error_text() -> str:
    return "خرید ماشین کامل نشد؛ هیچ مبلغی از کیف‌پولت کم نشده است. دوباره امتحان کن."


def vehicle_insufficient_funds_text() -> str:
    return "موجودی کیف‌پولت برای خرید این ماشین کافی نیست؛ خرید انجام نشد."
