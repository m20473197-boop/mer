"""Natural Persian player-facing texts for the Business System."""

from __future__ import annotations

from app.bot.messages.formatters import fa_int, money
from app.core import constants
from app.game.business.dto import (
    BusinessData,
    BusinessDefinitionData,
    BusinessIncomeResult,
    BusinessStartResult,
)


def business_menu_text() -> str:
    return (
        "🏪 منوی کسب‌وکار\n\n"
        "از بین کسب‌وکارهای آماده یکی رو انتخاب کن و صاحبش شو.\n"
        "درآمد روزانه اول به موجودی خود کسب‌وکار اضافه می‌شه؛ مستقیم وارد کیف‌پولت نمی‌شه."
    )


def business_list_text(businesses: list[BusinessDefinitionData]) -> str:
    if not businesses:
        return "فعلاً هیچ کسب‌وکاری برای راه‌اندازی تعریف نشده."

    lines = ["📋 کسب‌وکارهای آماده برای راه‌اندازی", "━━━━━━━━━━━━━━━"]
    for business in businesses:
        status = "✅ فعال" if business.is_available else "🔒 فعلاً بسته"
        lines.extend(
            [
                f"🏷️ {business.name} — {status}",
                f"  💵 سرمایه شروع: {money(business.startup_cost)}",
                (
                    "  📈 درآمد روزانه احتمالی: "
                    f"{money(business.min_daily_income)} تا "
                    f"{money(business.max_daily_income)}"
                ),
                "",
            ]
        )
    lines.append("برای شروع، روی دکمه همان کسب‌وکار بزن 👇")
    return "\n".join(lines)


def _latest_income_line(business: BusinessData) -> str:
    if business.last_income_date is None:
        return "  🕘 آخرین درآمد روزانه: هنوز ثبت نشده"
    return (
        f"  🕘 آخرین درآمد روزانه: {money(business.latest_daily_income)} "
        f"({business.last_income_date.isoformat()})"
    )


def owned_businesses_text(businesses: list[BusinessData]) -> str:
    if not businesses:
        return (
            "🏪 هنوز کسب‌وکاری نداری.\n"
            "از «کسب‌وکارهای موجود» یکی رو انتخاب کن و شروعش کن."
        )

    lines = [
        f"🏪 کسب‌وکارهای تو ({fa_int(len(businesses))})",
        "━━━━━━━━━━━━━━━",
    ]
    for business in businesses:
        state = "فعال" if business.is_active else "غیرفعال"
        lines.extend(
            [
                f"🏷️ {business.name} — {state}",
                f"  💰 موجودی کسب‌وکار: {money(business.balance)}",
                _latest_income_line(business),
                (
                    "  📈 بازه درآمد روزانه: "
                    f"{money(business.min_daily_income)} تا "
                    f"{money(business.max_daily_income)}"
                ),
                "",
            ]
        )
    lines.append(
        "درآمد امروز خودکار همین‌جا ثبت می‌شه؛ برای یک بار دیگر در همان روز دوباره اضافه نمی‌شه."
    )
    return "\n".join(lines)


def business_started_text(result: BusinessStartResult) -> str:
    business = result.business
    return "\n".join(
        [
            f"🎉 کسب‌وکار «{business.name}» راه افتاد!",
            "━━━━━━━━━━━━━━━",
            f"💵 سرمایه شروع پرداخت‌شده: {money(result.startup_cost)}",
            (
                "📈 درآمد روزانه احتمالی: "
                f"{money(business.min_daily_income)} تا "
                f"{money(business.max_daily_income)}"
            ),
            f"💰 موجودی فعلی کسب‌وکار: {money(business.balance)}",
            f"💳 موجودی کیف‌پولت: {money(result.wallet_balance_after)}",
            "",
            "درآمد هر روز به حساب همین کسب‌وکار می‌ره، نه کیف‌پول شخصی‌ات. 🧾",
        ]
    )


def daily_income_text(results: list[BusinessIncomeResult]) -> str:
    if not results:
        return (
            "هنوز کسب‌وکاری نداری که درآمد بده.\n"
            "اول از «کسب‌وکارهای موجود» یکی رو راه‌اندازی کن."
        )

    lines = ["💰 وضعیت درآمد امروز", "━━━━━━━━━━━━━━━"]
    for result in results:
        business = result.business
        if result.generated:
            lines.append(
                f"✅ {business.name}: +{money(result.amount_added)} به موجودی کسب‌وکار اضافه شد."
            )
        else:
            lines.append(
                f"⏱️ {business.name}: درآمد امروز قبلاً ثبت شده ({money(business.latest_daily_income)})."
            )
        lines.append(f"  💰 موجودی: {money(business.balance)}")
    lines.append("")
    lines.append("این پول هنوز داخل کسب‌وکارته و به کیف‌پول شخصی منتقل نشده.")
    return "\n".join(lines)


def business_not_found_text() -> str:
    return "این نوع کسب‌وکار معتبر نیست. از فهرست آماده یکی رو انتخاب کن."


def business_unavailable_text() -> str:
    return "این کسب‌وکار فعلاً بسته است و نمی‌شه راه‌اندازیش کرد."


def business_already_owned_text() -> str:
    return "این کسب‌وکار رو از قبل داری؛ هر نوع کسب‌وکار رو فقط یک بار می‌تونی داشته باشی."


def business_limit_text() -> str:
    return (
        f"به سقف {fa_int(constants.BUSINESS_MAX_PER_PLAYER)} کسب‌وکار رسیدی. "
        "فعلاً کسب‌وکار بیشتری نمی‌تونی راه بندازی."
    )


def business_not_owned_text() -> str:
    return "این کسب‌وکار برای تو نیست."


def business_insufficient_funds_text() -> str:
    return (
        "برای راه‌اندازی این کسب‌وکار پولت کافی نیست. 💸\n"
        "اول از کار و درآمدت پول جمع کن، بعد دوباره امتحان کن."
    )


def business_inactive_text() -> str:
    return "این کسب‌وکار فعلاً فعال نیست و درآمد روزانه نمی‌سازه."
