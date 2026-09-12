"""Natural Persian messages for the Iranian bank UI."""

from __future__ import annotations

from app.bot.messages.formatters import fa_int, money
from app.game.bank.catalog import BANK_INTEREST_RATE_PERCENT
from app.game.bank.dto import (
    BankAccountData,
    BankDepositResult,
    BankInterestResult,
    BankTransactionData,
    BankTransferPreview,
    BankTransferResult,
    BankWithdrawalResult,
)


def bank_menu_text(account: BankAccountData) -> str:
    return (
        "🏦 بانک ایران\n\n"
        f"موجودی بانک: {money(account.balance)}\n"
        f"شماره کارت: {account.card_number}\n\n"
        "یکی از خدمات بانک را انتخاب کن:"
    )


def balance_text(account: BankAccountData) -> str:
    return (
        "💰 موجودی بانک\n\n"
        f"موجودی حساب: {money(account.balance)}\n"
        f"شماره کارت: {account.card_number}"
    )


def card_text(account: BankAccountData) -> str:
    return (
        "💳 شماره کارت بانک ایران\n\n"
        f"{account.card_number}\n\n"
        "این شماره کارت دائمی است و برای انتقال وجه استفاده می‌شود."
    )


def deposit_prompt() -> str:
    return "💵 مبلغ سپرده‌گذاری را به تومان و به‌صورت عدد صحیح بفرست:"


def withdrawal_prompt() -> str:
    return "💸 مبلغ برداشت را به تومان و به‌صورت عدد صحیح بفرست:"


def transfer_card_prompt() -> str:
    return "💳 شماره کارت مقصد را (۱۶ رقم) بفرست:"


def transfer_recipient_text(preview: BankTransferPreview) -> str:
    return (
        "🔎 گیرنده پیدا شد\n\n"
        f"نام گیرنده: {preview.recipient_name}\n"
        f"شماره کارت: {preview.recipient_card_number}\n\n"
        "اگر اطلاعات درست است، ادامه را بزن."
    )


def transfer_amount_prompt(preview: BankTransferPreview) -> str:
    return (
        f"گیرنده: {preview.recipient_name}\n"
        f"کارت: {preview.recipient_card_number}\n\n"
        "مبلغ انتقال را به تومان و به‌صورت عدد صحیح بفرست:"
    )


def transfer_confirmation_text(
    preview: BankTransferPreview, amount: int
) -> str:
    return (
        "⚠️ تأیید انتقال وجه\n\n"
        f"گیرنده: {preview.recipient_name}\n"
        f"کارت مقصد: {preview.recipient_card_number}\n"
        f"مبلغ: {money(amount)}\n\n"
        "برای انجام نهایی انتقال، تأیید را بزن. موجودی در همان لحظه دوباره بررسی می‌شود."
    )


def deposit_success(result: BankDepositResult) -> str:
    return (
        "✅ سپرده‌گذاری با موفقیت انجام شد.\n\n"
        f"مبلغ واریزی: {money(result.amount)}\n"
        f"موجودی بانک: {money(result.account.balance)}\n"
        f"موجودی کیف پول: {money(result.wallet_balance_after)}"
    )


def withdrawal_success(result: BankWithdrawalResult) -> str:
    return (
        "✅ برداشت با موفقیت انجام شد.\n\n"
        f"مبلغ برداشت: {money(result.amount)}\n"
        f"موجودی بانک: {money(result.account.balance)}\n"
        f"موجودی کیف پول: {money(result.wallet_balance_after)}"
    )


def transfer_success(result: BankTransferResult) -> str:
    return (
        "✅ انتقال وجه با موفقیت انجام شد.\n\n"
        f"مبلغ انتقال: {money(result.amount)}\n"
        f"شماره کارت مقصد: {result.recipient_account.card_number}\n"
        f"موجودی بانک شما: {money(result.sender_account.balance)}"
    )


def interest_notice(result: BankInterestResult) -> str:
    if result.processed_days <= 0:
        return ""
    return (
        f"🎁 سود روزانه بانک ({fa_int(BANK_INTEREST_RATE_PERCENT)}٪) برای "
        f"{fa_int(result.processed_days)} روز ثبت شد: {money(result.interest_amount)}"
    )


def history_text(
    transactions: tuple[BankTransactionData, ...], page: int, total: int
) -> str:
    header = (
        "📜 تاریخچه تراکنش‌های بانک\n"
        f"صفحه {fa_int(page + 1)} — مجموع {fa_int(total)} تراکنش\n"
    )
    if not transactions:
        return header + "\nهنوز تراکنشی ثبت نشده است."
    lines = [header]
    for transaction in transactions:
        lines.append(
            "\n"
            f"{transaction_type_label(transaction.transaction_type)}\n"
            f"مبلغ: {money(transaction.amount)}\n"
            f"وضعیت: {status_label(transaction.status)}\n"
            f"شناسه: {transaction.transaction_id}"
        )
    return "\n".join(lines)


def transaction_type_label(transaction_type: str) -> str:
    return {
        "deposit": "💵 سپرده‌گذاری",
        "withdrawal": "💸 برداشت",
        "transfer_sent": "📤 انتقال وجه ارسالی",
        "transfer_received": "📥 انتقال وجه دریافتی",
        "interest": "🎁 سود روزانه",
    }.get(transaction_type, "🧾 تراکنش بانکی")


def status_label(status: str) -> str:
    return {"completed": "✅ موفق", "failed": "❌ ناموفق"}.get(status, status)


def invalid_amount_text() -> str:
    return "❌ مبلغ باید یک عدد صحیحِ بزرگ‌تر از صفر و به تومان باشد."


def invalid_card_text() -> str:
    return "❌ شماره کارت نامعتبر است. شماره کارت باید ۱۶ رقم باشد."


def recipient_not_found_text() -> str:
    return "❌ گیرنده‌ای با این شماره کارت پیدا نشد. شماره کارت را بررسی کن."


def self_transfer_text() -> str:
    return "❌ نمی‌توانی به شماره کارت خودت انتقال وجه انجام بدهی."


def insufficient_bank_text() -> str:
    return "❌ موجودی بانک برای این عملیات کافی نیست."


def insufficient_wallet_text() -> str:
    return "❌ موجودی کیف پول برای سپرده‌گذاری کافی نیست."


def not_registered_text() -> str:
    return "هنوز حساب بازی‌ات ساخته نشده است. با /start شروع کن."


def operation_error_text() -> str:
    return "⚠️ انجام عملیات بانکی ممکن نشد. لطفاً دوباره تلاش کن."


def cancelled_text() -> str:
    return "عملیات بانکی لغو شد."
