"""Persian player-facing messages for ``🧱 دیوار ایران``."""

from __future__ import annotations

from app.bot.messages.formatters import fa_int, money
from app.bot.messages.housing import house_card
from app.game.marketplace.catalog import (
    ASSET_TYPE_HOUSE,
    ASSET_TYPE_LAND,
    CATEGORY_LABELS,
    LISTING_STATUS_ACTIVE,
    LISTING_STATUS_CANCELLED,
    LISTING_STATUS_SOLD,
)
from app.game.marketplace.dto import (
    MarketplaceCancelResult,
    MarketplaceFilterState,
    MarketplaceListingData,
    MarketplaceOwnedAssetData,
    MarketplacePurchaseResult,
    MarketplaceSearchResult,
)


def divar_menu_text() -> str:
    return (
        "🧱 دیوار ایران\n"
        "━━━━━━━━━━━━━━━\n"
        "اینجا بازیکن‌ها دارایی واقعی‌شون رو به هم می‌فروشن.\n"
        "فقط خانه و زمینِ مالک‌شده قابل ثبت آگهی هستن؛ اطلاعات هر آگهی از خود ملک خوانده می‌شه.\n\n"
        "یکی از گزینه‌های پایین رو انتخاب کن 👇"
    )


def categories_text() -> str:
    return (
        "🏷️ دسته‌بندی‌های دیوار ایران\n"
        "━━━━━━━━━━━━━━━\n"
        "در این نسخه فقط دارایی‌هایی نمایش داده می‌شن که واقعاً در بازی وجود دارن:\n"
        "🏠 خانه\n"
        "🌍 زمین"
    )


def search_prompt_text() -> str:
    return (
        "🔎 جستجوی دیوار ایران\n\n"
        "عبارت طبیعی‌ات رو بنویس؛ مثلاً:\n"
        "«زمین ۱۰۰ متری یافت آباد»\n"
        "یا «خانه تهران ۲ خواب»"
    )


def filter_prompt_text(kind: str) -> str:
    if kind == "price":
        return "💰 بازه قیمت را بنویس؛ مثلاً «۵ میلیارد تا ۱۰ میلیارد» یا یک مبلغ دقیق."
    if kind == "area":
        return "📐 بازه متراژ را بنویس؛ مثلاً «۱۰۰ تا ۲۰۰» یا «۱۰۰ متر»."
    return "📍 نام محله را بنویس؛ مثلاً «یافت آباد»."


def results_text(result: MarketplaceSearchResult, state: MarketplaceFilterState) -> str:
    if not result.listings:
        return (
            "برای این جستجو آگهی‌ای پیدا نشد.\n\n"
            "عبارت یا فیلترها را تغییر بده و دوباره امتحان کن."
        )
    criteria = state.criteria
    filters: list[str] = []
    if criteria.asset_type == ASSET_TYPE_HOUSE:
        filters.append("خانه")
    elif criteria.asset_type == ASSET_TYPE_LAND:
        filters.append("زمین")
    if criteria.city:
        filters.append(criteria.city)
    if criteria.neighborhood:
        filters.append(criteria.neighborhood)
    if criteria.min_price is not None or criteria.max_price is not None:
        filters.append("بازه قیمت")
    if criteria.min_area_sqm is not None or criteria.max_area_sqm is not None:
        filters.append("بازه متراژ")
    title = "، ".join(filters) if filters else "همه دسته‌ها"
    return (
        f"🧱 آگهی‌های دیوار ایران — {title}\n"
        "━━━━━━━━━━━━━━━\n"
        f"صفحه {fa_int(result.page + 1)} از {fa_int(max(1, (result.total + result.page_size - 1) // result.page_size))}\n"
        "برای دیدن اطلاعات کامل، روی هر آگهی بزن 👇"
    )


def listing_detail_text(listing: MarketplaceListingData) -> str:
    status = {
        LISTING_STATUS_ACTIVE: "فعال ✅",
        LISTING_STATUS_SOLD: "فروخته‌شده 🔒",
        LISTING_STATUS_CANCELLED: "لغوشده 🔒",
    }.get(listing.status, "نامشخص")
    lines = [
        f"🧱 آگهی دیوار ایران #{fa_int(listing.id)}",
        "━━━━━━━━━━━━━━━",
    ]
    if listing.house is not None:
        lines.append(house_card(listing.house))
    elif listing.land is not None:
        land = listing.land
        lines.extend(
            [
                f"🌍 زمین #{fa_int(land.id)}",
                f"🏙️ شهر: {land.city}",
                f"📍 محله: {land.neighborhood}",
                f"📐 مساحت: {fa_int(land.area_sqm)} متر مربع",
                f"⭐ کیفیت موقعیت: {land.location_quality}",
            ]
        )
    lines.extend(
        [
            "━━━━━━━━━━━━━━━",
            f"👤 فروشنده: {listing.seller_name}",
            f"💰 قیمت فروش: {money(listing.price)}",
            f"📌 وضعیت آگهی: {status}",
        ]
    )
    if listing.sold_at is not None:
        lines.append("این آگهی دیگر قابل خرید نیست.")
    return "\n".join(lines)


def owned_assets_text(assets: list[MarketplaceOwnedAssetData]) -> str:
    if not assets:
        return (
            "دارایی قابل ثبت آگهی پیدا نشد.\n\n"
            "خانه یا زمین باید واقعاً به نام تو باشد، آگهی فعال دیگری نداشته باشد و درگیر اجاره/ساخت نباشد."
        )
    return (
        "➕ ثبت آگهی\n"
        "━━━━━━━━━━━━━━━\n"
        "دارایی واقعی‌ای را که می‌خواهی بفروشی انتخاب کن.\n"
        "بعد از انتخاب، قیمت را به تومان وارد می‌کنی."
    )


def price_prompt_text(asset_label: str) -> str:
    return (
        f"🏷️ ثبت آگهی برای {asset_label}\n\n"
        "قیمت فروش را به تومان بنویس؛ فقط عدد مثبت، مثل:\n"
        "۷۵۰۰۰۰۰۰۰۰ یا ۷.۵ میلیارد"
    )


def created_text(listing: MarketplaceListingData) -> str:
    return (
        f"✅ آگهی #{fa_int(listing.id)} ثبت شد.\n"
        f"💰 قیمت: {money(listing.price)}\n"
        "تا وقتی لغوش نکنی یا فروخته نشه، در جستجوی دیوار ایران نمایش داده می‌شه."
    )


def cancelled_text(result: MarketplaceCancelResult) -> str:
    return f"✅ آگهی #{fa_int(result.listing_id)} لغو شد. دارایی همچنان مال خودت است."


def purchased_text(result: MarketplacePurchaseResult) -> str:
    return (
        f"🎉 خرید آگهی #{fa_int(result.listing.id)} با موفقیت انجام شد.\n"
        "━━━━━━━━━━━━━━━\n"
        f"💰 مبلغ پرداخت‌شده: {money(result.price)}\n"
        f"💳 موجودی فعلی تو: {money(result.buyer_balance_after)}\n"
        "مالکیت دارایی به تو منتقل شد و آگهی از نتایج فعال حذف شد."
    )


def my_listings_text(listings: list[MarketplaceListingData]) -> str:
    if not listings:
        return "آگهی فعال نداری.\nاز «➕ ثبت آگهی» شروع کن."
    return (
        f"📋 آگهی‌های فعال تو ({fa_int(len(listings))})\n"
        "━━━━━━━━━━━━━━━\n"
        "برای لغو هر آگهی روی دکمه‌اش بزن."
    )


def filters_text(state: MarketplaceFilterState) -> str:
    criteria = state.criteria
    parts = ["🔎 فیلترهای دیوار ایران", "━━━━━━━━━━━━━━━"]
    parts.append(
        f"دسته: {'همه' if criteria.asset_type is None else CATEGORY_LABELS.get(criteria.asset_type, 'نامشخص')}"
    )
    parts.append(f"شهر: {criteria.city or 'همه'}")
    parts.append(f"محله: {criteria.neighborhood or 'همه'}")
    if criteria.min_price is not None or criteria.max_price is not None:
        parts.append(
            f"قیمت: {money(criteria.min_price or 0)} تا {money(criteria.max_price or criteria.min_price or 0)}"
        )
    if criteria.min_area_sqm is not None or criteria.max_area_sqm is not None:
        parts.append(
            f"متراژ: {fa_int(criteria.min_area_sqm or 0)} تا {fa_int(criteria.max_area_sqm or criteria.min_area_sqm or 0)} متر"
        )
    if state.search_query:
        parts.append(f"جستجو: «{state.search_query[:80]}»")
    return "\n".join(parts)


def listing_not_found_text() -> str:
    return "این آگهی پیدا نشد یا دیگر در دسترس نیست."


def listing_not_active_text() -> str:
    return "این آگهی دیگر فعال نیست و قابل خرید نیست."


def listing_not_owner_text() -> str:
    return "این آگهی متعلق به تو نیست."


def asset_not_found_text() -> str:
    return "دارایی واقعی پیدا نشد؛ نمی‌شود برای دارایی ساختگی آگهی ثبت کرد."


def asset_not_owned_text() -> str:
    return "این دارایی به نام تو نیست؛ فقط مالک واقعی می‌تواند آگهی ثبت کند."


def asset_not_transferable_text() -> str:
    return "این دارایی فعلاً قابل انتقال نیست؛ اجاره، ساخت یا وضعیت وابسته‌اش را اول تمام کن."


def listing_exists_text() -> str:
    return "این دارایی همین حالا یک آگهی فعال دارد."


def invalid_price_text() -> str:
    return "قیمت باید یک عدد صحیح مثبت به تومان باشد."


def own_listing_text() -> str:
    return "نمی‌توانی آگهی خودت را بخری."


def insufficient_balance_text() -> str:
    return "موجودی کافی نیست؛ خرید انجام نشد و هیچ تغییری در حساب‌ها ایجاد نشد."


def input_cancelled_text() -> str:
    return "ورود اطلاعات لغو شد."
