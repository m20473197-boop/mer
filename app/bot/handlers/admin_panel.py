"""Admin panel handlers — the professional management interface.

Entry point: the ``/admin`` command (admins only). Everything else is
button-driven through the ``adm_`` callback namespace, handled by a single
router (:func:`admin_callback`).

Free-text values (amounts, names, settings) flow through one generic
``ConversationHandler`` (see ``register_handlers``): buttons that need input
use the ``adm_in_<code>[_<target>[_<extra>]]`` namespace as conversation
entry points (:func:`admin_input_entry`); the typed reply lands in
:func:`admin_input_received`, which validates, executes and reports back.
Tapping any other admin button cancels a pending input.
"""

from __future__ import annotations

import logging

from telegram import CallbackQuery, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler

from app.bot.context import get_services
from app.bot.keyboards import admin as admin_keyboards
from app.bot.keyboards import callbacks
from app.bot.keyboards.admin import LOG_TITLES
from app.bot.messages import admin as admin_messages
from app.bot.messages import errors as message_errors
from app.bot.messages.formatters import fa_int, money
from app.core import constants
from app.core.config import load_settings
from app.game.admin import auth as admin_auth
from app.game.admin import dto as admin_dto
from app.game.admin import runtime as admin_runtime
from app.game.admin.parsing import parse_admin_float, parse_admin_int
from app.game.shared.errors import DomainError

logger = logging.getLogger(__name__)

# Conversation state: the admin owes us one typed value.
ADMIN_INPUT: int = 1

PENDING_KEY: str = "adm_pending"

# Text message that opens the admin panel (admins only).
ADMIN_PANEL_TEXT_TRIGGER: str = "پنل"

_KITCHEN_OPTIONS = ("مدرن", "معمولی", "قدیمی")
_QUALITY_OPTIONS = ("عالی", "خوب", "متوسط", "ضعیف")

# Reward-setting codes (callback suffix → service key + Persian label).
_REWARD_LABELS = {
    "pxd": "مقسوم XP خرید",
    "pxn": "کف XP خرید",
    "pxx": "سقف XP خرید",
    "cxd": "مقسوم XP ساخت‌وساز",
}

# House-edit field codes → (service field, prompt key).
_HOUSE_FIELDS = {
    "area": ("area_sqm", "ha_area"),
    "bed": ("bedrooms", "ha_bed"),
    "bath": ("bathrooms", "ha_bath"),
    "liv": ("living_rooms", "ha_liv"),
    "year": ("construction_year", "ha_year"),
    "loc": ("location", "ha_loc"),
    "ovr": ("override", "ha_ovr"),
}

# Land-edit field codes → (service field, prompt key).
_LAND_FIELDS = {
    "area": ("area_sqm", "la_area"),
    "loc": ("location", "la_loc"),
    "ovr": ("override", "la_ovr"),
}


# --- Auth helpers ---------------------------------------------------------------

def _admin_ids(context: ContextTypes.DEFAULT_TYPE) -> tuple[int, ...]:
    """Admin IDs from bot_data, falling back to settings, then the owner ID."""
    try:
        stored = context.application.bot_data.get("admin_ids")
    except Exception:  # pragma: no cover — defensive
        stored = None
    if stored:
        return tuple(stored)
    try:
        return tuple(load_settings().admin_ids)
    except Exception:
        return tuple(constants.ADMIN_TELEGRAM_IDS)


def _is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if user is None:
        return False
    return admin_auth.is_admin(user.id, _admin_ids(context))


async def _deny_query(query: CallbackQuery) -> None:
    await query.answer(text=admin_messages.NOT_ADMIN, show_alert=True)


async def _edit(query: CallbackQuery, text: str, markup=None) -> None:
    try:
        await query.edit_message_text(text=text, reply_markup=markup)
    except BadRequest as exc:
        if "not modified" in str(exc).lower():
            logger.debug("Ignored identical admin message edit")
        else:
            raise


def _parse_id(raw: str) -> int | None:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


# --- /admin command ---------------------------------------------------------------

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Open the admin panel (``پنل``) — admins only."""
    if update.message is None or update.effective_user is None:
        return ConversationHandler.END
    if not _is_admin(update, context):
        logger.warning(
            "Unauthorized admin-panel attempt by user %s", update.effective_user.id
        )
        await update.message.reply_text(admin_messages.NOT_ADMIN)
        return ConversationHandler.END
    context.user_data.pop(PENDING_KEY, None)
    await update.message.reply_text(
        admin_messages.ADMIN_MENU_TEXT,
        reply_markup=admin_keyboards.build_admin_menu(),
    )
    return ConversationHandler.END


# --- Callback router ---------------------------------------------------------------

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Route every ``adm_`` callback (also cancels pending typed inputs)."""
    query = update.callback_query
    if query is None or query.data is None:
        return ConversationHandler.END
    if not _is_admin(update, context):
        logger.warning(
            "Unauthorized admin-panel attempt by user %s",
            query.from_user.id if query.from_user else None,
        )
        await _deny_query(query)
        return ConversationHandler.END

    data = query.data
    # Tapping «cancel» or starting a new input never pops first — the entry
    # handler takes over the pending slot explicitly.
    if data == callbacks.ADM_IN_CANCEL:
        return await admin_input_cancel(update, context)
    if data.startswith(callbacks.ADM_IN_PREFIX):
        return await admin_input_entry(update, context)

    # Any other button cancels a pending typed input.
    context.user_data.pop(PENDING_KEY, None)
    await query.answer()

    try:
        await _route(query, context, data)
    except DomainError as exc:
        logger.info("Admin action failed: %s", exc)
        await _edit(
            query, f"❌ {exc}", admin_keyboards.build_back_to_admin()
        )
    except Exception:  # noqa: BLE001 — never crash the panel on one screen
        logger.exception("Admin panel error on %r", data)
        await _edit(
            query, message_errors.GENERIC, admin_keyboards.build_back_to_admin()
        )
    return ConversationHandler.END


async def _route(
    query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, data: str
) -> None:
    services = get_services(context)
    admin_id = query.from_user.id

    if data == callbacks.ADM_MENU:
        await _edit(
            query, admin_messages.ADMIN_MENU_TEXT,
            admin_keyboards.build_admin_menu(),
        )
        return
    if data == callbacks.ADM_DASH:
        stats = await services.admin.get_dashboard()
        await _edit(
            query, admin_messages.dashboard_text(stats),
            admin_keyboards.build_dashboard(),
        )
        return

    # Users
    if data.startswith(callbacks.ADM_UL_PREFIX):
        page = _parse_id(data[len(callbacks.ADM_UL_PREFIX):]) or 0
        users = await services.admin.list_users(page)
        await _edit(
            query, admin_messages.users_list_text(users),
            admin_keyboards.build_users_list(users),
        )
        return
    if data.startswith(callbacks.ADM_UTX_PREFIX):
        pid = _parse_id(data[len(callbacks.ADM_UTX_PREFIX):])
        detail = await services.admin.get_user_detail(_require_id(pid))
        entries = await services.admin.get_user_transactions(detail.summary.player_id)
        await _edit(
            query,
            admin_messages.user_tx_text(detail.summary, entries),
            admin_keyboards.build_user_back(detail.summary.player_id),
        )
        return
    if data.startswith(callbacks.ADM_UPROP_PREFIX):
        pid = _parse_id(data[len(callbacks.ADM_UPROP_PREFIX):])
        detail = await services.admin.get_user_detail(_require_id(pid))
        houses, lands = await services.admin.get_user_properties(
            detail.summary.player_id
        )
        await _edit(
            query,
            admin_messages.user_props_text(detail.summary, houses, lands),
            admin_keyboards.build_user_back(detail.summary.player_id),
        )
        return
    if data.startswith(callbacks.ADM_BANOK_PREFIX):
        pid = _parse_id(data[len(callbacks.ADM_BANOK_PREFIX):])
        await services.admin.ban_user(admin_id, _require_id(pid))
        detail = await services.admin.get_user_detail(_require_id(pid))
        await _edit(
            query,
            "🚫 کاربر مسدود شد.\n\n" + admin_messages.user_detail_text(detail),
            admin_keyboards.build_user_detail(detail.summary),
        )
        return
    if data.startswith(callbacks.ADM_UNBAN_PREFIX):
        pid = _parse_id(data[len(callbacks.ADM_UNBAN_PREFIX):])
        await services.admin.unban_user(admin_id, _require_id(pid))
        detail = await services.admin.get_user_detail(_require_id(pid))
        await _edit(
            query,
            "✅ مسدودیت کاربر برداشته شد.\n\n"
            + admin_messages.user_detail_text(detail),
            admin_keyboards.build_user_detail(detail.summary),
        )
        return
    if data.startswith(callbacks.ADM_BAN_PREFIX):
        pid = _parse_id(data[len(callbacks.ADM_BAN_PREFIX):])
        detail = await services.admin.get_user_detail(_require_id(pid))
        await _edit(
            query,
            admin_messages.ban_confirm_text(detail.summary),
            admin_keyboards.build_ban_confirm(detail.summary.player_id),
        )
        return
    if data.startswith(callbacks.ADM_U_PREFIX):
        pid = _parse_id(data[len(callbacks.ADM_U_PREFIX):])
        detail = await services.admin.get_user_detail(_require_id(pid))
        await _edit(
            query,
            admin_messages.user_detail_text(detail),
            admin_keyboards.build_user_detail(detail.summary),
        )
        return

    # Economy
    if data == callbacks.ADM_ECON:
        overview = await services.admin.get_economy_overview()
        await _edit(
            query, admin_messages.econ_text(overview),
            admin_keyboards.build_econ(overview),
        )
        return
    if data.startswith(callbacks.ADM_ASSET_PREFIX):
        code = data[len(callbacks.ADM_ASSET_PREFIX):]
        asset, ticks = await services.admin.get_asset_history(code)
        await _edit(
            query, admin_messages.asset_detail_text(asset, ticks),
            admin_keyboards.build_asset_detail(asset.code),
        )
        return
    if data.startswith(callbacks.ADM_EVENT_END_PREFIX):
        event_id = _parse_id(data[len(callbacks.ADM_EVENT_END_PREFIX):])
        await services.admin.end_event(admin_id, _require_id(event_id))
        overview = await services.admin.get_economy_overview()
        await _edit(
            query, "⏹ رویداد پایان یافت.\n\n" + admin_messages.econ_text(overview),
            admin_keyboards.build_econ(overview),
        )
        return
    if data.startswith(callbacks.ADM_EVENT_PREFIX):
        event_id = _parse_id(data[len(callbacks.ADM_EVENT_PREFIX):])
        overview = await services.admin.get_economy_overview()
        event = next(
            (e for e in overview.live_events if e.id == event_id), None
        )
        if event is None:
            await _edit(
                query, "این رویداد دیگه فعال نیست.",
                admin_keyboards.build_econ(overview),
            )
            return
        await _edit(
            query, admin_messages.event_detail_text(event),
            admin_keyboards.build_event_detail(event.id),
        )
        return
    if data == callbacks.ADM_CRISIS:
        await _edit(
            query, admin_messages.crisis_confirm_text(),
            admin_keyboards.build_crisis_confirm(),
        )
        return
    if data == callbacks.ADM_CRISIS_OK:
        await services.admin.trigger_crisis(admin_id)
        overview = await services.admin.get_economy_overview()
        await _edit(
            query, "🚨 بحران اقتصادی فعال شد!\n\n" + admin_messages.econ_text(overview),
            admin_keyboards.build_econ(overview),
        )
        return

    # Real estate
    if data == callbacks.ADM_ESTATE:
        await _edit(
            query, admin_messages.ESTATE_TEXT, admin_keyboards.build_estate()
        )
        return
    if data.startswith(callbacks.ADM_HL_PREFIX):
        page = _parse_id(data[len(callbacks.ADM_HL_PREFIX):]) or 0
        houses = await services.admin.list_houses(page)
        await _edit(
            query, admin_messages.houses_list_text(houses),
            admin_keyboards.build_houses_list(houses),
        )
        return
    if data.startswith(callbacks.ADM_HD_PREFIX):
        house_id = _parse_id(data[len(callbacks.ADM_HD_PREFIX):])
        detail = await services.admin.get_house_detail(_require_id(house_id))
        await _edit(
            query, admin_messages.house_detail_text(detail),
            admin_keyboards.build_house_detail(detail),
        )
        return
    if data.startswith(callbacks.ADM_HE_PREFIX):
        house_id = _parse_id(data[len(callbacks.ADM_HE_PREFIX):])
        detail = await services.admin.get_house_detail(_require_id(house_id))
        await _edit(
            query,
            admin_messages.house_detail_text(detail)
            + "\n\n"
            + admin_messages.HOUSE_EDIT_TEXT,
            admin_keyboards.build_house_edit(detail),
        )
        return
    if data.startswith(callbacks.ADM_HT_PREFIX):
        house_id, field = _parse_toggle(data[len(callbacks.ADM_HT_PREFIX):])
        mapping = {"p": "parking", "e": "elevator", "s": "storage"}
        if house_id is None or field not in mapping:
            await query.answer(text="گزینه نامعتبره.", show_alert=True)
            return
        current = await services.admin.get_house_detail(house_id)
        detail = await services.admin.update_house(
            admin_id, house_id, mapping[field],
            not getattr(current.house, mapping[field]),
        )
        await _edit(
            query,
            admin_messages.house_detail_text(detail)
            + "\n\n"
            + admin_messages.HOUSE_EDIT_TEXT,
            admin_keyboards.build_house_edit(detail),
        )
        return
    if data.startswith(callbacks.ADM_HK_PREFIX):
        house_id, index = _parse_toggle(data[len(callbacks.ADM_HK_PREFIX):])
        if house_id is None or index is None or not 0 <= index < len(_KITCHEN_OPTIONS):
            await query.answer(text="گزینه نامعتبره.", show_alert=True)
            return
        detail = await services.admin.update_house(
            admin_id, house_id, "kitchen_type", _KITCHEN_OPTIONS[index]
        )
        await _edit(
            query,
            admin_messages.house_detail_text(detail)
            + "\n\n"
            + admin_messages.HOUSE_EDIT_TEXT,
            admin_keyboards.build_house_edit(detail),
        )
        return
    if data.startswith(callbacks.ADM_HQ_PREFIX):
        house_id, index = _parse_toggle(data[len(callbacks.ADM_HQ_PREFIX):])
        if house_id is None or index is None or not 0 <= index < len(_QUALITY_OPTIONS):
            await query.answer(text="گزینه نامعتبره.", show_alert=True)
            return
        detail = await services.admin.update_house(
            admin_id, house_id, "quality", _QUALITY_OPTIONS[index]
        )
        await _edit(
            query,
            admin_messages.house_detail_text(detail)
            + "\n\n"
            + admin_messages.HOUSE_EDIT_TEXT,
            admin_keyboards.build_house_edit(detail),
        )
        return
    if data.startswith(callbacks.ADM_NL_PREFIX):
        page = _parse_id(data[len(callbacks.ADM_NL_PREFIX):]) or 0
        lands = await services.admin.list_lands(page)
        await _edit(
            query, admin_messages.lands_list_text(lands),
            admin_keyboards.build_lands_list(lands),
        )
        return
    if data.startswith(callbacks.ADM_ND_PREFIX):
        land_id = _parse_id(data[len(callbacks.ADM_ND_PREFIX):])
        detail = await services.admin.get_land_detail(_require_id(land_id))
        await _edit(
            query, admin_messages.land_detail_text(detail),
            admin_keyboards.build_land_detail(detail),
        )
        return
    if data.startswith(callbacks.ADM_NE_PREFIX):
        land_id = _parse_id(data[len(callbacks.ADM_NE_PREFIX):])
        detail = await services.admin.get_land_detail(_require_id(land_id))
        await _edit(
            query,
            admin_messages.land_detail_text(detail)
            + "\n\n"
            + admin_messages.LAND_EDIT_TEXT,
            admin_keyboards.build_land_edit(detail),
        )
        return
    if data.startswith(callbacks.ADM_LICLOSE_PREFIX):
        listing_id = _parse_id(data[len(callbacks.ADM_LICLOSE_PREFIX):])
        await services.admin.close_listing(admin_id, _require_id(listing_id))
        listings = await services.admin.list_active_listings(0)
        await _edit(
            query, "❌ آگهی حذف شد.\n\n" + admin_messages.listings_text(listings),
            admin_keyboards.build_listings(listings),
        )
        return
    if data.startswith(callbacks.ADM_LI_PREFIX):
        page = _parse_id(data[len(callbacks.ADM_LI_PREFIX):]) or 0
        listings = await services.admin.list_active_listings(page)
        await _edit(
            query, admin_messages.listings_text(listings),
            admin_keyboards.build_listings(listings),
        )
        return
    if data.startswith(callbacks.ADM_CTERM_PREFIX):
        contract_id = _parse_id(data[len(callbacks.ADM_CTERM_PREFIX):])
        await services.admin.terminate_contract(admin_id, _require_id(contract_id))
        contracts = await services.admin.list_contracts(0)
        await _edit(
            query, "⏹ قرارداد فسخ شد.\n\n" + admin_messages.contracts_text(contracts),
            admin_keyboards.build_contracts(contracts),
        )
        return
    if data.startswith(callbacks.ADM_CD_PREFIX):
        contract_id = _parse_id(data[len(callbacks.ADM_CD_PREFIX):])
        contracts = await services.admin.list_contracts(0, per_page=200)
        contract = next(
            (c for c in contracts.items if c.contract_id == contract_id), None
        )
        if contract is None:
            await _edit(
                query, "این قرارداد دیگه فعال نیست.",
                admin_keyboards.build_contracts(
                    await services.admin.list_contracts(0)
                ),
            )
            return
        await _edit(
            query, admin_messages.contract_detail_text(contract),
            admin_keyboards.build_contract_detail(contract.contract_id),
        )
        return
    if data.startswith(callbacks.ADM_C_PREFIX):
        page = _parse_id(data[len(callbacks.ADM_C_PREFIX):]) or 0
        contracts = await services.admin.list_contracts(page)
        await _edit(
            query, admin_messages.contracts_text(contracts),
            admin_keyboards.build_contracts(contracts),
        )
        return

    # Jobs
    if data == callbacks.ADM_JOBS:
        entries = await services.admin.list_jobs()
        await _edit(
            query, admin_messages.jobs_text(entries),
            admin_keyboards.build_jobs(entries),
        )
        return
    if data.startswith(callbacks.ADM_JOB_TOGGLE_PREFIX):
        job_id = _parse_id(data[len(callbacks.ADM_JOB_TOGGLE_PREFIX):])
        current = await services.admin.get_job(_require_id(job_id))
        job = await services.admin.set_job_active(
            admin_id, current.id, not current.is_active
        )
        await _edit(
            query, admin_messages.job_detail_text(job),
            admin_keyboards.build_job_detail(job),
        )
        return
    if data.startswith(callbacks.ADM_JOB_PREFIX):
        job_id = _parse_id(data[len(callbacks.ADM_JOB_PREFIX):])
        job = await services.admin.get_job(_require_id(job_id))
        await _edit(
            query, admin_messages.job_detail_text(job),
            admin_keyboards.build_job_detail(job),
        )
        return
    if data.startswith(callbacks.ADM_W_PREFIX):
        page = _parse_id(data[len(callbacks.ADM_W_PREFIX):]) or 0
        workers = await services.admin.list_workers(page)
        await _edit(
            query, admin_messages.workers_text(workers),
            admin_keyboards.build_workers(workers),
        )
        return

    # Trading
    if data == callbacks.ADM_TRADE:
        overview = await services.admin.get_trading_overview()
        await _edit(
            query, admin_messages.trade_text(overview),
            admin_keyboards.build_trade(),
        )
        return
    if data.startswith(callbacks.ADM_TS_PREFIX):
        page = _parse_id(data[len(callbacks.ADM_TS_PREFIX):]) or 0
        sales = await services.admin.list_recent_sales(page)
        await _edit(
            query, admin_messages.sales_text(sales),
            admin_keyboards.build_sales(sales),
        )
        return
    if data == callbacks.ADM_TA:
        activity = await services.admin.get_market_activity()
        await _edit(
            query, admin_messages.activity_text(activity),
            admin_keyboards.build_trade(),
        )
        return

    # Settings
    if data == callbacks.ADM_SETTINGS:
        overview = await services.admin.get_settings_overview()
        await _edit(
            query, admin_messages.settings_text(overview),
            admin_keyboards.build_settings(overview),
        )
        return
    if data.startswith(callbacks.ADM_TG_PREFIX):
        feature = data[len(callbacks.ADM_TG_PREFIX):]
        if feature not in admin_runtime.FEATURES:
            await query.answer(text="قابلیت نامعتبره.", show_alert=True)
            return
        await services.admin.set_feature(
            admin_id, feature, not admin_runtime.feature_enabled(feature)
        )
        overview = await services.admin.get_settings_overview()
        await _edit(
            query, admin_messages.settings_text(overview),
            admin_keyboards.build_settings(overview),
        )
        return

    # Database tools
    if data == callbacks.ADM_DB:
        await _edit(
            query, admin_messages.DB_TEXT, admin_keyboards.build_db()
        )
        return
    if data == callbacks.ADM_DB_STATS:
        stats = await services.admin.get_db_stats()
        await _edit(
            query, admin_messages.db_stats_text(stats),
            admin_keyboards.build_db_back(),
        )
        return
    if data == callbacks.ADM_DB_BACKUP:
        info = await services.admin.backup_database(admin_id)
        await _edit(
            query, admin_messages.backup_done_text(info),
            admin_keyboards.build_db_back(),
        )
        await _send_backup_file(query, context, info.filename)
        return
    if data == callbacks.ADM_DB_BACKUPS:
        backups = await services.admin.list_backups()
        await _edit(
            query, admin_messages.backups_text(backups),
            admin_keyboards.build_backups(backups),
        )
        return
    if data.startswith(callbacks.ADM_DB_RESTORE_OK_PREFIX):
        filename = data[len(callbacks.ADM_DB_RESTORE_OK_PREFIX):]
        await services.admin.restore_database(admin_id, filename)
        await _edit(
            query,
            f"✅ دیتابیس از «{filename}» بازیابی شد.",
            admin_keyboards.build_db(),
        )
        return
    if data.startswith(callbacks.ADM_DB_RESTORE_PREFIX):
        filename = data[len(callbacks.ADM_DB_RESTORE_PREFIX):]
        backups = await services.admin.list_backups()
        info = next((b for b in backups if b.filename == filename), None)
        if info is None:
            await _edit(
                query, "این بکاپ پیدا نشد.",
                admin_keyboards.build_backups(backups),
            )
            return
        await _edit(
            query, admin_messages.restore_confirm_text(info),
            admin_keyboards.build_restore_confirm(info.filename),
        )
        return
    if data == callbacks.ADM_DB_CLEAN:
        await _edit(
            query, admin_messages.CLEAN_TEXT, admin_keyboards.build_clean()
        )
        return

    # Logs
    if data == callbacks.ADM_LOGS:
        await _edit(
            query, admin_messages.LOGS_TEXT, admin_keyboards.build_logs()
        )
        return
    if data.startswith(callbacks.ADM_LOG_PREFIX):
        rest = data[len(callbacks.ADM_LOG_PREFIX):]
        category, _, page_raw = rest.rpartition("_")
        page = _parse_id(page_raw) or 0
        if category == "errors":
            lines = await services.admin.get_error_logs()
            await _edit(
                query, admin_messages.error_logs_text(lines),
                admin_keyboards.build_back_to_admin(),
            )
            return
        prefix = None if category == "admin" else category
        logs = await services.admin.list_audit_logs(page, action_prefix=prefix)
        title = LOG_TITLES.get(category, "📋 لاگ‌ها")
        await _edit(
            query, admin_messages.audit_list_text(logs, title),
            admin_keyboards.build_audit_list(
                f"{callbacks.ADM_LOG_PREFIX}{category}_", logs
            ),
        )
        return

    logger.warning("Unknown admin callback data received: %.100r", data)
    await query.answer(text=message_errors.UNKNOWN_ACTION, show_alert=True)


def _require_id(value: int | None) -> int:
    if value is None:
        raise DomainError("شناسه نامعتبر است.")
    return value


def _parse_toggle(raw: str) -> tuple[int | None, object]:
    """Split ``<id>_<code>`` payloads (facility toggles, option pickers)."""
    head, _, tail = raw.rpartition("_")
    item_id = _parse_id(head)
    code: object = tail
    if tail.isdigit():
        code = int(tail)
    return item_id, code


async def _send_backup_file(
    query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, filename: str
) -> None:
    services = get_services(context)
    path = services.admin.backup_file_path(filename)
    message = query.message
    chat_id = message.chat_id if message is not None else query.from_user.id
    with open(path, "rb") as handle:
        await context.bot.send_document(
            chat_id=chat_id, document=handle, filename=filename,
            caption=f"💾 بکاپ دیتابیس\n{filename}",
        )


# --- Input-flow entry ---------------------------------------------------------------

async def admin_input_entry(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Enter the typed-input conversation (``adm_in_...`` buttons)."""
    query = update.callback_query
    if query is None or query.data is None:
        return ConversationHandler.END
    if not _is_admin(update, context):
        await _deny_query(query)
        return ConversationHandler.END

    payload = query.data[len(callbacks.ADM_IN_PREFIX):]
    parts = payload.split("_")
    code = parts[0] if parts else ""
    target = parts[1] if len(parts) > 1 else None
    extra = parts[2] if len(parts) > 2 else None

    prompt_key: str | None = None
    step: str | None = None

    if code in ("q", "m+", "m-", "x+", "x-", "lvl", "infl", "mkt",
                "ap", "mwm"):
        prompt_key = code
    elif code == "ev":
        prompt_key, step = "ev_name", "name"
    elif code == "ja":
        prompt_key, step = "ja_name", "name"
    elif code in ("js", "jl", "jc", "je", "jd"):
        prompt_key = code
    elif code == "rw":
        prompt_key = code
    elif code == "ha" and target is not None and extra in _HOUSE_FIELDS:
        prompt_key = _HOUSE_FIELDS[extra][1]
    elif code == "la" and target is not None and extra in _LAND_FIELDS:
        prompt_key = _LAND_FIELDS[extra][1]
    elif code == "purge" and target in ("listings", "audit", "ticks"):
        prompt_key = "purge"

    if prompt_key is None or prompt_key not in admin_messages.INPUT_PROMPTS:
        await query.answer(text="گزینه نامعتبره.", show_alert=True)
        return ConversationHandler.END

    # Sanity-check numeric targets up front (codes, asset codes stay raw).
    if code in ("m+", "m-", "x+", "x-", "lvl",
                "js", "jl", "jc", "je", "jd") and _parse_id(target or "") is None:
        await query.answer(text="گزینه نامعتبره.", show_alert=True)
        return ConversationHandler.END
    if code in ("ha", "la") and _parse_id(target or "") is None:
        await query.answer(text="گزینه نامعتبره.", show_alert=True)
        return ConversationHandler.END
    if code == "rw" and target not in _REWARD_LABELS:
        await query.answer(text="گزینه نامعتبره.", show_alert=True)
        return ConversationHandler.END

    context.user_data[PENDING_KEY] = {
        "code": code, "target": target, "extra": extra,
        "step": step, "data": {},
    }
    await query.answer()
    await _edit(
        query, admin_messages.INPUT_PROMPTS[prompt_key],
        admin_keyboards.build_input_cancel(),
    )
    return ADMIN_INPUT


async def admin_input_cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Leave the typed-input conversation (✖️ انصراف)."""
    context.user_data.pop(PENDING_KEY, None)
    query = update.callback_query
    if query is not None:
        if not _is_admin(update, context):
            await _deny_query(query)
            return ConversationHandler.END
        await query.answer()
        await _edit(
            query, admin_messages.INPUT_CANCELLED,
            admin_keyboards.build_admin_menu(),
        )
    return ConversationHandler.END


# --- Input receiver -------------------------------------------------------------------

async def admin_input_received(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Handle one typed admin value (validates, executes, reports back)."""
    message = update.message
    if message is None or update.effective_user is None:
        return ConversationHandler.END
    if not _is_admin(update, context):
        logger.warning(
            "Unauthorized admin-input attempt by user %s",
            update.effective_user.id,
        )
        await message.reply_text(admin_messages.NOT_ADMIN)
        return ConversationHandler.END

    pending = context.user_data.get(PENDING_KEY)
    if not isinstance(pending, dict) or "code" not in pending:
        await message.reply_text(
            "نشست ورودی منقضی شده. از /admin دوباره شروع کن.",
            reply_markup=admin_keyboards.build_admin_menu(),
        )
        return ConversationHandler.END

    text = (message.text or "").strip()
    if not text:
        await message.reply_text(admin_messages.INPUT_INVALID)
        return ADMIN_INPUT

    services = get_services(context)
    admin_id = update.effective_user.id
    try:
        done, reply, markup = await _handle_input(
            services, admin_id, pending, text
        )
    except DomainError as exc:
        logger.info("Admin input failed: %s", exc)
        context.user_data.pop(PENDING_KEY, None)
        await message.reply_text(
            f"❌ {exc}", reply_markup=admin_keyboards.build_back_to_admin()
        )
        return ConversationHandler.END
    except Exception:  # noqa: BLE001 — one bad input must never break the panel
        logger.exception("Admin input error")
        context.user_data.pop(PENDING_KEY, None)
        await message.reply_text(
            message_errors.GENERIC,
            reply_markup=admin_keyboards.build_back_to_admin(),
        )
        return ConversationHandler.END

    if done:
        context.user_data.pop(PENDING_KEY, None)
        await message.reply_text(reply, reply_markup=markup)
        return ConversationHandler.END
    # Multi-step flow: stay in the conversation for the next value.
    context.user_data[PENDING_KEY] = pending
    await message.reply_text(reply, reply_markup=markup)
    return ADMIN_INPUT


async def _handle_input(
    services, admin_id: int, pending: dict, text: str
) -> tuple[bool, str, object]:
    """Run one input step.

    Returns ``(done, reply_text, reply_markup)``; ``done=False`` keeps the
    conversation open for the next step of a multi-step flow.
    """
    code = pending["code"]
    target = pending.get("target")
    extra = pending.get("extra")
    data = pending.setdefault("data", {})

    if code == "q":
        users = await services.admin.search_users(text, limit=10)
        if not users:
            return False, (
                "🔍 کسی پیدا نشد. دوباره امتحان کن:\n\n"
                + admin_messages.INPUT_PROMPTS["q"]
            ), admin_keyboards.build_input_cancel()
        page = admin_dto.Page(
            items=tuple(users), page=0, per_page=max(1, len(users)),
            total=len(users), total_pages=1,
        )
        return True, admin_messages.search_results_text(users), (
            admin_keyboards.build_users_list(page)
        )
    if code in ("m+", "m-", "x+", "x-", "lvl"):
        return await _handle_user_value(services, admin_id, code, int(target), text)
    if code == "infl":
        percent = parse_admin_float(text)
        if percent is None:
            return await _stay("infl")
        effective = await services.admin.set_inflation(admin_id, percent)
        return True, (
            f"✅ تورم روی {_fa(percent)}٪ تنظیم شد.\n"
            f"🎯 ضریب نهایی بازار: ×{_fa(effective, 4)}"
        ), admin_keyboards.build_back_to_admin()
    if code == "mkt":
        value = parse_admin_float(text)
        if value is None:
            return await _stay("mkt")
        effective = await services.admin.set_market_conditions(admin_id, value)
        return True, (
            f"✅ شرایط بازار روی ×{_fa(value)} تنظیم شد.\n"
            f"🎯 ضریب نهایی بازار: ×{_fa(effective, 4)}"
        ), admin_keyboards.build_back_to_admin()
    if code == "ap":
        price = parse_admin_int(text)
        if price is None:
            return await _stay("ap")
        asset = await services.admin.set_asset_price(admin_id, str(target), price)
        return True, (
            f"✅ قیمت {asset.name} شد {money(asset.price)}."
        ), admin_keyboards.build_asset_detail(asset.code)
    if code == "ev":
        return await _handle_event_flow(services, admin_id, pending, data, text)
    if code == "ja":
        return await _handle_job_flow(services, admin_id, pending, data, text)
    if code in ("js", "jl", "jc", "je", "jd"):
        return await _handle_job_edit(services, admin_id, code, int(target), text)
    if code == "rw":
        amount = parse_admin_int(text)
        if amount is None:
            return await _stay("rw")
        await services.admin.set_reward_setting(admin_id, str(target), amount)
        label = _REWARD_LABELS[str(target)]
        return True, (
            f"✅ {label} شد {fa_int(amount)}."
        ), admin_keyboards.build_back_to_admin()
    if code == "mwm":
        minutes = parse_admin_int(text)
        if minutes is None:
            return await _stay("mwm")
        await services.admin.set_min_work_minutes(admin_id, minutes)
        return True, (
            f"✅ حداقل کار برای تسویه شد {fa_int(minutes)} دقیقه."
        ), admin_keyboards.build_back_to_admin()
    if code == "ha":
        return await _handle_house_edit(
            services, admin_id, int(target), str(extra), text
        )
    if code == "la":
        return await _handle_land_edit(
            services, admin_id, int(target), str(extra), text
        )
    if code == "purge":
        return await _handle_purge(services, admin_id, str(target), text)

    raise DomainError("جریان ورودی نامعتبر است.")


async def _stay(prompt_key: str) -> tuple[bool, str, object]:
    return False, (
        admin_messages.INPUT_INVALID + "\n\n"
        + admin_messages.INPUT_PROMPTS[prompt_key]
    ), admin_keyboards.build_input_cancel()


def _fa(value: float, digits: int = 2) -> str:
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return text.translate(str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹/"))


async def _handle_user_value(
    services, admin_id: int, code: str, pid: int, text: str
) -> tuple[bool, str, object]:
    amount = parse_admin_int(text)
    if amount is None:
        return await _stay(code)
    back = admin_keyboards.build_user_back(pid)
    if code == "m+":
        result = await services.admin.add_money(admin_id, pid, amount)
        return True, (
            f"✅ {money(amount)} اضافه شد.\nموجودی جدید: {money(result.balance_after)}"
        ), back
    if code == "m-":
        result = await services.admin.remove_money(admin_id, pid, amount)
        return True, (
            f"✅ {money(amount)} کم شد.\nموجودی جدید: {money(result.balance_after)}"
        ), back
    if code == "x+":
        result = await services.admin.add_xp(admin_id, pid, amount)
        return True, (
            f"✅ {fa_int(amount)} XP اضافه شد.\n"
            f"XP: {fa_int(result.xp_before)} ← {fa_int(result.xp_after)} | "
            f"لول: {fa_int(result.new_level)}"
        ), back
    if code == "x-":
        result = await services.admin.remove_xp(admin_id, pid, amount)
        return True, (
            f"✅ {fa_int(amount)} XP کم شد.\n"
            f"XP: {fa_int(result.xp_before)} ← {fa_int(result.xp_after)} | "
            f"لول: {fa_int(result.new_level)}"
        ), back
    result = await services.admin.set_level(admin_id, pid, amount)
    return True, (
        f"✅ لول شد {fa_int(result.new_level)} (XP: {fa_int(result.xp_after)})"
    ), back


async def _handle_event_flow(
    services, admin_id: int, pending: dict, data: dict, text: str
) -> tuple[bool, str, object]:
    cancel = admin_keyboards.build_input_cancel()
    step = pending.get("step") or "name"
    if step == "name":
        name = " ".join(text.split())[:64]
        if not name:
            return await _stay("ev_name")
        data["name"] = name
        pending["step"] = "mult"
        return False, admin_messages.INPUT_PROMPTS["ev_mult"], cancel
    if step == "mult":
        multiplier = parse_admin_float(text)
        if multiplier is None:
            pending["step"] = "mult"
            return await _stay("ev_mult")
        data["mult"] = multiplier
        pending["step"] = "hours"
        return False, admin_messages.INPUT_PROMPTS["ev_hours"], cancel
    hours = parse_admin_int(text)
    if hours is None:
        pending["step"] = "hours"
        return await _stay("ev_hours")
    event = await services.admin.create_event(
        admin_id, name=data["name"], description="",
        multiplier=data["mult"], duration_hours=hours,
    )
    return True, (
        f"✅ رویداد «{event.name}» ساخته شد!\n"
        f"✖️ ضریب ×{_fa(event.multiplier)} به مدت {fa_int(hours)} ساعت."
    ), admin_keyboards.build_back_to_admin()


async def _handle_job_flow(
    services, admin_id: int, pending: dict, data: dict, text: str
) -> tuple[bool, str, object]:
    cancel = admin_keyboards.build_input_cancel()
    step = pending.get("step") or "name"
    if step == "name":
        name = " ".join(text.split())[:64]
        if len(name) < 2:
            return await _stay("ja_name")
        data["name"] = name
        pending["step"] = "desc"
        return False, admin_messages.INPUT_PROMPTS["ja_desc"], cancel
    if step == "desc":
        desc = " ".join(text.split())[:256]
        if not desc:
            return await _stay("ja_desc")
        data["desc"] = desc
        pending["step"] = "salary"
        return False, admin_messages.INPUT_PROMPTS["ja_salary"], cancel
    if step == "salary":
        salary = parse_admin_int(text)
        if salary is None:
            pending["step"] = "salary"
            return await _stay("ja_salary")
        data["salary"] = salary
        pending["step"] = "level"
        return False, admin_messages.INPUT_PROMPTS["ja_level"], cancel
    if step == "level":
        level = parse_admin_int(text)
        if level is None:
            pending["step"] = "level"
            return await _stay("ja_level")
        data["level"] = level
        pending["step"] = "emp"
        return False, admin_messages.INPUT_PROMPTS["ja_emp"], cancel
    if step == "emp":
        employer = " ".join(text.split())[:64]
        if not employer:
            return await _stay("ja_emp")
        data["emp"] = employer
        pending["step"] = "cool"
        return False, admin_messages.INPUT_PROMPTS["ja_cool"], cancel
    cooldown = parse_admin_int(text)
    if cooldown is None:
        pending["step"] = "cool"
        return await _stay("ja_cool")
    job = await services.admin.create_job(
        admin_id, name=data["name"], description=data["desc"],
        hourly_salary=data["salary"], required_level=data["level"],
        employer=data["emp"], cooldown=cooldown,
    )
    return True, (
        f"✅ شغل «{job.name}» ساخته شد!\n"
        f"💰 {money(job.hourly_salary)}/ساعت | ⭐ لول {fa_int(job.required_level)}"
    ), admin_keyboards.build_back_to_admin()


async def _handle_job_edit(
    services, admin_id: int, code: str, jid: int, text: str
) -> tuple[bool, str, object]:
    field = {"js": "hourly_salary", "jl": "required_level", "jc": "cooldown",
             "je": "employer", "jd": "description"}[code]
    if code in ("js", "jl", "jc"):
        value: object = parse_admin_int(text)
        if value is None:
            return await _stay(code)
    else:
        value = " ".join(text.split())
        if not value:
            return await _stay(code)
    job = await services.admin.update_job(admin_id, jid, field, value)
    return True, (
        "✅ شغل به‌روز شد.\n\n" + admin_messages.job_detail_text(job)
    ), admin_keyboards.build_job_detail(job)


async def _handle_house_edit(
    services, admin_id: int, hid: int, field_code: str, text: str
) -> tuple[bool, str, object]:
    field, prompt_key = _HOUSE_FIELDS[field_code]
    if field_code == "loc":
        city, neighborhood = _split_location(text)
        if city is None or neighborhood is None:
            return await _stay(prompt_key)
        detail = await services.admin.update_house_location(
            admin_id, hid, city, neighborhood
        )
    elif field_code == "ovr":
        per_mille = parse_admin_int(text)
        if per_mille is None:
            return await _stay(prompt_key)
        detail = await services.admin.set_house_override(
            admin_id, hid, None if per_mille == 0 else per_mille
        )
    else:
        value = parse_admin_int(text)
        if value is None:
            return await _stay(prompt_key)
        detail = await services.admin.update_house(admin_id, hid, field, value)
    return True, (
        "✅ خانه به‌روز شد.\n\n" + admin_messages.house_detail_text(detail)
    ), admin_keyboards.build_house_detail(detail)


async def _handle_land_edit(
    services, admin_id: int, lid: int, field_code: str, text: str
) -> tuple[bool, str, object]:
    field, prompt_key = _LAND_FIELDS[field_code]
    if field_code == "loc":
        city, neighborhood = _split_location(text)
        if city is None or neighborhood is None:
            return await _stay(prompt_key)
        detail = await services.admin.update_land_location(
            admin_id, lid, city, neighborhood
        )
    elif field_code == "ovr":
        per_mille = parse_admin_int(text)
        if per_mille is None:
            return await _stay(prompt_key)
        detail = await services.admin.set_land_override(
            admin_id, lid, None if per_mille == 0 else per_mille
        )
    else:
        value = parse_admin_int(text)
        if value is None:
            return await _stay(prompt_key)
        detail = await services.admin.update_land(admin_id, lid, field, value)
    return True, (
        "✅ زمین به‌روز شد.\n\n" + admin_messages.land_detail_text(detail)
    ), admin_keyboards.build_land_detail(detail)


def _split_location(text: str) -> tuple[str | None, str | None]:
    for separator in ("،", ",", "؛", ";"):
        if separator in text:
            city, _, neighborhood = text.partition(separator)
            city, neighborhood = city.strip(), neighborhood.strip()
            if city and neighborhood:
                return city, neighborhood
            return None, None
    return None, None


async def _handle_purge(
    services, admin_id: int, target: str, text: str
) -> tuple[bool, str, object]:
    days = parse_admin_int(text)
    if days is None:
        return await _stay("purge")
    if target == "listings":
        removed = await services.admin.purge_closed_listings(admin_id, days)
        what = "آگهی بسته"
    elif target == "audit":
        removed = await services.admin.purge_audit_logs(admin_id, days)
        what = "لاگ ادمین"
    else:
        removed = await services.admin.purge_price_ticks(admin_id, days)
        what = "نقطه تاریخچه قیمت"
    return True, (
        f"✅ پاک‌سازی انجام شد: {fa_int(removed)} {what}."
    ), admin_keyboards.build_db_back()
