"""Admin-panel player-facing Persian texts."""

from __future__ import annotations

from app.bot.messages.formatters import fa_int, fa_year, money
from app.game.admin import dto as admin_dto

NOT_ADMIN: str = "⛔ این بخش فقط برای ادمین‌هاست."
BANNED_TEXT: str = (
    "⛔ حساب شما توسط مدیریت مسدود شده است.\n"
    "برای پیگیری با پشتیبانی در تماس باشید."
)

ADMIN_MENU_TEXT: str = (
    "🛡️ پنل مدیریت\n\n"
    "به مرکز فرماندهی خوش اومدی قربان! 👇\n"
    "یکی از بخش‌ها رو انتخاب کن:"
)


def _fa_float(value: float, digits: int = 2) -> str:
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return text.translate(str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹/"))


def _fa_percent(value: float) -> str:
    return f"٪{_fa_float(value)}"


def _uptime_text(seconds: int) -> str:
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, _ = divmod(rest, 60)
    if days:
        return f"{fa_int(days)} روز و {fa_int(hours)} ساعت"
    if hours:
        return f"{fa_int(hours)} ساعت و {fa_int(minutes)} دقیقه"
    return f"{fa_int(minutes)} دقیقه"


def _size_text(size: int | None) -> str:
    if size is None:
        return "—"
    if size < 1024:
        return f"{fa_int(size)} بایت"
    if size < 1024 * 1024:
        return f"{_fa_float(size / 1024)} کیلوبایت"
    return f"{_fa_float(size / 1024 / 1024)} مگابایت"


# --- Dashboard -----------------------------------------------------------------

def dashboard_text(stats: admin_dto.DashboardStats) -> str:
    return (
        "📊 داشبورد مدیریت\n\n"
        f"👥 کاربران: {fa_int(stats.total_users)} "
        f"(فعال ۲۴ساعت اخیر: {fa_int(stats.active_users_24h)}، "
        f"مسدود: {fa_int(stats.banned_users)})\n"
        f"💰 پول در گردش: {money(stats.total_money)}\n"
        f"🏠 خانه‌ها: {fa_int(stats.houses_count)} | "
        f"🌍 زمین‌ها: {fa_int(stats.lands_count)} | "
        f"💼 شغل‌ها: {fa_int(stats.jobs_count)}\n"
        f"📈 معاملات فعال: فروش {fa_int(stats.active_sale_listings)} + "
        f"اجاره {fa_int(stats.active_rent_listings)} | "
        f"قراردادها: {fa_int(stats.active_contracts)}\n"
        f"🏗️ ساخت‌وساز فعال: {fa_int(stats.active_constructions)} | "
        f"🛠️ بازسازی فعال: {fa_int(stats.active_renovations)}\n"
        f"⚡ رویدادهای اقتصادی فعال: {fa_int(stats.active_events)} | "
        f"ضریب بازار: ×{_fa_float(stats.market_factor, 4)}\n\n"
        f"🖥️ سرور: آنلاین ✅ | آپتایم: {_uptime_text(stats.uptime_seconds)} | "
        f"پایتون {stats.python_version}\n"
        f"🗄️ دیتابیس: {stats.db_dialect} ✅ | "
        f"{fa_int(stats.db_tables)} جدول | "
        f"حجم: {_size_text(stats.db_size_bytes)} | "
        f"پینگ: {_fa_float(stats.db_ping_ms, 1)}ms"
    )


# --- Users ---------------------------------------------------------------------

def users_list_text(page: admin_dto.Page[admin_dto.AdminPlayerSummary]) -> str:
    lines = [
        f"👥 مدیریت کاربران (صفحه {fa_int(page.page + 1)} از {fa_int(page.total_pages)} — "
        f"مجموع {fa_int(page.total)} نفر)\n"
    ]
    for user in page.items:
        flag = " 🚫" if user.is_banned else ""
        handle = f"@{user.username}" if user.username else "—"
        lines.append(
            f"#{user.player_id} {user.display_name} ({handle}){flag}\n"
            f"   🆔 {fa_int(user.telegram_user_id)} | ⭐ لول {fa_int(user.level)} | "
            f"💰 {fa_int(user.money)}"
        )
    if not page.items:
        lines.append("هنوز کاربری ثبت نشده.")
    lines.append("\nبرای مشاهده و مدیریت، کاربر رو انتخاب کن 👇")
    return "\n".join(lines)


def user_detail_text(detail: admin_dto.AdminPlayerDetail) -> str:
    user = detail.summary
    handle = f"@{user.username}" if user.username else "—"
    status = "مسدود 🚫" if user.is_banned else "فعال ✅"
    job = detail.job_name or "بیکار"
    if detail.employer:
        job += f" ({detail.employer})"
    return (
        f"👤 پروفایل #{user.player_id} — {user.display_name}\n\n"
        f"🆔 تلگرام: {fa_int(user.telegram_user_id)}\n"
        f"📎 یوزرنیم: {handle}\n"
        f"📌 وضعیت: {status}\n"
        f"⭐ لول: {fa_int(user.level)} | ✨ XP: {fa_int(user.xp)}\n"
        f"💰 موجودی: {money(user.money)}\n"
        f"🏠 خانه‌ها: {fa_int(detail.houses_count)} | "
        f"🌍 زمین‌ها: {fa_int(detail.lands_count)}\n"
        f"💼 شغل: {job}\n"
        f"📅 عضویت: {detail.created_at.strftime('%Y-%m-%d')}"
    )


def user_tx_text(
    summary: admin_dto.AdminPlayerSummary, entries: list[admin_dto.UserTxEntry]
) -> str:
    lines = [f"📜 تراکنش‌های {summary.display_name} (آخرین {fa_int(len(entries))}):\n"]
    for entry in entries:
        arrow = "📥" if entry.incoming else "📤"
        lines.append(
            f"{arrow} {entry.label} — {money(entry.amount)} "
            f"({entry.created_at.strftime('%m-%d %H:%M')})"
        )
    if not entries:
        lines.append("تراکنشی ثبت نشده.")
    return "\n".join(lines)


def user_props_text(
    summary: admin_dto.AdminPlayerSummary,
    houses: list[admin_dto.HouseAdminEntry],
    lands: list[admin_dto.LandAdminEntry],
) -> str:
    lines = [f"🏠 املاک {summary.display_name}:\n"]
    for house in houses:
        lines.append(
            f"🏠 #{house.id} — {house.city}، {house.neighborhood} "
            f"({fa_int(house.area_sqm)} متری) — {money(house.market_value)}"
        )
    for land in lands:
        lines.append(
            f"🌍 زمین #{land.id} — {land.city}، {land.neighborhood} "
            f"({fa_int(land.area_sqm)} متری) — {money(land.market_value)}"
        )
    if not houses and not lands:
        lines.append("ملکی نداره.")
    return "\n".join(lines)


def ban_confirm_text(summary: admin_dto.AdminPlayerSummary) -> str:
    return (
        f"🚫 مسدودسازی {summary.display_name} (#{summary.player_id})؟\n\n"
        "کاربر مسدودشده نمی‌تونه از ربات استفاده کنه.\n"
        "مطمئنی؟"
    )


# --- Economy -------------------------------------------------------------------

_CATEGORY_EMOJI = {"currency": "💵", "gold": "🥇", "crypto": "🪙"}


def econ_text(overview: admin_dto.EconomyOverview) -> str:
    lines = [
        "💰 مدیریت اقتصاد\n",
        f"🧭 شرایط بازار: ×{_fa_float(overview.base_market_conditions)}",
        f"📉 نرخ تورم: {_fa_percent(overview.inflation_rate)}",
        f"⚡ اثر رویدادها: ×{_fa_float(overview.events_multiplier)}",
        f"🎯 ضریب نهایی بازار: ×{_fa_float(overview.effective_factor, 4)}\n",
        "دارایی‌ها:",
    ]
    for asset in overview.assets:
        emoji = _CATEGORY_EMOJI.get(asset.category, "💱")
        lines.append(f"{emoji} {asset.name}: {money(asset.price)}")
    lines.append("\nرویدادهای فعال:")
    for event in overview.live_events:
        lines.append(f"⚡ {event.name} (×{_fa_float(event.multiplier)})")
    if not overview.live_events:
        lines.append("—")
    return "\n".join(lines)


def asset_detail_text(
    asset: admin_dto.MarketAssetData, ticks: list[admin_dto.AssetPriceTickData]
) -> str:
    lines = [
        f"💱 {asset.name} ({asset.code})\n",
        f"💰 قیمت فعلی: {money(asset.price)}\n",
        "تاریخچه قیمت:",
    ]
    for tick in ticks[:10]:
        lines.append(
            f"• {money(tick.price)} ({tick.created_at.strftime('%m-%d %H:%M')})"
        )
    if not ticks:
        lines.append("—")
    return "\n".join(lines)


def event_detail_text(event: admin_dto.EconomicEventData) -> str:
    state = "فعال ⚡" if event.is_live else ("فعال ⏳" if event.is_active else "پایان‌یافته")
    return (
        f"⚡ {event.name}\n\n"
        f"📌 وضعیت: {state}\n"
        f"✖️ ضریب: ×{_fa_float(event.multiplier)}\n"
        f"📝 {event.description or '—'}\n"
        f"🕐 شروع: {event.starts_at.strftime('%m-%d %H:%M')}\n"
        f"🕐 پایان: {event.ends_at.strftime('%m-%d %H:%M')}"
    )


def crisis_confirm_text() -> str:
    return (
        "🚨 فعال‌سازی بحران اقتصادی؟\n\n"
        "✖️ ضریب ۱/۳۵ روی همه قیمت‌های ملک\n"
        "⏳ مدت: ۲۴ ساعت\n\n"
        "مطمئنی؟"
    )


# --- Real estate ---------------------------------------------------------------

ESTATE_TEXT: str = "🏠 مدیریت املاک\n\nیکی از بخش‌ها رو انتخاب کن 👇"


def houses_list_text(page: admin_dto.Page[admin_dto.HouseAdminEntry]) -> str:
    lines = [
        f"🏠 همه خانه‌ها (صفحه {fa_int(page.page + 1)} از {fa_int(page.total_pages)} — "
        f"مجموع {fa_int(page.total)})\n"
    ]
    for house in page.items:
        owner = house.owner_name or "بازار سیستم"
        override = " 💹" if house.has_override else ""
        lines.append(
            f"#{house.id} {house.city}، {house.neighborhood} "
            f"({fa_int(house.area_sqm)} متری){override}\n"
            f"   👤 {owner} | {money(house.market_value)}"
        )
    if not page.items:
        lines.append("خانه‌ای ثبت نشده.")
    return "\n".join(lines)


def house_detail_text(detail: admin_dto.HouseDetailAdmin) -> str:
    house = detail.house
    owner = detail.owner_name or "بازار سیستم"
    lines = [
        f"🏠 خانه #{house.id}\n",
        f"👤 مالک: {owner}",
        f"📍 {house.city}، {house.neighborhood}",
        f"📐 {fa_int(house.area_sqm)} متری | 🛏️ {fa_int(house.bedrooms)} خوابه | "
        f"🛁 {fa_int(house.bathrooms)} حمام",
        f"📅 سال ساخت: {fa_year(house.construction_year)} | "
        f"کیفیت: {house.quality} | آشپزخانه: {house.kitchen_type}",
        f"💰 ارزش بازار: {money(detail.market_value)}",
    ]
    if house.price_override_per_mille:
        lines.append(
            f"💹 ضریب مدیریتی: {_fa_percent(house.price_override_per_mille / 10)}"
        )
    if detail.active_sale_price is not None:
        lines.append(f"🏷️ در فروش: {money(detail.active_sale_price)}")
    if detail.active_rent is not None:
        deposit, rent = detail.active_rent
        lines.append(f"🔑 در اجاره: رهن {money(deposit)} + اجاره {money(rent)}")
    if detail.active_contract_id is not None:
        lines.append(
            f"📜 قرارداد فعال #{detail.active_contract_id} "
            f"(مستأجر: {detail.tenant_name or '؟'})"
        )
    return "\n".join(lines)


HOUSE_EDIT_TEXT: str = "✏️ ویرایش مشخصات خانه\n\nکدوم مشخصه رو تغییر بدم؟ 👇"
LAND_EDIT_TEXT: str = "✏️ ویرایش مشخصات زمین\n\nکدوم مشخصه رو تغییر بدم؟ 👇"


def lands_list_text(page: admin_dto.Page[admin_dto.LandAdminEntry]) -> str:
    lines = [
        f"🌍 همه زمین‌ها (صفحه {fa_int(page.page + 1)} از {fa_int(page.total_pages)} — "
        f"مجموع {fa_int(page.total)})\n"
    ]
    for land in page.items:
        owner = land.owner_name or "بازار سیستم"
        built = " 🏗️" if land.built_house_id else ""
        override = " 💹" if land.has_override else ""
        lines.append(
            f"#{land.id} {land.city}، {land.neighborhood} "
            f"({fa_int(land.area_sqm)} متری){built}{override}\n"
            f"   👤 {owner} | {money(land.market_value)}"
        )
    if not page.items:
        lines.append("زمینی ثبت نشده.")
    return "\n".join(lines)


def land_detail_text(detail: admin_dto.LandDetailAdmin) -> str:
    land = detail.land
    owner = detail.owner_name or "بازار سیستم"
    lines = [
        f"🌍 زمین #{land.id}\n",
        f"👤 مالک: {owner}",
        f"📍 {land.city}، {land.neighborhood} ({land.location_quality})",
        f"📐 {fa_int(land.area_sqm)} متری",
        f"💰 ارزش بازار: {money(detail.market_value)} "
        f"({money(detail.price_per_sqm)}/متر)",
    ]
    if land.built_house_id:
        lines.append(f"🏗️ ساخته‌شده: خانه #{land.built_house_id}")
    if land.price_override_per_mille:
        lines.append(
            f"💹 ضریب مدیریتی: {_fa_percent(land.price_override_per_mille / 10)}"
        )
    return "\n".join(lines)


def listings_text(page: admin_dto.Page[admin_dto.ListingAdminEntry]) -> str:
    lines = [
        f"🏷️ آگهی‌های فعال (صفحه {fa_int(page.page + 1)} از {fa_int(page.total_pages)} — "
        f"مجموع {fa_int(page.total)})\n"
    ]
    for listing in page.items:
        kind = "فروش" if listing.listing_type == "sale" else "اجاره"
        owner = listing.owner_name or "؟"
        lines.append(
            f"#{listing.listing_id} {kind} — {listing.house_label}\n"
            f"   👤 {owner} | 💰 {money(listing.price)}"
            + (f" + رهن {money(listing.deposit)}" if listing.deposit else "")
        )
    if not page.items:
        lines.append("آگهی فعالی نیست.")
    return "\n".join(lines)


def contracts_text(page: admin_dto.Page[admin_dto.ContractAdminEntry]) -> str:
    lines = [
        f"📜 قراردادهای اجاره (صفحه {fa_int(page.page + 1)} از {fa_int(page.total_pages)} — "
        f"مجموع {fa_int(page.total)})\n"
    ]
    for contract in page.items:
        lines.append(
            f"#{contract.contract_id} — {contract.house_label}\n"
            f"   👤 {contract.owner_name} ← مستأجر: {contract.tenant_name}\n"
            f"   💰 اجاره {money(contract.monthly_rent)} + رهن {money(contract.deposit)}"
        )
    if not page.items:
        lines.append("قرارداد فعالی نیست.")
    return "\n".join(lines)


def contract_detail_text(contract: admin_dto.ContractAdminEntry) -> str:
    state = "فعال ✅" if contract.is_active else "پایان‌یافته"
    return (
        f"📜 قرارداد #{contract.contract_id} — {state}\n\n"
        f"🏠 {contract.house_label}\n"
        f"👤 مالک: {contract.owner_name}\n"
        f"🧑‍💼 مستأجر: {contract.tenant_name}\n"
        f"💰 اجاره ماهانه: {money(contract.monthly_rent)}\n"
        f"💰 رهن: {money(contract.deposit)}\n"
        f"🕐 سررسید بعدی: {contract.next_due_at.strftime('%Y-%m-%d')}"
    )


# --- Jobs ----------------------------------------------------------------------

def jobs_text(entries: list[admin_dto.JobAdminEntry]) -> str:
    lines = ["💼 مدیریت شغل‌ها\n"]
    for job in entries:
        state = "فعال ✅" if job.is_active else "غیرفعال ❌"
        lines.append(
            f"#{job.id} {job.name} — {state}\n"
            f"   💰 {money(job.hourly_salary)}/ساعت | ⭐ لول {fa_int(job.required_level)} | "
            f"👷 {fa_int(job.workers_count)} کارگر"
        )
    if not entries:
        lines.append("شغلی ثبت نشده.")
    return "\n".join(lines)


def job_detail_text(job: admin_dto.JobAdminEntry) -> str:
    state = "فعال ✅" if job.is_active else "غیرفعال ❌"
    return (
        f"💼 {job.name} (#{job.id}) — {state}\n\n"
        f"📝 {job.description}\n"
        f"💰 حقوق ساعتی: {money(job.hourly_salary)}\n"
        f"🏢 صاحبکار: {job.employer or '—'}\n"
        f"⭐ حداقل لول: {fa_int(job.required_level)}\n"
        f"⏳ کول‌داون: {fa_int(job.cooldown)} ثانیه\n"
        f"👷 کارگران فعال: {fa_int(job.workers_count)}"
    )


def workers_text(page: admin_dto.Page[admin_dto.WorkerEntry]) -> str:
    lines = [
        f"👷 کارگران فعال (صفحه {fa_int(page.page + 1)} از {fa_int(page.total_pages)} — "
        f"مجموع {fa_int(page.total)})\n"
    ]
    for worker in page.items:
        lines.append(
            f"{worker.display_name} — {worker.job_name}\n"
            f"   🆔 {fa_int(worker.telegram_user_id)} | "
            f"💰 درآمد کل: {money(worker.total_earnings)}"
        )
    if not page.items:
        lines.append("کارگر فعالی نیست.")
    return "\n".join(lines)


# --- Trading -------------------------------------------------------------------

def trade_text(overview: dict) -> str:
    lines = [
        "📈 مدیریت معاملات (بازار P2P)\n",
        f"🏷️ آگهی‌های فروش فعال: {fa_int(overview['active_sales'])}",
        f"🔑 آگهی‌های اجاره فعال: {fa_int(overview['active_rents'])}",
        f"✅ کل فروش‌های ثبت‌شده: {fa_int(overview['total_sales'])}\n",
        "آخرین فروش‌ها:",
    ]
    for sale in overview["recent_sales"]:
        seller = sale.seller_name or "بازار سیستم"
        lines.append(f"• {sale.house_label}: {seller} ← {sale.buyer_name} — {money(sale.price)}")
    if not overview["recent_sales"]:
        lines.append("—")
    return "\n".join(lines)


def sales_text(page: admin_dto.Page[admin_dto.SaleAdminEntry]) -> str:
    lines = [
        f"✅ فروش‌های ثبت‌شده (صفحه {fa_int(page.page + 1)} از {fa_int(page.total_pages)} — "
        f"مجموع {fa_int(page.total)})\n"
    ]
    for sale in page.items:
        seller = sale.seller_name or "بازار سیستم"
        lines.append(
            f"#{sale.sale_id} {sale.house_label}\n"
            f"   {seller} ← {sale.buyer_name} — {money(sale.price)} "
            f"({sale.created_at.strftime('%m-%d %H:%M')})"
        )
    if not page.items:
        lines.append("فروشی ثبت نشده.")
    return "\n".join(lines)


def activity_text(entries: list[admin_dto.UserTxEntry]) -> str:
    lines = ["⚡ فعالیت اخیر بازار:\n"]
    for entry in entries:
        lines.append(
            f"• {entry.label} — {money(entry.amount)} "
            f"({entry.created_at.strftime('%m-%d %H:%M')})"
        )
    if not entries:
        lines.append("فعالیتی ثبت نشده.")
    return "\n".join(lines)


# --- Settings ------------------------------------------------------------------

def settings_text(overview: admin_dto.SettingsOverview) -> str:
    def flag(on: bool) -> str:
        return "روشن ✅" if on else "خاموش ❌"

    return (
        "⚙️ تنظیمات ربات\n\n"
        "💰 اقتصاد:\n"
        f"• شرایط بازار: ×{_fa_float(overview.market_conditions)}\n"
        f"• تورم: {_fa_percent(overview.inflation_rate)}\n\n"
        "🎁 پاداش‌ها (XP خرید):\n"
        f"• مقسوم خرید: {fa_int(overview.purchase_xp_divisor)}\n"
        f"• کف/سقف: {fa_int(overview.purchase_xp_min)} تا {fa_int(overview.purchase_xp_max)}\n"
        f"• مقسوم ساخت‌وساز: {fa_int(overview.construction_xp_divisor)}\n\n"
        "⏳ کول‌داون‌ها:\n"
        f"• حداقل کار برای تسویه: {fa_int(overview.min_work_minutes)} دقیقه\n\n"
        "🧩 قابلیت‌ها:\n"
        f"• شغل‌ها: {flag(overview.jobs_enabled)}\n"
        f"• خانه و مسکن: {flag(overview.housing_enabled)}\n"
        f"• زمین و ساخت‌وساز: {flag(overview.realestate_enabled)}"
    )


# --- Database ------------------------------------------------------------------

DB_TEXT: str = "🗄️ ابزارهای دیتابیس\n\nیکی رو انتخاب کن 👇"


def db_stats_text(stats: admin_dto.DBStats) -> str:
    lines = [
        "🗄️ آمار دیتابیس\n",
        f"🔧 موتور: {stats.dialect}",
        f"💾 حجم فایل: {_size_text(stats.file_size_bytes)}",
        f"📦 جدول‌ها: {fa_int(stats.tables)} | رکوردها: {fa_int(stats.total_rows)}\n",
    ]
    for name, count in stats.counts:
        if count:
            lines.append(f"• {name}: {fa_int(count)}")
    return "\n".join(lines)


def backups_text(backups: list[admin_dto.BackupInfo]) -> str:
    lines = ["💾 بکاپ‌ها (برای بازیابی انتخاب کن):\n"]
    for info in backups[:10]:
        lines.append(
            f"• {info.filename}\n"
            f"   {_size_text(info.size_bytes)} — "
            f"{info.created_at.strftime('%Y-%m-%d %H:%M')}"
        )
    if not backups:
        lines.append("بکاپی نیست. اول یه بکاپ بگیر.")
    return "\n".join(lines)


def backup_done_text(info: admin_dto.BackupInfo) -> str:
    return (
        "✅ بکاپ گرفته شد!\n\n"
        f"📁 {info.filename}\n"
        f"💾 حجم: {_size_text(info.size_bytes)}\n\n"
        "فایل بکاپ همینجا برات ارسال می‌شه 👇"
    )


def restore_confirm_text(info: admin_dto.BackupInfo) -> str:
    return (
        "⚠️ بازیابی دیتابیس؟\n\n"
        f"📁 {info.filename}\n"
        f"📅 {info.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
        "کل دیتابیس فعلی با این بکاپ جایگزین می‌شه!\n"
        "مطمئنی؟"
    )


CLEAN_TEXT: str = (
    "🧹 پاک‌سازی داده‌ها\n\n"
    "یکی رو انتخاب کن. بعدش تعداد روز رو می‌پرسم:"
)


# --- Logs ----------------------------------------------------------------------

LOGS_TEXT: str = "📋 لاگ‌ها و گزارش‌ها\n\nکدوم دسته؟ 👇"


def audit_list_text(
    page: admin_dto.Page[admin_dto.AdminAuditEntry], title: str
) -> str:
    lines = [
        f"{title} (صفحه {fa_int(page.page + 1)} از {fa_int(page.total_pages)} — "
        f"مجموع {fa_int(page.total)})\n"
    ]
    for row in page.items:
        target = f" {row.target_type}#{row.target_id}" if row.target_type else ""
        lines.append(
            f"#{row.id} 🛡️{fa_int(row.admin_telegram_id)} {row.action}{target}\n"
            f"   {row.details or '—'} ({row.created_at.strftime('%m-%d %H:%M')})"
        )
    if not page.items:
        lines.append("لاگی ثبت نشده.")
    return "\n".join(lines)


def error_logs_text(lines: list[str]) -> str:
    if not lines:
        return "⚠️ خطاهای اخیر:\n\nتازه هیچ خطایی ثبت نشده. همه‌چی آرومه! ✅"
    body = "\n\n".join(f"• {line}" for line in lines[-8:])
    return f"⚠️ خطاهای اخیر:\n\n{body}"


# --- Input prompts ---------------------------------------------------------------

INPUT_PROMPTS: dict[str, str] = {
    "q": "🔍 جست‌وجوی کاربر\n\nآیدی عددی، آیدی تلگرام، یوزرنیم یا اسم رو بفرست:",
    "m+": "➕ افزودن پول\n\nمبلغ (تومان) رو بفرست. می‌تونی از k و m هم استفاده کنی (مثلاً 10m):",
    "m-": "➖ کم‌کردن پول\n\nمبلغ (تومان) رو بفرست:",
    "x+": "➕ افزودن XP\n\nمقدار XP رو بفرست:",
    "x-": "➖ کم‌کردن XP\n\nمقدار XP رو بفرست:",
    "lvl": "⭐ تغییر لول\n\nلول جدید (۱ تا ۱۰۰) رو بفرست:",
    "infl": "📉 نرخ تورم\n\nدرصد تورم رو بفرست (مثلاً ۵ یا 12.5). عدد منفی یعنی کاهش قیمت‌ها:",
    "mkt": "🧭 شرایط بازار\n\nضریب بازار رو بفرست (۰/۱ تا ۱۰ — مثلاً 1.2):",
    "ap": "💱 قیمت جدید دارایی\n\nقیمت جدید (تومان) رو بفرست:",
    "ev_name": "⚡ رویداد اقتصادی جدید\n\nقدم ۱ از ۳ — اسم رویداد رو بفرست (مثلاً «رونق بازار»):",
    "ev_mult": "قدم ۲ از ۳ — ضریب اثر رو بفرست (۰/۱ تا ۱۰ — مثلاً 1.2 برای رشد ۲۰٪):",
    "ev_hours": "قدم ۳ از ۳ — مدت (ساعت) رو بفرست (مثلاً ۴۸):",
    "ja_name": "💼 شغل جدید\n\nقدم ۱ از ۶ — اسم شغل رو بفرست:",
    "ja_desc": "قدم ۲ از ۶ — توضیح شغل رو بفرست:",
    "ja_salary": "قدم ۳ از ۶ — حقوق ساعتی (تومان) رو بفرست:",
    "ja_level": "قدم ۴ از ۶ — حداقل لول لازم رو بفرست:",
    "ja_emp": "قدم ۵ از ۶ — اسم صاحبکار رو بفرست:",
    "ja_cool": "قدم ۶ از ۶ — کول‌داون (ثانیه) رو بفرست (۰ یعنی بدون کول‌داون):",
    "js": "💰 حقوق ساعتی جدید (تومان) رو بفرست:",
    "jl": "⭐ حداقل لول جدید رو بفرست:",
    "jc": "⏳ کول‌داون جدید (ثانیه) رو بفرست:",
    "je": "🏢 اسم جدید صاحبکار رو بفرست:",
    "jd": "📝 توضیح جدید شغل رو بفرست:",
    "rw": "🎁 مقدار جدید رو بفرست:",
    "mwm": "⏳ حداقل دقایق کار برای تسویه رو بفرست (۰ تا ۱۴۴۰):",
    "ha_area": "📐 متراژ جدید (۱۰ تا ۵۰۰۰) رو بفرست:",
    "ha_bed": "🛏️ تعداد خواب جدید (۰ تا ۲۰) رو بفرست:",
    "ha_bath": "🛁 تعداد حمام جدید (۱ تا ۱۰) رو بفرست:",
    "ha_liv": "🛋️ تعداد نشیمن جدید (۰ تا ۲۰) رو بفرست:",
    "ha_year": "📅 سال ساخت جدید (شمسی، مثلاً ۱۳۹۵) رو بفرست:",
    "ha_loc": "📍 لوکیشن جدید رو با فرمت «شهر، محله» بفرست (مثلاً: تهران، ونک):",
    "ha_ovr": "💹 ضریب قیمت جدید (در هزار) رو بفرست — ۱۰۰۰ یعنی قیمت عادی، ۱۲۰۰ یعنی ۲۰٪ گرون‌تر. برای حذف ضریب، ۰ بفرست:",
    "la_area": "📐 متراژ جدید زمین (۳۰ تا ۱۰۰۰۰۰) رو بفرست:",
    "la_loc": "📍 لوکیشن جدید رو با فرمت «شهر، محله» بفرست:",
    "la_ovr": "💹 ضریب قیمت جدید (در هزار) رو بفرست. برای حذف ضریب، ۰ بفرست:",
    "purge": "🧹 تعداد روز رو بفرست:",
}

INPUT_INVALID: str = "❌ ورودی معتبر نیست. دوباره امتحان کن یا انصراف بزن."

INPUT_CANCELLED: str = "انصراف زده شد. برگشتی به پنل 👇"


def search_results_text(users: list[admin_dto.AdminPlayerSummary]) -> str:
    lines = [f"🔍 نتایج جست‌وجو ({fa_int(len(users))}):\n"]
    for user in users:
        flag = " 🚫" if user.is_banned else ""
        lines.append(
            f"#{user.player_id} {user.display_name}{flag} — "
            f"⭐ {fa_int(user.level)} | 💰 {fa_int(user.money)}"
        )
    if not users:
        lines.append("کسی پیدا نشد.")
    return "\n".join(lines)
