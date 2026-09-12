"""Admin development commands — protected by ADMIN_IDS.

These commands are for testing the Level/XP system:
    /admin_add_xp [amount] [reason] [target_telegram_id]
    /admin_remove_xp [amount] [reason] [target_telegram_id]
    /admin_set_level [level] [target_telegram_id]
    /admin_status [target_telegram_id]
    /admin_xp_history [target_telegram_id]

Only users whose Telegram ID is in settings.admin_ids can use them.
If ADMIN_IDS is empty, no one is admin — commands are effectively disabled.
"""

from __future__ import annotations

import logging
from typing import List

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.context import get_services
from app.bot.messages import player as player_messages
from app.bot.messages.formatters import fa_int
from app.core.config import Settings, load_database_url
from app.core.config import load_settings as _load_settings
from app.game.shared.errors import InvalidAmountError, PlayerNotFoundError

logger = logging.getLogger(__name__)

# Cache settings for admin check to avoid re-loading env on every command?
# We will fetch from bot_data if available, else load.
def _get_settings(context: ContextTypes.DEFAULT_TYPE) -> Settings | None:
    # Try to get from application bot_data if we stored it, else load
    # In main.py we don't store settings in bot_data, so load from env
    try:
        return _load_settings()
    except Exception:
        return None


def _is_admin(user_id: int, settings: Settings | None) -> bool:
    if settings is None:
        return False
    return user_id in settings.admin_ids


async def _check_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if user is None:
        return False
    settings = _get_settings(context)
    if not _is_admin(user.id, settings):
        # Not admin — silent ignore or friendly Persian message
        if update.message:
            await update.message.reply_text(
                "⛔ این دستور فقط برای ادمین‌هاست."
            )
        logger.warning("Unauthorized admin command attempt by user %s", user.id)
        return False
    return True


def _parse_args(args: List[str]) -> dict:
    """Simple arg parser for admin commands."""
    # Returns dict with amount/level, reason, target_id
    return {"raw": args}


async def admin_add_xp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add XP to a player (default: self). Usage: /admin_add_xp 100 reason [tg_id]"""
    if not await _check_admin(update, context):
        return
    if update.message is None or update.effective_user is None:
        return

    services = get_services(context)
    args = context.args or []

    if not args:
        await update.message.reply_text(
            "❓ استفاده: /admin_add_xp <مقدار> [دلیل] [آیدی تلگرام]\n"
            "مثال: /admin_add_xp 100 تست\n"
            "مثال: /admin_add_xp 50 جایزه 123456789"
        )
        return

    # Parse: first arg is amount, last arg might be telegram_id if numeric and > 1e6?
    # Heuristic: if last arg is all digits and len > 6 and we have at least 2 args, treat as target tg_id
    # Otherwise, target is the admin himself
    try:
        amount = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ مقدار XP باید عدد باشه.")
        return

    if amount <= 0:
        await update.message.reply_text("❌ مقدار باید مثبت باشه.")
        return

    # Detect target telegram_id
    target_tg_id = update.effective_user.id
    reason_parts = args[1:]

    if reason_parts:
        # If last part looks like a telegram user id (numeric, >= 5 digits), treat as target
        last = reason_parts[-1]
        if last.lstrip("-").isdigit() and len(last) >= 5:
            # Could be target id — check if it's plausible and not part of reason?
            # If we have at least 1 reason part before, or if args length >=3, we treat last as target
            # Simpler: if last is numeric and user explicitly passed it, we try to interpret
            # We will check: if last token is integer and (len(args)>=3 or reason_parts length==1 and int(last) > 10000)
            # To avoid ambiguity, we support explicit: if last token is numeric and > 100000 (typical tg ids are 9 digits)
            try:
                possible_id = int(last)
                if possible_id > 10000 and (len(args) >= 3 or possible_id > 100000):
                    target_tg_id = possible_id
                    reason_parts = reason_parts[:-1]
            except ValueError:
                pass

    reason = " ".join(reason_parts).strip() or "admin_add_xp"

    # Resolve player_id from telegram_user_id
    # We need to get player by telegram id — use player service
    # PlayerService doesn't have get_by_tg_id returning player_id, but we can use repository via service?
    # We'll use services.players.get_profile to check existence, but we need player_id.
    # Let's use a direct approach: call register_or_get? No, we should fetch player_id via service.
    # For simplicity, we will use the database session via services.players internal?
    # Instead, we will use services.players.get_status to check, but we need player_id for level service.
    # We'll add a helper: get player_id by telegram id using player service's repository logic.
    # Quick workaround: use services.players._session_factory? It's private but accessible.
    # Better: add method to PlayerService to get player_id by telegram id. For now, we do direct DB query here.

    from app.database.repositories.player_repository import PlayerRepository

    # Get player_id
    async with services.players._session_factory() as session:  # type: ignore
        repo = PlayerRepository(session)
        player = await repo.get_by_telegram_user_id(target_tg_id)
        if player is None:
            await update.message.reply_text(
                f"❌ بازیکن با آیدی تلگرام {fa_int(target_tg_id)} پیدا نشد.\n"
                "اول باید /start بزنه."
            )
            return
        player_id = player.id
        display_name = player.display_name

    try:
        result = await services.levels.add_xp(player_id, amount, reason)
    except (InvalidAmountError, PlayerNotFoundError) as exc:
        await update.message.reply_text(f"❌ خطا: {exc}")
        return
    except Exception as exc:
        logger.error("admin_add_xp failed", exc_info=exc)
        await update.message.reply_text("❌ خطای داخلی.")
        return

    text = (
        f"✅ {fa_int(amount)} XP به {display_name} اضافه شد.\n"
        f"📝 دلیل: {result.reason}\n"
        f"📊 XP: {fa_int(result.xp_before)} → {fa_int(result.xp_after)}\n"
        f"⭐ لول: {fa_int(result.old_level)} → {fa_int(result.new_level)}\n"
    )
    if result.leveled_up:
        text += f"\n{player_messages.level_up_text(result.old_level, result.new_level)}"
    else:
        prog = await services.levels.get_progress(player_id)
        text += f"\n📈 پیشرفت: {fa_int(prog.xp_in_current_level)} / {fa_int(prog.xp_needed_for_next)} ({prog.progress_percent:.1f}٪)"

    await update.message.reply_text(text)


async def admin_remove_xp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove XP from a player."""
    if not await _check_admin(update, context):
        return
    if update.message is None or update.effective_user is None:
        return

    services = get_services(context)
    args = context.args or []

    if not args:
        await update.message.reply_text(
            "❓ استفاده: /admin_remove_xp <مقدار> [دلیل] [آیدی تلگرام]"
        )
        return

    try:
        amount = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ مقدار XP باید عدد باشه.")
        return

    target_tg_id = update.effective_user.id
    reason_parts = args[1:]
    if reason_parts:
        last = reason_parts[-1]
        if last.lstrip("-").isdigit() and len(last) >= 5:
            try:
                possible_id = int(last)
                if possible_id > 10000 and (len(args) >= 3 or possible_id > 100000):
                    target_tg_id = possible_id
                    reason_parts = reason_parts[:-1]
            except ValueError:
                pass

    reason = " ".join(reason_parts).strip() or "admin_remove_xp"

    from app.database.repositories.player_repository import PlayerRepository

    async with services.players._session_factory() as session:  # type: ignore
        repo = PlayerRepository(session)
        player = await repo.get_by_telegram_user_id(target_tg_id)
        if player is None:
            await update.message.reply_text(
                f"❌ بازیکن با آیدی تلگرام {fa_int(target_tg_id)} پیدا نشد."
            )
            return
        player_id = player.id
        display_name = player.display_name

    try:
        result = await services.levels.remove_xp(player_id, amount, reason)
    except InvalidAmountError as exc:
        await update.message.reply_text(f"❌ {exc}")
        return
    except PlayerNotFoundError:
        await update.message.reply_text("❌ بازیکن پیدا نشد.")
        return
    except Exception as exc:
        logger.error("admin_remove_xp failed", exc_info=exc)
        await update.message.reply_text("❌ خطای داخلی.")
        return

    text = (
        f"✅ {fa_int(amount)} XP از {display_name} کم شد.\n"
        f"📝 دلیل: {result.reason}\n"
        f"📊 XP: {fa_int(result.xp_before)} → {fa_int(result.xp_after)}\n"
        f"⭐ لول: {fa_int(result.old_level)} → {fa_int(result.new_level)}"
    )
    await update.message.reply_text(text)


async def admin_set_level(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set player's level directly."""
    if not await _check_admin(update, context):
        return
    if update.message is None or update.effective_user is None:
        return

    services = get_services(context)
    args = context.args or []

    if not args:
        await update.message.reply_text(
            "❓ استفاده: /admin_set_level <لول> [آیدی تلگرام]\n"
            "مثال: /admin_set_level 5\n"
            "مثال: /admin_set_level 10 123456789"
        )
        return

    try:
        level = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ لول باید عدد باشه.")
        return

    if level < 1:
        await update.message.reply_text("❌ لول باید حداقل ۱ باشه.")
        return

    target_tg_id = update.effective_user.id
    if len(args) >= 2:
        try:
            target_tg_id = int(args[1])
        except ValueError:
            await update.message.reply_text("❌ آیدی تلگرام باید عدد باشه.")
            return

    from app.database.repositories.player_repository import PlayerRepository

    async with services.players._session_factory() as session:  # type: ignore
        repo = PlayerRepository(session)
        player = await repo.get_by_telegram_user_id(target_tg_id)
        if player is None:
            await update.message.reply_text(
                f"❌ بازیکن با آیدی تلگرام {fa_int(target_tg_id)} پیدا نشد."
            )
            return
        player_id = player.id
        display_name = player.display_name

    try:
        result = await services.levels.set_level(player_id, level, reason="admin_set_level")
    except InvalidAmountError as exc:
        await update.message.reply_text(f"❌ {exc}")
        return
    except Exception as exc:
        logger.error("admin_set_level failed", exc_info=exc)
        await update.message.reply_text("❌ خطای داخلی.")
        return

    text = (
        f"✅ لول {display_name} تنظیم شد به {fa_int(level)}\n"
        f"📊 XP: {fa_int(result.xp_before)} → {fa_int(result.xp_after)}\n"
        f"⭐ لول: {fa_int(result.old_level)} → {fa_int(result.new_level)}"
    )
    await update.message.reply_text(text)


async def admin_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show detailed XP status for a player."""
    if not await _check_admin(update, context):
        return
    if update.message is None or update.effective_user is None:
        return

    services = get_services(context)
    args = context.args or []

    target_tg_id = update.effective_user.id
    if args:
        try:
            target_tg_id = int(args[0])
        except ValueError:
            await update.message.reply_text("❌ آیدی باید عدد باشه.")
            return

    from app.database.repositories.player_repository import PlayerRepository

    async with services.players._session_factory() as session:  # type: ignore
        repo = PlayerRepository(session)
        player = await repo.get_by_telegram_user_id(target_tg_id)
        if player is None:
            await update.message.reply_text(
                f"❌ بازیکن با آیدی {fa_int(target_tg_id)} پیدا نشد."
            )
            return
        player_id = player.id

    try:
        progress = await services.levels.get_progress(player_id)
        profile = await services.players.get_profile(target_tg_id)
    except Exception as exc:
        logger.error("admin_status failed", exc_info=exc)
        await update.message.reply_text("❌ خطای داخلی.")
        return

    if profile is None:
        await update.message.reply_text("❌ پروفایل پیدا نشد.")
        return

    text = (
        f"📊 وضعیت {profile.display_name} ({fa_int(target_tg_id)}):\n\n"
        f"⭐ لول: {fa_int(progress.level)}\n"
        f"✨ XP کل: {fa_int(progress.total_xp)}\n"
        f"📈 داخل لول: {fa_int(progress.xp_in_current_level)} / {fa_int(progress.xp_needed_for_next)}\n"
        f"📊 درصد: {progress.progress_percent:.1f}٪\n"
        f"🎯 XP برای لول بعد: {fa_int(progress.total_xp_for_next_level)} کل\n"
        f"💰 پول: {fa_int(profile.money)}"
    )
    await update.message.reply_text(text)


async def admin_xp_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show recent XP history."""
    if not await _check_admin(update, context):
        return
    if update.message is None or update.effective_user is None:
        return

    services = get_services(context)
    args = context.args or []

    target_tg_id = update.effective_user.id
    if args:
        try:
            target_tg_id = int(args[0])
        except ValueError:
            await update.message.reply_text("❌ آیدی باید عدد باشه.")
            return

    from app.database.repositories.player_repository import PlayerRepository

    async with services.players._session_factory() as session:  # type: ignore
        repo = PlayerRepository(session)
        player = await repo.get_by_telegram_user_id(target_tg_id)
        if player is None:
            await update.message.reply_text("❌ بازیکن پیدا نشد.")
            return
        player_id = player.id
        display_name = player.display_name

    try:
        history = await services.levels.get_xp_history(player_id, limit=10)
    except Exception as exc:
        logger.error("admin_xp_history failed", exc_info=exc)
        await update.message.reply_text("❌ خطای داخلی.")
        return

    if not history:
        await update.message.reply_text(f"📭 تاریخچه XP برای {display_name} خالیه.")
        return

    lines = [f"📜 تاریخچه XP برای {display_name} (آخرین {len(history)}):\n"]
    for tx in history:
        sign = "+" if tx.amount > 0 else ""
        lines.append(
            f"{sign}{fa_int(tx.amount)} XP | {tx.reason} | {tx.created_at.strftime('%Y-%m-%d %H:%M')}"
        )
    await update.message.reply_text("\n".join(lines))
