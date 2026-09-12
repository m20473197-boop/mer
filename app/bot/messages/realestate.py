"""Land / Construction / Renovation player-facing Persian texts."""

from __future__ import annotations

from app.bot.messages.formatters import fa_int, fa_year, money
from app.core import constants
from app.game.realestate.dto import (
    ConstructionCancelResult,
    ConstructionProjectData,
    ConstructionStartResult,
    LandInfoData,
    LandMarketEntry,
    LandPurchaseResult,
    LandWithStatus,
    PlayerLandsData,
    ProjectsStatusData,
    RenovationProjectData,
    RenovationStartResult,
)
from app.game.realestate.renovation import RenovationOption

_YES = "دارد ✅"
_NO = "ندارد ❌"


def lands_market_text(entries: list[LandMarketEntry]) -> str:
    if not entries:
        return "فعلاً زمینی برای فروش نیست. 🌍\nبعداً سر بزن!"
    lines = [
        f"🌍 زمین‌های موجود برای خرید ({fa_int(len(entries))}):",
        "━━━━━━━━━━━━━━━",
    ]
    for entry in entries[:12]:
        lines.append(
            f"• #{fa_int(entry.land.id)} {entry.land.city}، {entry.land.neighborhood} — "
            f"{fa_int(entry.land.area_sqm)} متری\n"
            f"  📍 کیفیت موقعیت: {entry.land.location_quality}\n"
            f"  💵 قیمت: {money(entry.price)} ({money(entry.price_per_sqm)} هر متر)"
        )
    lines.append("")
    lines.append("قیمت‌ها لحظه‌ای و بر اساس بازار حساب می‌شن 👇")
    return "\n".join(lines)


def _land_sheet(item: LandWithStatus | LandInfoData) -> str:
    land = item.land
    lines = [
        f"🌍 زمین #{fa_int(land.id)}",
        "━━━━━━━━━━━━━━━",
        f"🏙️ شهر: {land.city}",
        f"📍 محله: {land.neighborhood}",
        f"📐 مساحت: {fa_int(land.area_sqm)} متر مربع",
        f"⭐ کیفیت موقعیت: {land.location_quality}",
    ]
    if land.price_override_per_mille:
        percent = land.price_override_per_mille / 10
        pretty = f"{percent:.1f}".rstrip("0").rstrip(".")
        pretty_fa = pretty.translate(str.maketrans("0123456789.", "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9/"))
        lines.append(f"\U0001f4b9 \u0636\u0631\u06cc\u0628 \u0642\u06cc\u0645\u062a \u0645\u062f\u06cc\u0631\u06cc\u062a\u06cc: \u066a{pretty_fa}")
    return "\n".join(lines)


def land_info_text(info: LandInfoData) -> str:
    lines = [_land_sheet(info), "━━━━━━━━━━━━━━━"]
    lines.append(f"💰 ارزش لحظه‌ای: {money(info.market_value)}")
    lines.append(f"💵 قیمت هر متر: {money(info.price_per_sqm)}")

    if info.land.owner_player_id is None:
        lines.append("📍 وضعیت: در بازار سیستم (بدون صاحب)")
    else:
        lines.append(f"👤 مالک: {info.owner_name or 'نامشخص'}")

    if info.active_construction is not None:
        project = info.active_construction
        lines.append(
            f"🏗️ در حال ساخت: {project.building_type_label} "
            f"{fa_int(project.area_sqm)} متری، {fa_int(project.floors)} طبقه — "
            f"{fa_int(int(project.progress_percent))}٪"
        )
    elif info.built_house is not None:
        lines.append(f"🏠 خانه ساخته‌شده: #{fa_int(info.built_house.id)}")
    elif info.land.owner_player_id is not None:
        lines.append("📍 وضعیت: زمین خالی — آماده ساخت")
    return "\n".join(lines)


def land_buy_confirmation_text(info: LandInfoData) -> str:
    return (
        "🛒 تأیید خرید زمین\n"
        "━━━━━━━━━━━━━━━\n"
        + _land_sheet(info)
        + "\n━━━━━━━━━━━━━━━\n"
        + f"💵 مبلغ خرید: {money(info.market_value)}\n\n"
        + "مطمئنی؟ با تأیید، پول از کیف‌پولت کم می‌شه و زمین مال تو می‌شه."
    )


def land_purchased_text(result: LandPurchaseResult) -> str:
    return (
        "🎉 تبریک! صاحب زمین شدی!\n"
        "━━━━━━━━━━━━━━━\n"
        + _land_sheet(
            LandWithStatus(land=result.land, market_value=result.price, active_construction=None)
        )
        + "\n━━━━━━━━━━━━━━━\n"
        + f"💵 مبلغ پرداخت‌شده: {money(result.price)}\n"
        + f"💳 موجودی فعلی: {money(result.balance_after)}\n\n"
        + "از «🏗️ ساخت خانه» می‌تونی روی زمینت ساختمان بسازی."
    )


def my_lands_text(assets: PlayerLandsData) -> str:
    if not assets.lands:
        return (
            "هنوز زمینی نداری. 🌍\n"
            "از «🛒 خرید زمین» شروع کن — زمین پایه‌ی هر ملکه!"
        )
    lines = [
        f"🌍 زمین‌های تو ({fa_int(len(assets.lands))} قطعه):",
        "━━━━━━━━━━━━━━━",
    ]
    for item in assets.lands:
        land = item.land
        if item.active_construction is not None:
            status = (
                f"🏗️ در حال ساخت ({fa_int(int(item.active_construction.progress_percent))}٪)"
            )
        elif land.built_house_id is not None:
            status = f"🏠 ساخته‌شده — خانه #{fa_int(land.built_house_id)}"
        else:
            status = "🟢 خالی — آماده ساخت"
        lines.append(
            f"• #{fa_int(land.id)} {land.city}، {land.neighborhood} — "
            f"{fa_int(land.area_sqm)} متری ({land.location_quality})\n"
            f"  💰 ارزش: {money(item.market_value)} — {status}"
        )
    lines.append("")
    lines.append(f"💰 ارزش کل زمین‌های تو: {money(assets.total_market_value)}")
    lines.append("برای مدیریت هر زمین، روی دکمه‌های پایین بزن 👇")
    return "\n".join(lines)


# --- Construction blueprint flow -------------------------------------------------


def _land_header(land) -> str:
    return (
        f"🌍 زمین #{fa_int(land.id)} — {land.city}، {land.neighborhood} "
        f"({fa_int(land.area_sqm)} متری، {land.location_quality})"
    )


def build_type_text(land) -> str:
    return (
        "🏗️ ساخت خانه — قدم ۱ از ۶\n"
        "━━━━━━━━━━━━━━━\n"
        + _land_header(land)
        + "\n\nنوع ساخت‌وساز رو انتخاب کن:\n"
        "• آپارتمانی: ۲ تا ۴ طبقه، آسانسور داره\n"
        "• ویلایی: تک‌طبقه، بدون آسانسور"
    )


def build_floors_text(land) -> str:
    return (
        "🏗️ ساخت خانه — قدم ۲ از ۶: تعداد طبقات\n"
        "━━━━━━━━━━━━━━━\n"
        + _land_header(land)
    )


def build_size_text(land, floors: int) -> str:
    return (
        "🏗️ ساخت خانه — قدم ۳ از ۶: متراژ ساختمان\n"
        "━━━━━━━━━━━━━━━\n"
        + _land_header(land)
        + f"\n🏢 طبقات: {fa_int(floors)}\n\n"
        "متراژ کل ساختمان (مجموع همه طبقات) رو انتخاب کن:"
    )


def build_bedrooms_text(land, floors: int, area: int) -> str:
    return (
        "🏗️ ساخت خانه — قدم ۴ از ۶: تعداد اتاق‌ها\n"
        "━━━━━━━━━━━━━━━\n"
        + _land_header(land)
        + f"\n🏢 طبقات: {fa_int(floors)} — 📐 متراژ: {fa_int(area)} متر\n\n"
        "تعداد اتاق‌های خواب رو انتخاب کن:"
    )


def build_quality_text(land, floors: int, area: int, bedrooms: int) -> str:
    return (
        "🏗️ ساخت خانه — قدم ۵ از ۶: کیفیت مصالح\n"
        "━━━━━━━━━━━━━━━\n"
        + _land_header(land)
        + f"\n🏢 {fa_int(floors)} طبقه — 📐 {fa_int(area)} متر — 🛏️ {fa_int(bedrooms)} اتاق\n\n"
        "درجه مصالح رو انتخاب کن (روی هزینه و کیفیت اثر داره):"
    )


def build_facilities_text(land, floors: int, area: int, bedrooms: int, quality: str) -> str:
    return (
        "🏗️ ساخت خانه — قدم ۶ از ۶: امکانات\n"
        "━━━━━━━━━━━━━━━\n"
        + _land_header(land)
        + f"\n🏢 {fa_int(floors)} طبقه — 📐 {fa_int(area)} متر — "
        f"🛏️ {fa_int(bedrooms)} اتاق — ⭐ {quality}\n\n"
        "سطح امکانات رو انتخاب کن:"
    )


def construction_confirm_text(land, spec, cost: int, duration_seconds: int) -> str:
    facilities = "پارکینگ" if spec.parking else ""
    if spec.elevator:
        facilities += (" + " if facilities else "") + "آسانسور"
    if spec.storage:
        facilities += (" + " if facilities else "") + "انباری"
    if not facilities:
        facilities = "ندارد"
    return (
        "📋 شناسنامه ساخت — بررسی نهایی\n"
        "━━━━━━━━━━━━━━━\n"
        + _land_header(land) + "\n"
        + f"🏢 نوع: {spec.building_type_label} — {fa_int(spec.floors)} طبقه\n"
        + f"📐 متراژ کل: {fa_int(spec.area_sqm)} متر (هر طبقه ≈ {fa_int(spec.footprint_sqm)} متر)\n"
        + f"🛏️ اتاق خواب: {fa_int(spec.bedrooms)} — 🛋️ نشیمن: "
        + f"{fa_int(1 if spec.area_sqm < 150 else 2)} — 🚿 سرویس: "
        + f"{fa_int(2 if spec.bedrooms > 2 else 1)}"
        + (" (یا بیشتر در متراژ بالا)" if spec.area_sqm >= 180 else "")
        + "\n"
        + f"⭐ کیفیت: {spec.quality} — 🍽️ آشپزخانه: {spec.kitchen_type}\n"
        + f"🅿️ امکانات: {facilities}\n"
        + "━━━━━━━━━━━━━━━\n"
        + f"💵 هزینه ساخت: {money(cost)} (الان از کیف‌پول کم می‌شه)\n"
        + f"⏱️ مدت ساخت: {_format_duration(duration_seconds)}\n\n"
        + "با تأیید، ساخت شروع می‌شه و تا پایان، زمین درگیر می‌مونه."
    )


def construction_started_text(result: ConstructionStartResult) -> str:
    project = result.project
    return (
        "🏗️ ساخت‌وساز شروع شد!\n"
        "━━━━━━━━━━━━━━━\n"
        + f"🌍 زمین: {result.land.city}، {result.land.neighborhood}\n"
        + f"🏢 {project.building_type_label} — {fa_int(project.floors)} طبقه — "
        + f"{fa_int(project.area_sqm)} متر\n"
        + f"💵 هزینه: {money(result.cost)}\n"
        + f"⏱️ مدت ساخت: {_format_duration(project.seconds_remaining or 0)}\n"
        + f"💳 موجودی فعلی: {money(result.balance_after)}\n\n"
        + "پیشرفت ساخت رو از «📈 وضعیت ساخت» دنبال کن."
    )


def _progress_bar(percent: float) -> str:
    filled = int(percent // 10)
    bar = "▓" * filled + "░" * (10 - filled)
    return f"{bar} {fa_int(int(percent))}٪"


def _format_duration(seconds: int) -> str:
    days = int(seconds // 86400)
    hours = int(seconds % 86400 // 3600)
    minutes = int(seconds % 3600 // 60)
    if days > 0 and hours > 0:
        return f"{fa_int(days)} روز و {fa_int(hours)} ساعت"
    if days > 0:
        return f"{fa_int(days)} روز"
    if hours > 0 and minutes > 0:
        return f"{fa_int(hours)} ساعت و {fa_int(minutes)} دقیقه"
    if hours > 0:
        return f"{fa_int(hours)} ساعت"
    if minutes > 0:
        return f"{fa_int(minutes)} دقیقه"
    return "کمتر از یک دقیقه"


_STATUS_LABELS = {
    "in_progress": "🏗️ در حال ساخت",
    "completed": "✅ تکمیل شده",
    "cancelled": "❌ لغو شده",
}


def construction_line(project: ConstructionProjectData) -> str:
    lines = [
        f"🏗️ پروژه #{fa_int(project.id)} — {project.land_label or 'زمین'}",
        f"  🏢 {project.building_type_label} — {fa_int(project.floors)} طبقه — "
        f"{fa_int(project.area_sqm)} متر — {fa_int(project.bedrooms)} اتاق — {project.quality}",
        f"  💰 {_STATUS_LABELS.get(project.status, project.status)}",
    ]
    if project.status == "in_progress":
        lines.append(f"  {_progress_bar(project.progress_percent)}")
        lines.append(
            f"  ⏳ زمان باقی‌مانده: {_format_duration(project.seconds_remaining or 0)}"
        )
    elif project.status == "completed" and project.house_id is not None:
        lines.append(f"  🏠 خانه آماده: #{fa_int(project.house_id)}")
    return "\n".join(lines)


def renovation_line(project: RenovationProjectData) -> str:
    lines = [
        f"🛠️ {project.title} — خانه #{fa_int(project.house_id)}",
        f"  📝 {project.description}",
        f"  💰 هزینه: {money(project.cost)}",
    ]
    if project.status == "in_progress":
        lines.append(f"  {_progress_bar(project.progress_percent)}")
        lines.append(
            f"  ⏳ زمان باقی‌مانده: {_format_duration(project.seconds_remaining or 0)}"
        )
    else:
        lines.append("  ✅ تکمیل شده — ارزش خانه به‌روز شد")
    return "\n".join(lines)


def status_text(status: ProjectsStatusData) -> str:
    if not status.constructions and not status.renovations:
        return (
            "هنوز پروژه‌ای نداری. 🏗️\n"
            "از «🏗️ ساخت خانه» یه ساختمان بزن یا از «🛠️ بازسازی خانه» "
            "خونه‌ات رو نو کن."
        )
    lines = ["📈 وضعیت پروژه‌های تو:", "━━━━━━━━━━━━━━━"]
    if status.constructions:
        lines.append("🏗️ ساخت‌وسازها:")
        lines.extend(construction_line(p) for p in status.constructions)
        lines.append("")
    if status.renovations:
        lines.append("🛠️ بازسازی‌ها:")
        lines.extend(renovation_line(p) for p in status.renovations)
    return "\n".join(lines)


def construction_cancelled_text(result: ConstructionCancelResult) -> str:
    return (
        f"❌ پروژه ساخت #{fa_int(result.project_id)} لغو شد.\n"
        f"💸 {fa_int(70)}٪ هزینه برگشت: {money(result.refund)}\n"
        f"💳 موجودی فعلی: {money(result.balance_after)}\n"
        "زمین آزاد شد و می‌تونی دوباره روش بسازی."
    )


def renovatable_houses_text(houses, value_of) -> str:
    if not houses:
        return (
            "خانه‌ای برای بازسازی نداری. 🛠️\n"
            "اول از «🏘️ بازار مسکن» یه خانه بخر یا خودت بساز!"
        )
    lines = [
        "🛠️ بازسازی خانه — کدوم خانه؟",
        "━━━━━━━━━━━━━━━",
    ]
    for house in houses:
        lines.append(
            f"• #{fa_int(house.id)} {house.city}، {house.neighborhood} — "
            f"{fa_int(house.area_sqm)} متری ({house.quality}) — "
            f"ارزش: {money(value_of(house))}"
        )
    lines.append("")
    lines.append("یکی رو انتخاب کن 👇")
    return "\n".join(lines)


def renovation_options_text(house, value: int) -> str:
    return (
        "🛠️ بازسازی خانه\n"
        "━━━━━━━━━━━━━━━\n"
        f"🏠 #{fa_int(house.id)} {house.city}، {house.neighborhood} — "
        f"{fa_int(house.area_sqm)} متری\n"
        f"⭐ کیفیت: {house.quality} — 🍽️ آشپزخانه: {house.kitchen_type} — "
        f"📅 سال ساخت: {fa_year(house.construction_year)}\n"
        f"🚗 پارکینگ: {_YES if house.parking else _NO} — "
        f"🛗 آسانسور: {_YES if house.elevator else _NO} — "
        f"📦 انباری: {_YES if house.storage else _NO}\n"
        "━━━━━━━━━━━━━━━\n"
        f"💰 ارزش لحظه‌ای: {money(value)}\n\n"
        "گزینه‌های بازسازی (هزینه · مدت) 👇\n"
        "بعد از تکمیل، ارزش خانه بیشتر می‌شه."
    )


def renovation_confirm_text(option: RenovationOption, value: int) -> str:
    return (
        "🛠️ تأیید بازسازی\n"
        "━━━━━━━━━━━━━━━\n"
        f"🔧 کار: {option.title}\n"
        f"📝 تغییر: {option.description}\n"
        f"💵 هزینه: {money(option.cost)} (الان کم می‌شه)\n"
        f"⏱️ مدت: {_format_duration(option.duration_seconds)}\n"
        f"💰 ارزش فعلی خانه: {money(value)}\n\n"
        "بعد از تکمیل، ارزش خانه بر اساس تغییرات جدید حساب می‌شه."
    )


def renovation_started_text(result: RenovationStartResult) -> str:
    return (
        "🛠️ بازسازی شروع شد!\n"
        "━━━━━━━━━━━━━━━\n"
        f"🏠 خانه #{fa_int(result.house.id)}\n"
        f"🔧 کار: {result.project.title} — {result.project.description}\n"
        f"💵 هزینه: {money(result.cost)}\n"
        f"⏱️ مدت: {_format_duration(result.project.seconds_remaining or 0)}\n"
        f"💳 موجودی فعلی: {money(result.balance_after)}\n\n"
        "پیشرفت رو از «📈 وضعیت ساخت» دنبال کن."
    )


# --- Error texts ---------------------------------------------------------------


def land_not_found_text() -> str:
    return "این زمین پیدا نشد. 🔍"


def land_not_available_text() -> str:
    return "این زمین دیگه تو بازار نیست — یکی زودتر از تو خریدش! 😅"


def land_busy_text() -> str:
    return "روی این زمین نمی‌شه ساخت — یا خانه داره یا در حال ساخته‌شدنه. 🚧"


def spec_invalid_text() -> str:
    return "این نقشه ساخت معتبر نیست — دوباره گزینه‌ها رو انتخاب کن. ⚠️"


def project_not_found_text() -> str:
    return "این پروژه پیدا نشد یا قبلاً بسته شده. 📭"


def already_renovating_text() -> str:
    return "این خانه همین الان در حال بازسازیه! 🛠️"


def renovation_blocked_text() -> str:
    return "این خونه مستأجر داره — وسایل مردم رو به‌هم نریز! 😄\nاول قرارداد اجاره رو تموم کن."


def nothing_to_renovate_text() -> str:
    return "این بازسازی برای این خانه امکان‌پذیر نیست. ⚠️"


def insufficient_funds_text() -> str:
    return (
        "پول کافی نداری! 💸\n"
        f"با 💼 {constants.JOBS_SYSTEM_NAME} درآمد بساز و برگرد."
    )
