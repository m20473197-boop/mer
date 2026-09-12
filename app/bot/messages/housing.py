"""Housing system player-facing Persian texts."""

from __future__ import annotations

from datetime import datetime, timezone

from app.bot.messages.formatters import fa_int, fa_year, money
from app.core import constants
from app.game.housing.dto import (
    EndContractResult,
    HouseInfoData,
    HouseMarketEntry,
    HouseRentalEntry,
    HouseData,
    ListForRentResult,
    ListForSaleResult,
    PlayerAssetsData,
    PurchaseResult,
    RentOptions,
    RentPaymentResult,
    RentalContractData,
    SaleOptions,
)

_YES = "دارد ✅"
_NO = "ندارد ❌"

_QUALITY_EMOJI = {
    "عالی": "🌟",
    "خوب": "👍",
    "متوسط": "😐",
    "ضعیف": "⚠️",
}

_KITCHEN_EMOJI = {
    "مدرن": "✨",
    "معمولی": "🍽️",
    "قدیمی": "🧱",
}

_LISTING_TYPE_LABELS = {
    "sale": "فروش",
    "rent": "اجاره",
}


def housing_menu_text() -> str:
    return (
        "🏠 منوی خانه و ملک:\n\n"
        "می‌تونی خانه بخری، بفروشی، اجاره بدهی، زمین بخری، روش ساختمان بسازی و خونه‌ات رو بازسازی کنی.\n"
        "قیمت همه خانه‌ها با قیمت‌گذاری پویا از روی شهر، محله، متراژ، سال ساخت و امکانات حساب می‌شه.\n"
        "یکی از گزینه‌های پایین رو انتخاب کن 👇"
    )


def house_card(house: HouseData) -> str:
    """The realistic property list of one house."""
    card = (
        f"🏙️ شهر: {house.city}\n"
        f"📍 محله: {house.neighborhood}\n"
        f"📐 متراژ: {fa_int(house.area_sqm)} متر مربع\n"
        f"🛏️ خواب: {fa_int(house.bedrooms)}\n"
        f"🛋️ نشیمن: {fa_int(house.living_rooms)}\n"
        f"🚿 سرویس بهداشتی: {fa_int(house.bathrooms)}\n"
        f"{_KITCHEN_EMOJI.get(house.kitchen_type, '🍽️')} آشپزخانه: {house.kitchen_type}\n"
        f"📅 سال ساخت: {fa_year(house.construction_year)}\n"
        f"🚗 پارکینگ: {_YES if house.parking else _NO}\n"
        f"🛗 آسانسور: {_YES if house.elevator else _NO}\n"
        f"📦 انباری: {_YES if house.storage else _NO}\n"
        f"{_QUALITY_EMOJI.get(house.quality, '🏠')} کیفیت: {house.quality}"
    )
    if house.price_override_per_mille:
        percent = house.price_override_per_mille / 10
        pretty = f"{percent:.1f}".rstrip("0").rstrip(".")
        pretty_fa = pretty.translate(str.maketrans("0123456789.", "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9/"))
        card += f"\n\U0001f4b9 \u0636\u0631\u06cc\u0628 \u0642\u06cc\u0645\u062a \u0645\u062f\u06cc\u0631\u06cc\u062a\u06cc: \u066a{pretty_fa}"
    return card


def _duration_days(delta_days: int) -> str:
    return f"{fa_int(delta_days)} روز"


def my_houses_text(assets: PlayerAssetsData) -> str:
    if not assets.houses:
        return (
            "هنوز خانه‌ای نداری. 🏚️\n"
            "از «🏘️ بازار مسکن» شروع کن — اولین خونه‌ات منتظرته!"
        )
    lines = [
        f"🏠 خانه‌های تو ({fa_int(len(assets.houses))} ملک):",
        "━━━━━━━━━━━━━━━",
    ]
    for house in assets.houses:
        lines.append(f"• {house.city}، {house.neighborhood} — {fa_int(house.area_sqm)} متری")
    lines.append("")
    lines.append(f"💰 ارزش کل دارایی ملکی: {money(assets.total_market_value)}")

    sale_ids = {l.house_id for l in assets.active_sale_listings}
    rent_ids = {l.house_id for l in assets.active_rent_listings}
    rented = {c.house_id for c in assets.rented_out_contracts}
    for house in assets.houses:
        if house.id in sale_ids:
            lines.append(f"🏷️ خانه #{fa_int(house.id)} آگهی فروش فعال دارد")
        if house.id in rent_ids:
            lines.append(f"🔑 خانه #{fa_int(house.id)} آگهی اجاره فعال دارد")
        if house.id in rented:
            lines.append(f"🧑‍🤝‍🧑 خانه #{fa_int(house.id)} اجاره داده شده")

    lines.append("")
    lines.append("برای مدیریت هر خانه، روی دکمه‌های پایین بزن 👇")
    return "\n".join(lines)


def market_text(entries: list[HouseMarketEntry]) -> str:
    if not entries:
        return (
            "فعلاً خانه‌ای برای فروش نیست. 🏚️\n"
            "بعداً سر بزن یا خودت خانه‌ات را بفروش!"
        )
    lines = [
        f"🏘️ خانه‌های موجود برای خرید ({fa_int(len(entries))}):",
        "━━━━━━━━━━━━━━━",
    ]
    for entry in entries[:12]:
        seller = (
            f"فروشنده: {entry.seller_name}"
            if entry.seller_name
            else "بازار سیستم (بانک/سازنده)"
        )
        diff = ""
        if entry.seller_player_id is not None:
            if entry.price > entry.market_value:
                diff = " — گرون‌تر از ارزش ⬆️"
            elif entry.price < entry.market_value:
                diff = " — ارزون‌تر از ارزش ⬇️"
        lines.append(
            f"• #{fa_int(entry.house.id)} {entry.house.city}، {entry.house.neighborhood} — "
            f"{fa_int(entry.house.area_sqm)} متری، {entry.house.quality}\n"
            f"  💵 قیمت: {money(entry.price)}{diff}\n"
            f"  👤 {seller}"
        )
    lines.append("")
    lines.append("برای اطلاعات کامل و خرید، روی دکمه‌ها بزن 👇")
    return "\n".join(lines)


def rentals_text(entries: list[HouseRentalEntry]) -> str:
    if not entries:
        return (
            "فعلاً خانه‌ای برای اجاره نیست. 🔑\n"
            "بعداً سر بزن — یا اگه خانه داری، خودت اجاره بده!"
        )
    lines = [
        f"🛏️ خانه‌های موجود برای اجاره ({fa_int(len(entries))}):",
        "━━━━━━━━━━━━━━━",
    ]
    for entry in entries[:12]:
        deposit_part = (
            f" + رهن {money(entry.deposit)}" if entry.deposit > 0 else " (بدون رهن)"
        )
        lines.append(
            f"• #{fa_int(entry.house.id)} {entry.house.city}، {entry.house.neighborhood} — "
            f"{fa_int(entry.house.area_sqm)} متری\n"
            f"  💵 اجاره ماهانه: {money(entry.monthly_rent)}{deposit_part}\n"
            f"  👤 صاحبخانه: {entry.owner_name}"
        )
    lines.append("")
    lines.append("برای اطلاعات کامل و اجاره، روی دکمه‌ها بزن 👇")
    return "\n".join(lines)


def house_info_text(info: HouseInfoData) -> str:
    house = info.house
    lines = [f"🏠 خانه #{fa_int(house.id)}", "━━━━━━━━━━━━━━━"]
    lines.append(house_card(house))
    lines.append("━━━━━━━━━━━━━━━")
    lines.append(f"💰 ارزش لحظه‌ای بازار: {money(info.market_value)}")
    lines.append(f"🔑 اجاره تقریبی ماهانه: {money(info.estimated_rent)}")

    if house.owner_player_id is None:
        lines.append("📍 وضعیت: در بازار سیستم (بدون صاحب)")
    else:
        lines.append(f"👤 مالک: {info.owner_name or 'نامشخص'}")

    if info.active_sale_price is not None:
        lines.append(f"🏷️ آگهی فروش فعال: {money(info.active_sale_price)}")
    if info.active_rent is not None:
        rent, deposit = info.active_rent
        deposit_part = f" + رهن {money(deposit)}" if deposit > 0 else " (بدون رهن)"
        lines.append(f"🔑 آگهی اجاره فعال: {money(rent)} در ماه{deposit_part}")
    if info.tenant_name is not None:
        lines.append(f"🧑‍🤝‍🧑 مستأجر فعلی: {info.tenant_name}")

    return "\n".join(lines)


def buy_confirmation_text(info: HouseInfoData) -> str:
    house = info.house
    seller = info.owner_name or "بازار سیستم (بانک/سازنده)"
    price = info.active_sale_price if info.active_sale_price is not None else info.market_value
    lines = [
        "🛒 تأیید خرید خانه",
        "━━━━━━━━━━━━━━━",
        house_card(house),
        "━━━━━━━━━━━━━━━",
        f"👤 فروشنده: {seller}",
        f"💵 مبلغ خرید: {money(price)}",
        "",
        "مطمئنی؟ با تأیید، پول از کیف‌پولت کم می‌شه و خانه مال تو می‌شه.",
    ]
    return "\n".join(lines)


def rent_confirmation_text(entry: HouseRentalEntry) -> str:
    lines = [
        "🔑 تأیید اجاره خانه",
        "━━━━━━━━━━━━━━━",
        house_card(entry.house),
        "━━━━━━━━━━━━━━━",
        f"👤 صاحبخانه: {entry.owner_name}",
        f"💵 اجاره ماهانه: {money(entry.monthly_rent)}",
        (
            f"📦 رهن (بلافاصله پرداخت می‌شه): {money(entry.deposit)}"
            if entry.deposit > 0
            else "📦 رهن: بدون رهن"
        ),
        "",
        "با تأیید، قرارداد اجاره رسمی می‌شه و رهن از کیف‌پولت کم می‌شه.",
    ]
    return "\n".join(lines)


def purchased_text(result: PurchaseResult, buyer_name: str = "") -> str:
    seller_part = (
        "از بازیکن دیگر خریدی ✅"
        if result.seller_player_id is not None
        else "از بازار سیستم خریدی ✅"
    )
    lines = [
        "🎉 تبریک! صاحب‌خانه شدی!",
        "━━━━━━━━━━━━━━━",
        house_card(result.house),
        "━━━━━━━━━━━━━━━",
        f"💵 مبلغ پرداخت‌شده: {money(result.price)}",
        f"🧾 {seller_part}",
        f"💳 موجودی فعلی: {money(result.balance_after)}",
    ]
    if result.xp_granted > 0:
        lines.append(f"✨ پاداش خرید: +{fa_int(result.xp_granted)} XP")
    lines.append("")
    lines.append("این خانه الان جزو دارایی‌هات حساب می‌شه 🏠")
    return "\n".join(lines)


def sale_options_text(options: SaleOptions) -> str:
    lines = [
        "🏷️ فروش خانه — قیمت رو انتخاب کن:",
        "━━━━━━━━━━━━━━━",
        f"💰 ارزش لحظه‌ای بازار: {money(options.market_value)}",
        "",
        "قیمت‌های پیشنهادی بر اساس ارزش لحظه‌ای محاسبه شدن 👇",
    ]
    return "\n".join(lines)


def rent_options_text(options: RentOptions) -> str:
    lines = [
        "🔑 اجاره‌دادن خانه — رهن و اجاره رو انتخاب کن:",
        "━━━━━━━━━━━━━━━",
        f"💰 ارزش لحظه‌ای بازار: {money(options.market_value)}",
        "",
        "هرچی رهن بیشتر باشه، اجاره ماهانه کمتر می‌شه 👇",
    ]
    return "\n".join(lines)


def listed_for_sale_text(result: ListForSaleResult) -> str:
    return (
        f"🏷️ خانه #{fa_int(result.house.id)} ({result.house.city}، "
        f"{result.house.neighborhood}) به قیمت {money(result.price)} برای فروش آگهی شد.\n"
        f"💰 ارزش لحظه‌ای بازار: {money(result.market_value)}\n"
        "بازیکن‌های دیگه الان می‌تونن از «🏘️ بازار مسکن» بخرنش."
    )


def listed_for_rent_text(result: ListForRentResult) -> str:
    deposit_part = (
        f"\n📦 رهن: {money(result.deposit)}" if result.deposit > 0 else "\n📦 رهن: بدون رهن"
    )
    return (
        f"🔑 خانه #{fa_int(result.house.id)} ({result.house.city}، "
        f"{result.house.neighborhood}) برای اجاره آگهی شد.\n"
        f"💵 اجاره ماهانه: {money(result.monthly_rent)}{deposit_part}\n"
        "بازیکن‌های دیگه الان می‌تونن از «🛏️ خانه‌های اجاره‌ای» بگیرنش."
    )


def listing_cancelled_text(listing_type: str, house: HouseData) -> str:
    kind = _LISTING_TYPE_LABELS.get(listing_type, listing_type)
    return (
        f"❌ آگهی {kind} خانه #{fa_int(house.id)} ({house.city}، "
        f"{house.neighborhood}) لغو شد."
    )


def contract_text(contract: RentalContractData, *, viewer_is_tenant: bool) -> str:
    counterpart = contract.owner_name if viewer_is_tenant else contract.tenant_name
    role = "صاحبخانه" if viewer_is_tenant else "مستأجر"
    lines = [
        f"📜 قرارداد اجاره #{fa_int(contract.id)}",
        "━━━━━━━━━━━━━━━",
        f"🏠 خانه: {contract.house_label}",
        f"👤 {role}: {counterpart}",
        f"💵 اجاره ماهانه: {money(contract.monthly_rent)}",
    ]
    if contract.deposit > 0:
        lines.append(f"📦 رهن پرداخت‌شده: {money(contract.deposit)}")
    days_left = max(
        0,
        (
            contract.next_due_at.replace(tzinfo=None) - _utcnow_naive()
        ).days,
    )
    if days_left <= 0:
        lines.append("⏰ اجاره این ماه سرسید شده — پرداخت کن!")
    else:
        lines.append(f"⏳ تا سرسید اجاره بعدی: {_duration_days(days_left)}")
    return "\n".join(lines)


def my_rents_text(contracts: list[RentalContractData]) -> str:
    if not contracts:
        return (
            "هنوز قرارداد اجاره‌ای نداری. 📭\n"
            "از «🛏️ خانه‌های اجاره‌ای» می‌تونی خونه اجاره کنی."
        )
    lines = [
        f"📜 قراردادهای اجاره تو ({fa_int(len(contracts))}):",
        "━━━━━━━━━━━━━━━",
    ]
    for contract in contracts:
        lines.append(
            f"• قرارداد #{fa_int(contract.id)} — {contract.house_label}\n"
            f"  👤 صاحبخانه: {contract.owner_name}\n"
            f"  💵 اجاره ماهانه: {money(contract.monthly_rent)}"
        )
    lines.append("")
    lines.append("با دکمه‌های پایین اجاره بده یا قرارداد رو تموم کن 👇")
    return "\n".join(lines)


def rent_paid_text(result: RentPaymentResult) -> str:
    return (
        "💵 اجاره پرداخت شد!\n"
        f"🏠 خانه #{fa_int(result.house_id)}\n"
        f"💰 مبلغ: {money(result.amount)}\n"
        f"💳 موجودی تو: {money(result.tenant_balance_after)}\n"
        f"📅 سرسید اجاره بعدی: {result.next_due_at.strftime('%Y-%m-%d')}"
    )


def contract_ended_text(result: EndContractResult, house_label: str) -> str:
    return (
        f"⏹ قرارداد اجاره #{fa_int(result.contract_id)} برای "
        f"{house_label} تمام شد.\n"
        "خونه به صاحبش برگشت. 🏠"
    )


def _utcnow_naive() -> datetime:
    """Naive-UTC now (matches how SQLite datetimes are read back)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --- Error texts (translated from service domain errors) -----------------------


def house_not_found_text() -> str:
    return "این خانه پیدا نشد — شاید همین الان فروخته شده. 🔍"


def not_owner_text() -> str:
    return "این خانه مال تو نیست! 🚫"


def house_not_available_text() -> str:
    return "این خانه دیگه تو بازار نیست — یکی زودتر از تو خریدش! 😅"


def not_listed_for_sale_text() -> str:
    return "این خانه الان آگهی فروش نداره. 🏷️"


def not_listed_for_rent_text() -> str:
    return "این خانه الان آگهی اجاره نداره. 🔑"


def already_listed_text() -> str:
    return "این خانه یه آگهی فعال داره — اول اون رو لغو کن. ⚠️"


def rented_out_text() -> str:
    return "این خونه مستأجر داره — اول قرارداد رو تموم کن. 🧑‍🤝‍🧑"


def price_out_of_bounds_text() -> str:
    return "این قیمت از محدوده مجاز بازار بیرونه — از گزینه‌های پیشنهادی استفاده کن. ⚠️"


def cannot_buy_own_text() -> str:
    return "این خانه از قبل مال خودته! 😄"


def cannot_rent_own_text() -> str:
    return "نمی‌تونی خونه خودتو از خودت اجاره کنی! 😄"


def already_renting_text() -> str:
    return "الان یه خونه اجاره‌ای داری — اول قراردادش رو تموم کن. 📜"


def contract_not_found_text() -> str:
    return "این قرارداد پیدا نشد یا قبلاً تموم شده. 📭"


def not_contract_party_text() -> str:
    return "این قرارداد مال تو نیست! 🚫"


def insufficient_funds_text() -> str:
    return (
        "پول کافی نداری! 💸\n"
        f"با 💼 {constants.JOBS_SYSTEM_NAME} درآمد بساز و برگرد."
    )
