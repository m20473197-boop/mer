"""Player-facing texts for the player domain (welcome, profile, status)."""

from __future__ import annotations

from app.bot.messages.formatters import fa_int, money
from app.game.player.dto import ProfileData, StatusData


def welcome_new_player(profile: ProfileData) -> str:
    """First-time ``/start`` greeting."""
    return (
        f"سلام {profile.display_name} جان! 🎉\n"
        "به شهر خوش اومدی! زندگی دومت از همین‌جا شروع می‌شه 😎\n\n"
        "یه پروفایل تازه هم برات ساختم؛ همه‌چی از صفر شروع می‌شه.\n"
        "از منوی پایین یه گزینه انتخاب کن 👇"
    )


def welcome_back_player(profile: ProfileData) -> str:
    """Greeting for returning players (no duplicate profile is created)."""
    return (
        f"سلام {profile.display_name}! 👋\n"
        "خوش برگشتی، جا برایت خالی بود 😄\n\n"
        "از منوی پایین ادامه بده 👇"
    )


def _format_progress(percent: float) -> str:
    """Format progress percent as Persian digits, e.g. 50% -> ۵۰٪."""
    # Keep one decimal if needed, otherwise integer
    if percent >= 99.95:
        percent = 100.0
    # Round to 1 decimal for display but avoid .0
    rounded = round(percent, 1)
    if rounded == int(rounded):
        return f"{fa_int(int(rounded))}٪"
    # For decimal, replace dot with Persian decimal? Keep simple latin dot
    # and Persian digits for integer part
    int_part = int(rounded)
    dec_part = str(rounded).split(".")[1]
    return f"{fa_int(int_part)}٫{dec_part}٪"


def profile_text(profile: ProfileData) -> str:
    """The profile screen — simple progression display."""
    # Fallback for old data where extended fields are 0
    xp_needed = profile.xp_needed_for_next or 0
    xp_in = profile.xp_in_current_level
    progress = profile.progress_percent
    total_next = profile.total_xp_for_next_level

    lines = [
        f"👤 پروفایل {profile.display_name}",
        "━━━━━━━━━━━━━━━",
        f"⭐ لول: {fa_int(profile.level)}",
        f"✨ XP: {fa_int(profile.xp)}",
        f"📈 پیشرفت لول: {fa_int(xp_in)} / {fa_int(xp_needed)}",
        f"📊 درصد پیشرفت: {_format_progress(progress)}",
        f"🎯 XP کل برای لول بعد: {fa_int(total_next)}",
        f"💰 موجودی: {money(profile.money)}",
        _family_lines(profile),
    ]
    return "\n".join(lines)


def _family_lines(profile: ProfileData) -> str:
    """The Marriage and Family block of the profile screen.

    Kept in its own helper (rather than inlined) so the profile stays one
    obvious screen per function, and so the family section can grow (child
    growth, education, family expenses) without touching progression text.
    """
    rows = [f"💍 وضعیت ازدواج: {'متأهل' if profile.married else 'مجرد'}"]
    if profile.married:
        rows.append(f"🧑 همسر: {profile.spouse_name or '—'} (شناسه {fa_int(profile.spouse_player_id or 0)})")
        rows.append(f"📅 تاریخ ازدواج: {_marriage_date(profile.marriage_date)}")
    rows.append(f"👶 فرزندان: {fa_int(profile.children_count)}")
    return "\n".join(rows)


def _marriage_date(value) -> str:
    if value is None:
        return "—"
    return value.strftime("%Y/%m/%d")


def status_text(status: StatusData) -> str:
    """The status screen — detailed level progress."""
    xp_needed = status.xp_needed_for_next or 0
    xp_in = status.xp_in_current_level
    progress = status.progress_percent
    total_next = status.total_xp_for_next_level

    return (
        "📊 وضعیت فعلیت:\n\n"
        f"⭐ لول: {fa_int(status.level)}\n"
        f"✨ XP کل: {fa_int(status.xp)}\n"
        f"📈 پیشرفت: {fa_int(xp_in)} / {fa_int(xp_needed)}\n"
        f"📊 درصد: {_format_progress(progress)}\n"
        f"🎯 تا لول بعد: {fa_int(total_next)} XP کل لازمه\n"
        f"💰 موجودی: {money(status.money)}"
    )


def level_comment(level: int) -> str:
    """A touch of flavour so the profile feels alive, not robotic."""
    if level < 3:
        return "هنوز اول راهی، ولی شروع خوبی بوده 😎"
    if level < 6:
        return "داری کم‌کم یه رونق حسابی راه می‌ندازی 👏"
    if level < 11:
        return "این شهر کم‌کم اسمت رو می‌شنوه 🔥"
    return "تو دیگه از چهره‌های همیشگی این شهری 👑"


def level_up_text(old_level: int, new_level: int) -> str:
    """Message shown when a player levels up."""
    return (
        f"🎉 لول آپ! {fa_int(old_level)} → {fa_int(new_level)}\n"
        f"تبریک! رسیدی به لول {fa_int(new_level)} 🔥"
    )


def xp_added_text(amount: int, reason: str, new_total: int) -> str:
    """Message for XP addition (used by admin commands)."""
    return (
        f"✨ {fa_int(amount)} XP اضافه شد\n"
        f"📝 دلیل: {reason}\n"
        f"📊 XP فعلی: {fa_int(new_total)}"
    )


def xp_removed_text(amount: int, reason: str, new_total: int) -> str:
    """Message for XP removal."""
    return (
        f"➖ {fa_int(amount)} XP کم شد\n"
        f"📝 دلیل: {reason}\n"
        f"📊 XP فعلی: {fa_int(new_total)}"
    )
