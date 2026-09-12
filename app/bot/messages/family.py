"""All player-facing Persian texts of the Marriage and Family system.

Same rule as every other ``app/bot/messages`` module: no UI string lives in a
handler. Numbers are formatted with the shared Persian formatters.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.bot.messages.formatters import fa_int, money
from app.core import constants
from app.game.family.dto import (
    CheatingResult,
    ChildData,
    DivorceResult,
    FamilyHistoryEntryData,
    FamilyInfoData,
    MarriageRequestData,
    MarriageResult,
    RelationshipResult,
)

# How a family milestone is labelled in the timeline output.
_EVENT_LABELS: dict[str, str] = {
    "marriage": "💍 ازدواج",
    "divorce": "💔 طلاق",
    "forced_divorce": "⚡ طلاق اجباری",
    "birth": "👶 تولد فرزند",
    "pregnancy": "🤰 بارداری",
    "cheating_discovered": "🕵️ فاش شدن خیانت",
    "marriage_request": "📨 درخواست ازدواج",
    "request_rejected": "🚫 رد/لغو درخواست",
    "request_expired": "⌛ انقضای درخواست",
}


def _date(value: datetime | None) -> str:
    """Short Gregorian date for the Persian UI (no new dependency needed)."""
    if value is None:
        return "—"
    moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y/%m/%d")


# === Marriage ================================================================


def marriage_needs_reply() -> str:
    """«ازدواج» was sent without replying to somebody."""
    return (
        "💍 برای ازدواج باید این دستور رو **روی پیام خودِ طرف مقابل** ریپلای کنی.\n\n"
        f"«{constants.MARRIAGE_TRIGGER}»"
    )


def marriage_request_created(request: MarriageRequestData, target_name: str) -> str:
    return (
        f"💍 درخواست ازدواج برای {target_name} ارسال شد.\n\n"
        f"💰 مهریه‌ای که هنگام طلاق باید پرداخته بشه: {money(request.mahriyeh_amount)}\n"
        f"⏳ تا {fa_int(constants.MARRIAGE_REQUEST_EXPIRY_HOURS)} ساعت فرصت پاسخ هست.\n\n"
        "اگه پشیمون شدی: «"
        + constants.MARRIAGE_CANCEL_TRIGGER
        + "»"
    )


def marriage_request_incoming(request: MarriageRequestData, proposer_name: str) -> str:
    return (
        f"💌 {proposer_name}خواسته با تو ازدواج کنه!\n\n"
        f"💰 مهریه: {money(request.mahriyeh_amount)}\n\n"
        f"✅ برای قبول: «{constants.MARRIAGE_ACCEPT_TRIGGER}»\n"
        f"⛔ برای رد: «{constants.MARRIAGE_REJECT_TRIGGER}»"
    )


def marriage_accepted(result: MarriageResult) -> str:
    return (
        f"🎉 تبریک! ازدواج {result.husband_name} و {result.wife_name} ثبت شد.\n\n"
        f"💰 مهریه (ذخیره‌شده): {money(result.mahriyeh_amount)}\n"
        f"❤️ رابطه: {fa_int(result.relationship_quality)} از {fa_int(constants.RELATIONSHIP_QUALITY_MAX)}\n\n"
        f"با «{constants.FAMILY_TRIGGER}» می‌تونی اطلاعات خانواده‌ات رو ببینی."
    )


def marriage_rejected(proposer_name: str) -> str:
    return f"{proposer_name} درخواست ازدواجت رو رد کرد. 😔 ناامید نشو، زندگی ادامه داره!"


def marriage_cancelled(target_name: str) -> str:
    return f"🗑️ درخواست ازدواجت به {target_name} لغو شد."


def marriage_already_answered() -> str:
    return "این درخواست دیگه پاسخش داده شده یا زمانش تموم شده."


def already_married(spouse_name: str) -> str:
    return (
        f"💍 تو متأهلی! همسرت {spouse_name} هست.\n"
        "اول باید جدا بشی: «" + constants.DIVORCE_TRIGGER + "»"
    )


def target_already_married(target_name: str) -> str:
    return f"😅 {target_name} متأهله و نمی‌تونه دوباره ازدواج کنه."


def cannot_marry_yourself() -> str:
    return "🙃 با خودت که نمی‌شه ازدواج کرد!"


def requirement_level(level: int) -> str:
    return (
        f"🔒 برای ازدواج حداقل لول {fa_int(constants.MARRIAGE_MIN_LEVEL)} لازمه.\n"
        f"📊 لول فعلی تو: {fa_int(level)}"
    )


def requirement_money(money_: int) -> str:
    return (
        f"💰 برای خواستگاری حداقل {money(constants.MARRIAGE_MIN_MONEY)} توی کیف پولت لازمه.\n"
        f"👛 موجودی فعلی: {money(money_)}"
    )


def not_registered_reply() -> str:
    return "🤔 طرف مقابل هنوز تو بازی ثبت‌نام نکرده؛ اول باید /start بزنه."


# === Divorce =================================================================


def divorce_done(result: DivorceResult, ex_spouse_name: str) -> str:
    if result.mahriyeh_waived:
        return (
            f"💔 ازدواجت با {ex_spouse_name} تموم شد.\n\n"
            f"⚖️ به خاطر خیانت {ex_spouse_name}، مهریه بخشیده شد و چیزی پرداخت نکردی.\n"
            f"👶 بچه‌ها: {fa_int(result.children_count)}"
        )
    if result.mahriyeh_paid:
        return (
            f"💔 ازدواجت با {ex_spouse_name} تموم شد.\n\n"
            f"💰 مهریه پرداخت شد: {money(result.mahriyeh_amount)}\n"
            f"👛 موجودی بعد از پرداخت: {money(result.balance_after)}\n"
            f"👶 بچه‌ها: {fa_int(result.children_count)}"
        )
    return (
        f"💔 ازدواجت با {ex_spouse_name} تموم شد.\n\n"
        "💸 این ازدواج بدون مهریه تموم شد.\n"
        f"👶 بچه‌ها: {fa_int(result.children_count)}"
    )


def divorce_unaffordable(required: int, balance: int) -> str:
    missing = max(0, required - balance)
    return (
        "💸 برای طلاق باید مهریه رو پرداخت کنی و موجودیت کافی نیست.\n\n"
        f"💰 مبلغ لازم: {money(required)}\n"
        f"👛 موجودی تو: {money(balance)}\n"
        f"📉 کم داری: {money(missing)}\n\n"
        "یه مدتی کار کن و برگرد. 🙂"
    )


def not_married() -> str:
    return (
        "💍 متأهل نیستی.\n"
        f"برای شروع: پیام طرف مقابل رو ریپلای کن و بزن «{constants.MARRIAGE_TRIGGER}»"
    )


# === Cheating ================================================================


def cheating_discovered(result: CheatingResult) -> str:
    lines = [
        "🕵️ خیانتت فاش شد!",
        "",
        f"❤️ رابطه: {fa_int(result.quality_before)} → {fa_int(result.quality_after)}",
        f"⚠️ دفعه‌های لو رفتن: {fa_int(result.strikes)}",
    ]
    if result.fine_amount > 0:
        lines.append(f"💸 جریمه: {money(result.fine_amount)}")
        lines.append(f"👛 موجودی: {money(result.balance_after)}")
    if result.forced_divorce:
        lines.append("")
        lines.append("⚡ این آخرین هشدار بود؛ ازدواجت باطل شد و مهریه رو باید بدی.")
    return "\n".join(lines)


def cheating_success(result: CheatingResult) -> str:
    return (
        "🤫 چیزی نگذشت که... فعلاً کسی چیزی نفهمیده.\n\n"
        f"❤️ رابطه: {fa_int(result.quality_before)} → {fa_int(result.quality_after)}\n"
        "⚠️ هر بار که لو بری گرون‌تر تمام می‌شه."
    )


def cheating_failed() -> str:
    return "😅 هیچ‌چیز نشد که! پشیمون شدی و ولش کردی. این بهترین حالت بود."


# === Relationship / children =================================================


def relationship_result(result: RelationshipResult, spouse_name: str | None) -> str:
    partner = f" با {spouse_name}" if spouse_name else ""
    lines = [
        f"💞 یه وقت دونفره{partner} داشتید.",
        "",
        f"❤️ رابطه: {fa_int(result.quality_before)} → {fa_int(result.quality_after)}",
    ]
    if result.xp_granted:
        lines.append(f"✨ XP: {fa_int(result.xp_granted)}")
    if result.pregnancy:
        lines.append("")
        lines.append("🤰 یه خبر بزرگ در راهه! بارداری ثبت شد.")
    elif result.blocked_max_children:
        lines.append("")
        lines.append(
            f"👶 به سقف {fa_int(constants.MAX_CHILDREN_PER_MARRIAGE)} فرزند رسیدید."
        )
    return "\n".join(lines)


def relationship_must_reply_to_spouse() -> str:
    return (
        f"💞 «{constants.RELATIONSHIP_TRIGGER}» رو باید روی پیام همسرت ریپلای کنی."
    )


def child_birth_notice(child: ChildData, parent_name: str) -> str:
    return (
        f"👶 تبریک {parent_name}! یه فرزند به دنیا اومد.\n\n"
        f"🧒 نام: {child.name}\n"
        f"🆔 شناسه فرزند: {fa_int(child.child_id)}\n"
        f"📅 تاریخ تولد: {_date(child.birth_date)}\n"
        f"🌱 مرحله رشد: {child.growth_stage}"
    )


def children_list(children: list[ChildData]) -> str:
    if not children:
        return "👶 فرزندنداری.\nبا «" + constants.RELATIONSHIP_TRIGGER + "» می‌تونید بچه‌دار بشید."
    rows = ["👶 فرزندان تو:\n"]
    for child in children:
        rows.append(
            f"🧒 {child.name} — شناسه {fa_int(child.child_id)}، "
            f"تولد {_date(child.birth_date)}، {child.growth_stage}"
        )
    rows.append(f"\n📊 تعداد: {fa_int(len(children))}")
    return "\n".join(rows)


# === Family info =============================================================


def family_info(info: FamilyInfoData) -> str:
    if not info.married:
        return (
            "👤 وضعیت خانوادگی: **مجرد**\n\n"
            f"👶 فرزندان: {fa_int(info.children_count)}\n\n"
            f"برای ازدواج، پیام طرف مقابل رو ریپلای کن و بزن «{constants.MARRIAGE_TRIGGER}»"
        )
    lines = [
        "👨‍👩‍👧 اطلاعات خانواده",
        "━━━━━━━━━━━━━━━",
        "💍 وضعیت ازدواج: متأهل",
        f"🧑 همسر: {info.spouse_name or '—'} (شناسه {fa_int(info.spouse_player_id or 0)})",
        f"📅 تاریخ ازدواج: {_date(info.marriage_date)}",
        f"⏳ مدت ازدواج: {fa_int(info.marriage_years)} سال",
        f"👶 تعداد فرزندان: {fa_int(info.children_count)}",
        f"❤️ کیفیت رابطه: {fa_int(info.relationship_quality)} — {info.quality_label}",
        f"💰 مهریه: {money(info.mahriyeh_amount)}"
        + ("" if info.mahriyeh_paid else " (پرداخت‌نشده)"),
    ]
    if info.cheating_strikes:
        lines.append(f"🕵️ خیانت‌های فاش‌شده: {fa_int(info.cheating_strikes)}")
    if info.pregnant:
        lines.append("🤰 بارداری در راهه...")
    return "\n".join(lines)


def family_history_list(entries: list[FamilyHistoryEntryData]) -> str:
    if not entries:
        return "📜 تاریخچه خانوادگی‌ات خالیه."
    rows = ["📜 تاریخچه خانواده:\n"]
    for entry in entries:
        label = _EVENT_LABELS.get(entry.event_type, entry.event_type)
        rows.append(f"{label} — {_date(entry.created_at)}\n   {entry.note}")
    return "\n".join(rows)


def commands_help() -> str:
    """The command list — text commands only, no menu, no buttons."""
    return (
        "👨‍👩‍👧 سیستم ازدواج و خانواده (فقط با دستور، بدون منو):\n\n"
        f"«{constants.MARRIAGE_TRIGGER}» — ریپلای روی پیام طرف مقابل = درخواست ازدواج\n"
        f"«{constants.MARRIAGE_ACCEPT_TRIGGER}» — قبول درخواست\n"
        f"«{constants.MARRIAGE_REJECT_TRIGGER}» — رد درخواست\n"
        f"«{constants.MARRIAGE_CANCEL_TRIGGER}» — لغو درخواست خودت\n"
        f"«{constants.DIVORCE_TRIGGER}» — طلاق (با پرداخت مهریه)\n"
        f"«{constants.RELATIONSHIP_TRIGGER}» — ریپلای روی پیام همسر\n"
        f"«{constants.CHEATING_TRIGGER}» — خیانت (پنهان)\n"
        f"«{constants.FAMILY_TRIGGER}» — اطلاعات خانواده\n"
        f"«{constants.CHILDREN_TRIGGER}» — فرزندان\n"
        f"«{constants.FAMILY_HISTORY_TRIGGER}» — تاریخچه خانواده"
    )
