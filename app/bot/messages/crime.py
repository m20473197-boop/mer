"""Natural Persian player-facing text for the fictional خلاف system."""

from __future__ import annotations

from datetime import datetime

from app.bot.messages.formatters import fa_int


def menu_text() -> str:
    return (
        "🕳️ <b>خلاف</b>\n\n"
        "یک فعالیت را انتخاب کن. همه نتیجه‌ها و پرداخت‌ها ثبت می‌شوند و شوتی فقط از همین بخش در دسترس است."
    )


def target_prompt(kind: str) -> str:
    if kind == "information":
        return (
            "🕵️ برای اطلاعات‌فروشی، به پیام بازیکن موردنظر پاسخ بده و همان پیام را ارسال کن.\n"
            "به پیام خودت یا ربات نمی‌شود هدف زد."
        )
    return (
        "💻 برای هک بانکی، به پیام بازیکن موردنظر پاسخ بده و همان پیام را ارسال کن.\n"
        "هدف باید حساب بانکی فعال L.I.R داشته باشد."
    )


def laundering_prompt(min_amount: int, max_amount: int) -> str:
    return (
        "💰 مبلغ کیف پول را به تومان و به‌صورت یک عدد صحیح مثبت بفرست.\n"
        f"حداقل: {fa_int(min_amount)} تومان — حداکثر: {fa_int(max_amount)} تومان\n"
        "درصد کارمزد قبل از شروع نشان داده می‌شود و پرداخت نهایی بعد از پردازش انجام خواهد شد."
    )


def invalid_amount() -> str:
    return "❌ مبلغ باید یک عدد صحیح مثبت باشد و داخل بازه مجاز قرار بگیرد."


def insufficient_wallet() -> str:
    return "❌ موجودی کیف پولت برای این عملیات کافی نیست؛ هیچ مبلغی کم نشد."


def cooldown(remaining_seconds: int) -> str:
    minutes, seconds = divmod(max(0, remaining_seconds), 60)
    if minutes:
        return f"⏳ برای تلاش دوباره باید {fa_int(minutes)} دقیقه و {fa_int(seconds)} ثانیه صبر کنی."
    return f"⏳ برای تلاش دوباره {fa_int(seconds)} ثانیه صبر کن."


def invalid_target() -> str:
    return "❌ هدف پیدا نشد، ربات است یا نمی‌توانی خودت را هدف بگیری. به پیام یک بازیکن ثبت‌نام‌شده پاسخ بده."


def not_registered() -> str:
    return "❌ ابتدا باید در بازی ثبت‌نام کنی."


def information_result(result) -> str:
    if result.success:
        return (
            f"🕵️ اطلاعات‌فروشی موفق شد.\n"
            f"هدف: {result.target_name}\n\n{result.information}\n\n"
            f"💵 پاداش: {fa_int(result.reward_amount)} تومان"
        )
    return f"🕵️ اطلاعات‌فروشی ناموفق بود.\n{result.information}\nپاداشی پرداخت نشد."


def laundering_started(result) -> str:
    return (
        "💰 درخواست پول‌شویی ثبت شد.\n"
        f"مبلغ برداشت‌شده: {fa_int(result.amount)} تومان\n"
        f"کارمزد: {fa_int(result.fee_amount)} تومان\n"
        f"دریافتی نهایی: {fa_int(result.final_amount)} تومان\n"
        f"زمان تکمیل: {format_time(result.process_at)}\n"
        "تا قبل از تکمیل، این عملیات در وضعیت «در انتظار» است."
    )


def laundering_history(rows) -> str:
    if not rows:
        return "💰 هنوز هیچ درخواست پول‌شویی ثبت نکرده‌ای."
    lines = ["💰 <b>تاریخچه پول‌شویی</b>"]
    for row in rows[:8]:
        status = {
            "pending": "در انتظار",
            "processing": "در حال پردازش",
            "completed": "تکمیل‌شده",
            "failed": "ناموفق",
        }.get(row.status, row.status)
        lines.append(
            f"• {fa_int(row.amount)} → {fa_int(row.final_amount)} تومان | {status}"
        )
    return "\n".join(lines)


def documents_menu(rows) -> str:
    if not rows:
        return "🪪 <b>مدارک جعلی</b>\n\nمدرک فعالی نداری. یک نوع مدرک را انتخاب کن."
    active = [row for row in rows if row.status == "active"]
    return (
        "🪪 <b>مدارک جعلی</b>\n\n"
        f"مدرک فعال: {fa_int(len(active))}\n"
        "نوع مدرک را برای صدور انتخاب کن."
    )


def document_issued(document) -> str:
    expiry = "بدون انقضا" if document.expires_at is None else format_time(document.expires_at)
    return (
        f"🪪 {document.document_name} صادر شد.\n"
        f"وضعیت: فعال\nانقضا: {expiry}\n"
        "این رکورد برای بررسی مالکیت و تاریخچه ذخیره شد."
    )


def duplicate_document() -> str:
    return "❌ از این نوع مدرک جعلی، یک نمونه فعال داری. ابتدا باید منقضی شود."


def invalid_document() -> str:
    return "❌ این نوع مدرک در کاتالوگ خلاف وجود ندارد."


def shoti_no_vehicle() -> str:
    return "🏎️ برای شوتی باید یکی از پژو ۴۰۵، پژو پارس، زانتیا یا سمند را داشته باشی."


def shoti_vehicle_prompt() -> str:
    return "🏎️ یک خودرو برای مأموریت شوتی انتخاب کن. در هر لحظه فقط یک مأموریت فعال مجاز است."


def shoti_started(mission) -> str:
    return (
        "🏎️ مأموریت شوتی شروع شد.\n"
        f"مسیر: {mission.origin} ← {mission.destination}\n"
        f"بار: {mission.shipment}\n"
        f"خودرو: {mission.vehicle_name}\n"
        f"پاداش احتمالی: {fa_int(mission.reward)} تومان\n"
        f"سختی: {fa_int(mission.difficulty)}٪ | ریسک: {fa_int(mission.risk)}٪\n"
        f"تسویه: {format_time(mission.completes_at)}\n"
        "نتیجه پس از پایان زمان مأموریت به‌صورت خودکار ثبت می‌شود."
    )


def shoti_history(rows) -> str:
    if not rows:
        return "🏎️ هنوز مأموریت شوتی ثبت نکرده‌ای."
    lines = ["🏎️ <b>وضعیت مأموریت‌های شوتی</b>"]
    for row in rows[:8]:
        if row.status in {"pending", "processing"}:
            status = "فعال"
        elif row.success:
            status = f"موفق؛ {fa_int(row.reward)} تومان پرداخت شد"
        else:
            status = "ناموفق؛ بدون پرداخت"
        lines.append(f"• {row.origin} ← {row.destination} | {status}")
    return "\n".join(lines)


def active_mission() -> str:
    return "❌ یک مأموریت شوتی فعال داری؛ تا تسویه آن مأموریت دیگری نمی‌توانی شروع کنی."


def vehicle_not_owned() -> str:
    return "❌ این خودرو متعلق به تو نیست یا برای شوتی مجاز نیست."


def hack_result(result) -> str:
    if result.success:
        return (
            f"💻 نفوذ به حساب «{result.target_name}» موفق بود.\n"
            f"💵 مبلغ منتقل‌شده به بانک تو: {fa_int(result.transferred_amount)} تومان"
        )
    return f"💻 نفوذ ناموفق بود.\n{result.reason}\nهیچ انتقالی انجام نشد."


def target_without_bank() -> str:
    return "❌ هدف حساب بانکی فعال L.I.R ندارد؛ عملیات هک انجام نشد."


def generic_error() -> str:
    return "⚠️ انجام عملیات خلاف ممکن نشد. دوباره تلاش کن."


def history_text(rows, total: int) -> str:
    if not rows:
        return "📜 هنوز سابقه‌ای برای خلاف ثبت نشده است."
    lines = [f"📜 <b>تاریخچه خلاف</b> — {fa_int(total)} رکورد"]
    names = {
        "information_selling": "اطلاعات‌فروشی",
        "money_laundering": "پول‌شویی",
        "fake_document": "مدرک جعلی",
        "shoti": "شوتی",
        "bank_hack": "هک بانکی",
    }
    for row in rows:
        status = "موفق" if row.success else "ناموفق" if row.success is False else "در انتظار"
        lines.append(f"• {names.get(row.activity_type, 'خلاف')} | {status} | {format_time(row.created_at)}")
    return "\n".join(lines)


def format_time(value: datetime) -> str:
    return value.astimezone().strftime("%Y/%m/%d %H:%M")
