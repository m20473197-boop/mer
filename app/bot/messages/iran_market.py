"""Persian player-facing texts for ``📈 بازار ایران``."""

from __future__ import annotations

from app.bot.messages.formatters import fa_int, money
from app.game.market.catalog import (
    ASSET_HOUSING,
    COIN_CODE,
    GOLD_CODE,
    USD_CODE,
)
from app.game.market.dto import (
    IranMarketAssetData,
    IranMarketHoldingData,
    IranMarketPurchaseResult,
    IranMarketSnapshotData,
)


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
            "💵 دلار، 🪙 طلا و 🪙 سکه قابل خرید هستند.",
            "🏠 مسکن در این بخش فقط نمایش داده می‌شود.",
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
            (
                "🏠 مسکن در این بخش فقط برای نمایش قیمت است و خرید مستقیم ندارد."
                if asset.category == ASSET_HOUSING
                else "برای خرید، دکمه خرید را بزن و مقدار موردنظرت را وارد کن."
            ),
        ]
    )


def purchase_quantity_prompt(asset: IranMarketAssetData) -> str:
    unit = _quantity_unit(asset.code)
    return (
        f"🛒 خرید {asset.display_name}\n"
        "━━━━━━━━━━━━━━━\n"
        f"قیمت فعلی: {_price_text(asset)}\n\n"
        f"مقدار را به {unit} وارد کن؛ فقط عدد صحیح مثبت."
    )


def purchase_success_text(result: IranMarketPurchaseResult) -> str:
    unit = _quantity_unit(result.asset.code)
    return (
        f"✅ {fa_int(result.quantity)} {unit} {result.asset.display_name} خریداری شد.\n"
        "━━━━━━━━━━━━━━━\n"
        f"💰 مبلغ پرداخت‌شده: {money(result.total_cost)}\n"
        f"💳 موجودی کیف‌پول: {money(result.wallet_balance_after)}\n"
        f"📦 دارایی تو: {fa_int(result.holding.quantity)} {unit}"
    )


def purchase_command_success_text(result: IranMarketPurchaseResult) -> str:
    if result.asset.code == USD_CODE:
        return f"💵 {fa_int(result.quantity)} دلار خریداری شد."
    if result.asset.code == GOLD_CODE:
        return f"🪙 {fa_int(result.quantity)} گرم طلا خریداری شد."
    return f"🪙 {fa_int(result.quantity)} سکه خریداری شد."


def purchase_invalid_quantity_text() -> str:
    return "مقدار باید یک عدد صحیح مثبت باشد؛ مثلاً «خرید دلار ۱۰۰»."


def purchase_not_allowed_text() -> str:
    return "این مورد قابل خرید نیست یا قیمت فعلی آن آماده نیست."


def purchase_error_text() -> str:
    return "خرید کامل نشد؛ هیچ مبلغی از کیف‌پولت کم نشده است. دوباره امتحان کن."


def insufficient_balance_text() -> str:
    return "موجودی کیف‌پولت برای این خرید کافی نیست؛ خرید انجام نشد."


def market_not_ready_text() -> str:
    return "هنوز قیمت‌های بازار آماده نشده؛ آخرین داده معتبر به‌زودی دوباره بررسی می‌شه."


def market_asset_not_found_text() -> str:
    return "این مورد جزو بازار ایران نیست. از همان چهار گزینه بازار انتخاب کن."


def holdings_text(holdings: list[IranMarketHoldingData]) -> str:
    if not holdings:
        return "هنوز از بازار ایران دارایی‌ای نخریده‌ای."
    lines = ["📦 دارایی‌های بازار ایران", "━━━━━━━━━━━━━━━"]
    for holding in holdings:
        unit = _quantity_unit(holding.asset_code)
        category = "gold" if holding.asset_code == GOLD_CODE else (
            "coin" if holding.asset_code == COIN_CODE else "currency"
        )
        lines.append(
            f"{_emoji(category)} {holding.display_name}: "
            f"{fa_int(holding.quantity)} {unit}"
        )
    return "\n".join(lines)


def _quantity_unit(asset_code: str) -> str:
    if asset_code == GOLD_CODE:
        return "گرم"
    if asset_code == COIN_CODE:
        return "سکه"
    return "دلار"


def _summary_line(asset: IranMarketAssetData) -> str:
    return (
        f"{_emoji(asset.category)} {asset.display_name}: "
        f"{_price_text(asset)} {_movement(asset)}"
    )


def _price_text(asset: IranMarketAssetData) -> str:
    if asset.current_price is None:
        return "فعلاً دریافت نشده"
    if asset.category == "housing":
        return f"{money(asset.current_price)}/متر"
    if asset.category == "gold":
        return f"{money(asset.current_price)}/گرم"
    return money(asset.current_price)


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
