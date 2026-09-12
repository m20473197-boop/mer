"""Persian player-facing texts for ``📈 بازار ایران``."""

from __future__ import annotations

from app.bot.messages.formatters import fa_int, money
from app.game.market.dto import IranMarketAssetData, IranMarketSnapshotData


def iran_market_menu_text(snapshot: IranMarketSnapshotData) -> str:
    lines = [
        "📈 بازار ایران",
        "━━━━━━━━━━━━━━━",
        "قیمت‌ها از آخرین داده ذخیره‌شده بازار نمایش داده می‌شن:",
        "",
    ]
    for asset in snapshot.assets:
        lines.append(_summary_line(asset))
    if not snapshot.assets:
        lines.append("فعلاً اطلاعات بازار آماده نیست؛ بعداً دوباره سر بزن.")
    lines.extend(
        [
            "",
            "برای جزئیات هر مورد روی دکمه‌اش بزن 👇",
        ]
    )
    return "\n".join(lines)


def iran_market_detail_text(asset: IranMarketAssetData) -> str:
    current = _price_text(asset)
    previous = (
        money(asset.previous_price)
        if asset.previous_price is not None
        else "هنوز ثبت نشده"
    )
    change = _change_text(asset)
    updated = (
        asset.last_successful_update.strftime("%Y-%m-%d %H:%M")
        if asset.last_successful_update is not None
        else "هنوز بروزرسانی موفقی ثبت نشده"
    )
    return "\n".join(
        [
            f"{_emoji(asset.category)} {asset.display_name}",
            "━━━━━━━━━━━━━━━",
            f"قیمت فعلی: {current}",
            f"قیمت قبلی: {previous}",
            f"تغییر: {change}",
            f"آخرین بروزرسانی موفق: {updated}",
            "",
            "این صفحه فقط قیمت ذخیره‌شده را می‌خواند و با بازکردنش قیمت عوض نمی‌شود.",
        ]
    )


def market_not_ready_text() -> str:
    return "هنوز قیمت‌های بازار آماده نشده؛ آخرین داده معتبر به‌زودی دوباره بررسی می‌شه."


def market_asset_not_found_text() -> str:
    return "این مورد جزو بازار ایران نیست. از همان چهار گزینه بازار انتخاب کن."


def _summary_line(asset: IranMarketAssetData) -> str:
    return (
        f"{_emoji(asset.category)} {asset.display_name}: "
        f"{_price_text(asset)} {_movement(asset)}"
    )


def _price_text(asset: IranMarketAssetData) -> str:
    if asset.current_price is None:
        return "فعلاً دریافت نشده"
    suffix = "" if asset.category == "currency" else ""
    if asset.category == "housing":
        return f"{money(asset.current_price)}/متر"
    if asset.category == "gold":
        return f"{money(asset.current_price)}/گرم"
    return f"{money(asset.current_price)}{suffix}"


def _movement(asset: IranMarketAssetData) -> str:
    if asset.change_amount is None or asset.direction is None:
        return ""
    if asset.direction == "up":
        return f"📈 +{fa_int(asset.change_amount)}"
    if asset.direction == "down":
        return f"📉 -{fa_int(asset.change_amount)}"
    return "➖ بدون تغییر"


def _change_text(asset: IranMarketAssetData) -> str:
    if asset.change_amount is None or asset.direction is None:
        return "هنوز قابل محاسبه نیست"
    if asset.direction == "up":
        return f"📈 +{money(asset.change_amount)}"
    if asset.direction == "down":
        return f"📉 -{money(asset.change_amount)}"
    return "➖ بدون تغییر"


def _emoji(category: str) -> str:
    return {
        "currency": "💵",
        "gold": "🪙",
        "coin": "🪙",
        "housing": "🏠",
    }.get(category, "📈")
