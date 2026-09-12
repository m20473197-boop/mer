"""Job system player-facing texts — simple, no motivational fluff."""

from __future__ import annotations

from app.bot.messages.formatters import fa_int, money
from app.core import constants
from app.game.player.dto import (
    JobData,
    JobEventData,
    PlayerJobData,
    SettlementResult,
)


def jobs_menu_text() -> str:
    name = constants.JOBS_SYSTEM_NAME
    return (
        f"💼 منوی {name}:\n\n"
        "از اینجا می‌تونی کار انتخاب کنی، کار کنی و درآمد بگیری.\n"
        "یه کار انتخاب کن و هر وقت خواستی با صاحبکار تسویه کن 👇"
    )


def jobs_list_text(jobs: list[JobData]) -> str:
    if not jobs:
        return f"هنوز کاری توی {constants.JOBS_SYSTEM_NAME} باز نیست."

    lines = [f"📋 کارهای موجود ({constants.JOBS_SYSTEM_NAME}):\n"]
    for job in jobs:
        lines.append(
            f"• {job.name}\n"
            f"  {job.description}\n"
            f"  🏢 صاحبکار: {job.employer}\n"
            f"  💰 حقوق ساعتی: {money(job.hourly_salary)}\n"
            f"  ⭐ لول مورد نیاز: {fa_int(job.required_level)}\n"
        )
    lines.append("برای انتخاب کار، روی دکمه مربوطه بزن 👇")
    return "\n".join(lines)


def _format_duration(minutes: int) -> str:
    hours = minutes // 60
    rest = minutes % 60
    if hours > 0 and rest > 0:
        return f"{fa_int(hours)} ساعت و {fa_int(rest)} دقیقه"
    if hours > 0:
        return f"{fa_int(hours)} ساعت"
    return f"{fa_int(rest)} دقیقه"


def my_job_text(player_job: PlayerJobData | None) -> str:
    if player_job is None:
        return job_no_job()

    return (
        f"👔 کار فعلیت: {player_job.job_name}\n"
        f"📝 {player_job.job_description}\n"
        f"🏢 صاحبکار: {player_job.employer}\n"
        f"💰 حقوق ساعتی: {money(player_job.hourly_salary)}\n"
        f"📅 شروع کار: {player_job.started_at.strftime('%Y-%m-%d %H:%M')}\n"
        f"⏱️ مدت کار: {_format_duration(player_job.worked_minutes)}\n"
        f"🧮 درآمد فعلی (تسویه‌نشده): {money(player_job.accrued_salary)}\n"
        f"💵 کل دریافتی از این کار: {money(player_job.total_earnings)}\n\n"
        "هر وقت خواستی با دکمه «تسویه با صاحبکار» حقوقت رو بگیر 👇"
    )


def job_applied_success(job_name: str, employer: str, hourly_salary: int) -> str:
    return (
        f"«{job_name}» با موفقیت انتخاب شد.\n"
        f"🏢 صاحبکار: {employer}\n"
        f"💰 حقوق ساعتی: {money(hourly_salary)}\n"
        "⏱️ از همین حالا ساعت کاری شروع شد!"
    )


def job_apply_error(message: str) -> str:
    return f"❌ {message}"


def settlement_text(result: SettlementResult) -> str:
    """Render the outcome of settling accounts with the employer."""
    lines = [
        f"💼 تسویه حساب با {result.employer}",
        "━━━━━━━━━━━━━━━",
        f"👔 کار: {result.job_name}",
        f"⏱️ مدت کار: {_format_duration(result.worked_minutes)}",
        f"💰 حقوق ساعتی: {money(result.hourly_salary)}",
        f"🧮 حقوق ناخالص: {money(result.gross_salary)}",
    ]

    if result.event_type == "bonus":
        lines.append(
            f"🎉 پاداش {fa_int(result.bonus_percent or 0)}٪: +{money(result.bonus_amount)}"
        )
    elif result.event_type == "mistake":
        lines.append(
            f"⚠️ جریمه {fa_int(result.penalty_percent or 0)}٪: -{money(result.penalty_amount)}"
        )

    if result.status == "delayed":
        lines.append("")
        lines.append("⏳ صاحبکار پرداخت رو عقب انداخت! 😤")
        lines.append("فعلاً پولی دریافت نکردی؛ یه‌کم بعد دوباره تسویه کن.")
    else:
        lines.append("")
        lines.append("✅ پرداخت انجام شد.")
        lines.append(f"💸 مبلغ دریافتی: {money(result.final_amount)}")
        lines.append(f"💳 موجودی فعلی: {money(result.balance_after)}")

    return "\n".join(lines)


def job_settle_too_early() -> str:
    return (
        "هنوز حتی یک دقیقه هم از شروع کارت نگذشته! ⏱️\n"
        "کمی کار کن و بعد دوباره تسویه کن."
    )


def job_no_job() -> str:
    return "کاری نداری.\nاز «لیست کارها» یکی رو انتخاب کن."


def job_leave_success(job_name: str, total_earnings: int) -> str:
    return (
        f"«{job_name}» ترک شد.\n"
        f"💵 کل درآمد از این کار: {money(total_earnings)}"
    )


_EVENT_LABELS = {
    "normal": "پرداخت عادی",
    "bonus": "پرداخت با پاداش",
    "mistake": "پرداخت با جریمه",
    "delayed": "تأخیر در پرداخت",
}


def salary_events_text(events: list[JobEventData]) -> str:
    if not events:
        return "هنوز هیچ رویداد تسویه‌ای ثبت نشده."

    lines = [f"📜 تاریخچه تسویه‌حساب‌ها (آخرین {len(events)}):\n"]
    for e in events:
        label = _EVENT_LABELS.get(e.event_type, e.event_type)
        if e.status == "delayed":
            amount = f"⏳ عقب‌افتاده ({money(e.gross_salary)})"
        else:
            amount = money(e.final_amount)
        lines.append(
            f"• {e.employer}: {label} — {amount} — "
            f"{e.created_at.strftime('%Y-%m-%d %H:%M')}"
        )
    return "\n".join(lines)


def job_not_found() -> str:
    return "این کار پیدا نشد."
