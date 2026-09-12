"""Admin-panel handler tests — navigation, input flows, feature flags.

Telegram objects are simulated; the real service/database stack runs
underneath.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import CallbackQuery, Chat, Message, Update, User
from telegram.ext import ConversationHandler

from app.bot.handlers import admin_panel, housing, job
from app.bot.keyboards import callbacks
from app.bot.keyboards.main_menu import build_main_menu
from app.database.repositories.player_repository import PlayerRepository
from app.game.admin import runtime as admin_runtime

ADMIN_ID = 8154313073


@pytest.fixture(autouse=True)
def _clean_runtime():
    admin_runtime.reset_to_defaults()
    yield
    admin_runtime.reset_to_defaults()


@pytest.fixture
def tg_env(monkeypatch):
    answer, edit, reply = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(CallbackQuery, "answer", answer)
    monkeypatch.setattr(CallbackQuery, "edit_message_text", edit)
    monkeypatch.setattr(Message, "reply_text", reply)
    return SimpleNamespace(answer=answer, edit=edit, reply=reply)


def make_user(tg_id: int = ADMIN_ID) -> User:
    return User(id=tg_id, first_name="Admin", is_bot=False, username="admin")


def make_context(services, user_data: dict | None = None) -> MagicMock:
    context = MagicMock()
    context.application.bot_data = {"services": services, "admin_ids": (ADMIN_ID,)}
    context.user_data = {} if user_data is None else user_data
    return context


async def _tap(services, tg_id: int, data: str, user_data: dict | None = None):
    """Simulate tapping an admin inline button; returns (state, context)."""
    query = CallbackQuery(id="q", from_user=make_user(tg_id), chat_instance="ci", data=data)
    context = make_context(services, user_data)
    state = await admin_panel.admin_callback(
        Update(update_id=1, callback_query=query), context
    )
    return state, context


async def _type(services, text: str, user_data: dict, tg_id: int = ADMIN_ID):
    """Simulate typing a value into a pending admin input."""
    user = make_user(tg_id)
    message = Message(
        message_id=1, date=datetime.now(), chat=Chat(id=user.id, type=Chat.PRIVATE),
        from_user=user, text=text,
    )
    context = make_context(services, user_data)
    state = await admin_panel.admin_input_received(
        Update(update_id=1, message=message), context
    )
    return state, context


def _last_edit(tg_env) -> str:
    return tg_env.edit.await_args.kwargs["text"]


def _last_reply(tg_env) -> str:
    return tg_env.reply.await_args.args[0]


async def _fund(services, player_id: int, amount: int) -> None:
    async with services.players._session_factory() as session:  # noqa: SLF001
        await PlayerRepository(session).add_money(player_id, amount)
        await session.commit()


# --- Menu & dashboard ------------------------------------------------------------------

async def test_menu_and_dashboard_render(services, tg_env):
    state, _ = await _tap(services, ADMIN_ID, callbacks.ADM_MENU)
    assert state == ConversationHandler.END
    assert "پنل مدیریت" in _last_edit(tg_env)

    await _tap(services, ADMIN_ID, callbacks.ADM_DASH)
    assert "داشبورد" in _last_edit(tg_env)
    assert "کاربران" in _last_edit(tg_env)


async def test_unknown_admin_callback_gets_alert(services, tg_env):
    await _tap(services, ADMIN_ID, "adm_nonsense_xyz")
    assert "نمی‌شناسم" in tg_env.answer.await_args.kwargs["text"]


# --- Users -----------------------------------------------------------------------------

async def test_user_list_detail_and_ban_flow(services, register, tg_env):
    target = await register(tg_id=6401)

    await _tap(services, ADMIN_ID, f"{callbacks.ADM_UL_PREFIX}0")
    assert "کاربران" in _last_edit(tg_env)

    await _tap(services, ADMIN_ID, f"{callbacks.ADM_U_PREFIX}{target.player_id}")
    assert "پروفایل" in _last_edit(tg_env)

    await _tap(services, ADMIN_ID, f"{callbacks.ADM_UTX_PREFIX}{target.player_id}")
    assert "تراکنش" in _last_edit(tg_env)

    await _tap(services, ADMIN_ID, f"{callbacks.ADM_UPROP_PREFIX}{target.player_id}")
    assert "املاک" in _last_edit(tg_env)

    await _tap(services, ADMIN_ID, f"{callbacks.ADM_BAN_PREFIX}{target.player_id}")
    assert "مسدودسازی" in _last_edit(tg_env)

    await _tap(services, ADMIN_ID, f"{callbacks.ADM_BANOK_PREFIX}{target.player_id}")
    assert "مسدود شد" in _last_edit(tg_env)
    assert await services.admin.is_user_banned(6401) is True

    await _tap(services, ADMIN_ID, f"{callbacks.ADM_UNBAN_PREFIX}{target.player_id}")
    assert "برداشته شد" in _last_edit(tg_env)
    assert await services.admin.is_user_banned(6401) is False


async def test_user_detail_unknown_is_safe(services, tg_env):
    await _tap(services, ADMIN_ID, f"{callbacks.ADM_U_PREFIX}999999")
    assert "❌" in _last_edit(tg_env)


# --- Input entry / cancel ------------------------------------------------------------------

@pytest.mark.parametrize(
    ("data", "prompt_part"),
    [
        ("adm_in_q", "جست‌وجو"),
        ("adm_in_m+_1", "افزودن پول"),
        ("adm_in_m-_1", "کم‌کردن پول"),
        ("adm_in_x+_1", "افزودن XP"),
        ("adm_in_lvl_1", "لول جدید"),
        ("adm_in_infl", "تورم"),
        ("adm_in_mkt", "شرایط بازار"),
        ("adm_in_ap_USD", "قیمت جدید"),
        ("adm_in_ev", "قدم ۱ از ۳"),
        ("adm_in_ja", "قدم ۱ از ۶"),
        ("adm_in_js_1", "حقوق ساعتی"),
        ("adm_in_rw_pxd", "مقدار جدید"),
        ("adm_in_mwm", "حداقل دقایق"),
        ("adm_in_ha_1_area", "متراژ"),
        ("adm_in_la_1_loc", "لوکیشن"),
        ("adm_in_purge_audit", "تعداد روز"),
    ],
)
async def test_input_entry_prompts(services, tg_env, data, prompt_part):
    state, context = await _tap(services, ADMIN_ID, data)
    assert state == admin_panel.ADMIN_INPUT
    assert prompt_part in _last_edit(tg_env)
    assert admin_panel.PENDING_KEY in context.user_data


async def test_input_entry_rejects_garbage(services, tg_env):
    for data in ("adm_in_zzz", "adm_in_m+_abc", "adm_in_rw_zzz", "adm_in_ha_1_nope"):
        state, _ = await _tap(services, ADMIN_ID, data)
        assert state == ConversationHandler.END


async def test_input_cancel_returns_to_menu(services, tg_env):
    _, context = await _tap(services, ADMIN_ID, "adm_in_mkt")
    assert admin_panel.PENDING_KEY in context.user_data

    state, context2 = await _tap(services, ADMIN_ID, "adm_cancel", context.user_data)
    assert state == ConversationHandler.END
    assert admin_panel.PENDING_KEY not in context2.user_data
    assert "پنل" in _last_edit(tg_env)


async def test_tapping_buttons_cancels_pending_input(services, tg_env):
    _, context = await _tap(services, ADMIN_ID, "adm_in_mkt")
    assert admin_panel.PENDING_KEY in context.user_data
    await _tap(services, ADMIN_ID, callbacks.ADM_DASH, context.user_data)
    assert admin_panel.PENDING_KEY not in context.user_data


# --- Typed inputs --------------------------------------------------------------------------

async def test_add_money_flow(services, register, tg_env):
    target = await register(tg_id=6411)
    _, context = await _tap(services, ADMIN_ID, f"adm_in_m+_{target.player_id}")

    state, _ = await _type(services, "۲۵۰۰۰۰۰", context.user_data)
    assert state == ConversationHandler.END
    assert "اضافه شد" in _last_reply(tg_env)
    profile = await services.players.get_profile(6411)
    assert profile is not None and profile.money == 2_500_000


async def test_invalid_money_stays_in_conversation(services, register, tg_env):
    target = await register(tg_id=6412)
    _, context = await _tap(services, ADMIN_ID, f"adm_in_m+_{target.player_id}")

    state, context = await _type(services, "not-a-number", context.user_data)
    assert state == admin_panel.ADMIN_INPUT
    assert "معتبر نیست" in _last_reply(tg_env)

    # Still pending → a good value completes it.
    state, _ = await _type(services, "1000", context.user_data)
    assert state == ConversationHandler.END


async def test_remove_money_overdraw_reports_error(services, register, tg_env):
    target = await register(tg_id=6413)
    _, context = await _tap(services, ADMIN_ID, f"adm_in_m-_{target.player_id}")
    state, _ = await _type(services, "999999999", context.user_data)
    assert state == ConversationHandler.END
    assert "❌" in _last_reply(tg_env)


async def test_xp_and_level_flows(services, register, tg_env):
    target = await register(tg_id=6414)
    _, context = await _tap(services, ADMIN_ID, f"adm_in_x+_{target.player_id}")
    await _type(services, "120", context.user_data)
    assert "XP" in _last_reply(tg_env)

    _, context = await _tap(services, ADMIN_ID, f"adm_in_lvl_{target.player_id}")
    await _type(services, "4", context.user_data)
    assert "لول" in _last_reply(tg_env)
    detail = await services.admin.get_user_detail(target.player_id)
    assert detail.summary.level == 4


async def test_search_flow(services, register, tg_env):
    await register(tg_id=6415, username="nima", display_name="نیما")
    _, context = await _tap(services, ADMIN_ID, "adm_in_q")
    state, _ = await _type(services, "نیما", context.user_data)
    assert state == ConversationHandler.END
    assert "نیما" in _last_reply(tg_env)

    _, context = await _tap(services, ADMIN_ID, "adm_in_q")
    state, _ = await _type(services, "ghost-xyz", context.user_data)
    assert state == admin_panel.ADMIN_INPUT  # stays for another try
    assert "پیدا نشد" in _last_reply(tg_env)


async def test_inflation_and_market_inputs(services, tg_env):
    await services.admin.ensure_economy_seeded()

    _, context = await _tap(services, ADMIN_ID, "adm_in_infl")
    await _type(services, "۲۵", context.user_data)
    assert "تورم" in _last_reply(tg_env)
    assert admin_runtime.inflation_rate() == pytest.approx(25.0)

    _, context = await _tap(services, ADMIN_ID, "adm_in_mkt")
    await _type(services, "1.5", context.user_data)
    assert "شرایط بازار" in _last_reply(tg_env)
    assert admin_runtime.market_conditions_base() == pytest.approx(1.5)


async def test_event_creation_flow(services, tg_env):
    await services.admin.ensure_economy_seeded()
    _, context = await _tap(services, ADMIN_ID, "adm_in_ev")

    state, context = await _type(services, "رونق بهاری", context.user_data)
    assert state == admin_panel.ADMIN_INPUT
    state, context = await _type(services, "1.2", context.user_data)
    assert state == admin_panel.ADMIN_INPUT
    state, _ = await _type(services, "۷۲", context.user_data)
    assert state == ConversationHandler.END
    assert "ساخته شد" in _last_reply(tg_env)
    assert admin_runtime.effective_market_factor() == pytest.approx(1.2)


async def test_job_creation_flow(services, tg_env):
    _, context = await _tap(services, ADMIN_ID, "adm_in_ja")
    # «نقشه‌کش» is deliberately not part of the «خر حمالی» catalog, so this
    # proves the admin really can add a job of their own next to the seeded ones.
    for text in ["نقشه‌کش", "نقشه‌کشی ساختمان", "150000", "1", "اسنپ‌فود", "0"]:
        state, context = await _type(services, text, context.user_data)
    assert state == ConversationHandler.END
    assert "ساخته شد" in _last_reply(tg_env)
    jobs = await services.admin.list_jobs()
    assert any(j.name == "نقشه‌کش" for j in jobs)


# --- Economy screens -------------------------------------------------------------------------

async def test_economy_asset_and_event_screens(services, tg_env):
    await services.admin.ensure_economy_seeded()

    await _tap(services, ADMIN_ID, callbacks.ADM_ECON)
    assert "اقتصاد" in _last_edit(tg_env)

    await _tap(services, ADMIN_ID, f"{callbacks.ADM_ASSET_PREFIX}USD")
    assert "دلار" in _last_edit(tg_env)

    _, context = await _tap(services, ADMIN_ID, "adm_in_ap_USD")
    await _type(services, "2000000", context.user_data)
    assert "دلار" in _last_reply(tg_env)

    event = await services.admin.create_event(
        ADMIN_ID, name="تست", description="", multiplier=1.1, duration_hours=5
    )
    await _tap(services, ADMIN_ID, f"{callbacks.ADM_EVENT_PREFIX}{event.id}")
    assert "تست" in _last_edit(tg_env)
    await _tap(services, ADMIN_ID, f"{callbacks.ADM_EVENT_END_PREFIX}{event.id}")
    assert "پایان یافت" in _last_edit(tg_env)


async def test_crisis_flow(services, tg_env):
    await services.admin.ensure_economy_seeded()
    await _tap(services, ADMIN_ID, callbacks.ADM_CRISIS)
    assert "بحران" in _last_edit(tg_env)
    await _tap(services, ADMIN_ID, callbacks.ADM_CRISIS_OK)
    assert "بحران" in _last_edit(tg_env)
    assert admin_runtime.effective_market_factor() == pytest.approx(1.35)


# --- Real estate screens -----------------------------------------------------------------------

async def test_house_navigation_and_edits(services, tg_env):
    await services.housing.ensure_initial_houses()

    await _tap(services, ADMIN_ID, callbacks.ADM_ESTATE)
    assert "املاک" in _last_edit(tg_env)
    await _tap(services, ADMIN_ID, f"{callbacks.ADM_HL_PREFIX}0")
    assert "خانه‌ها" in _last_edit(tg_env)
    await _tap(services, ADMIN_ID, f"{callbacks.ADM_HD_PREFIX}1")
    assert "خانه #1" in _last_edit(tg_env)
    await _tap(services, ADMIN_ID, f"{callbacks.ADM_HE_PREFIX}1")
    assert "ویرایش" in _last_edit(tg_env)

    before = (await services.admin.get_house_detail(1)).house.parking
    await _tap(services, ADMIN_ID, f"{callbacks.ADM_HT_PREFIX}1_p")
    after = (await services.admin.get_house_detail(1)).house.parking
    assert after is (not before)

    await _tap(services, ADMIN_ID, f"{callbacks.ADM_HK_PREFIX}1_0")
    assert (await services.admin.get_house_detail(1)).house.kitchen_type == "مدرن"
    await _tap(services, ADMIN_ID, f"{callbacks.ADM_HQ_PREFIX}1_0")
    assert (await services.admin.get_house_detail(1)).house.quality == "عالی"

    _, context = await _tap(services, ADMIN_ID, "adm_in_ha_1_area")
    await _type(services, "175", context.user_data)
    assert "به‌روز شد" in _last_reply(tg_env)

    _, context = await _tap(services, ADMIN_ID, "adm_in_ha_1_ovr")
    await _type(services, "0", context.user_data)
    assert "به‌روز شد" in _last_reply(tg_env)


async def test_land_navigation_and_edits(services, tg_env):
    await services.realestate.ensure_initial_lands()

    await _tap(services, ADMIN_ID, f"{callbacks.ADM_NL_PREFIX}0")
    assert "زمین‌ها" in _last_edit(tg_env)
    await _tap(services, ADMIN_ID, f"{callbacks.ADM_ND_PREFIX}1")
    assert "زمین #1" in _last_edit(tg_env)
    await _tap(services, ADMIN_ID, f"{callbacks.ADM_NE_PREFIX}1")
    assert "ویرایش" in _last_edit(tg_env)

    _, context = await _tap(services, ADMIN_ID, "adm_in_la_1_area")
    await _type(services, "600", context.user_data)
    assert "به‌روز شد" in _last_reply(tg_env)
    assert (await services.admin.get_land_detail(1)).land.area_sqm == 600

    _, context = await _tap(services, ADMIN_ID, "adm_in_la_1_loc")
    await _type(services, "تهران، ونک", context.user_data)
    assert "به‌روز شد" in _last_reply(tg_env)
    assert (await services.admin.get_land_detail(1)).land.location_quality == "لوکس"


async def test_listing_close_flow(services, register, tg_env):
    await services.housing.ensure_initial_houses()
    owner = await register(tg_id=6421)
    entries = await services.housing.get_available_houses_for_sale()
    cheapest = min(entries, key=lambda e: e.price)
    await _fund(services, owner.player_id, cheapest.price)
    await services.housing.buy_from_market(owner.player_id, cheapest.house.id)
    async with services.players._session_factory() as session:  # noqa: SLF001
        from app.database.repositories.house_repository import HouseRepository

        house = await HouseRepository(session).get_by_id(cheapest.house.id)
        assert house is not None
        value = services.housing.estimate_value(house)
    await services.housing.list_house_for_sale(owner.player_id, cheapest.house.id, value)

    await _tap(services, ADMIN_ID, f"{callbacks.ADM_LI_PREFIX}0")
    assert "آگهی" in _last_edit(tg_env)
    listing = (await services.admin.list_active_listings(0)).items[0]
    await _tap(services, ADMIN_ID, f"{callbacks.ADM_LICLOSE_PREFIX}{listing.listing_id}")
    assert "حذف شد" in _last_edit(tg_env)
    assert (await services.admin.list_active_listings(0)).total == 0


async def test_contracts_screen_empty(services, tg_env):
    await _tap(services, ADMIN_ID, f"{callbacks.ADM_C_PREFIX}0")
    assert "قرارداد" in _last_edit(tg_env)


# --- Jobs screens ------------------------------------------------------------------------------

async def test_job_screens_and_toggle(services, register, tg_env):
    await _tap(services, ADMIN_ID, callbacks.ADM_JOBS)
    assert "شغل" in _last_edit(tg_env)

    jobs = await services.admin.list_jobs()
    jid = jobs[0].id
    await _tap(services, ADMIN_ID, f"{callbacks.ADM_JOB_PREFIX}{jid}")
    assert jobs[0].name in _last_edit(tg_env)

    await _tap(services, ADMIN_ID, f"{callbacks.ADM_JOB_TOGGLE_PREFIX}{jid}")
    assert (await services.admin.get_job(jid)).is_active is False
    await _tap(services, ADMIN_ID, f"{callbacks.ADM_JOB_TOGGLE_PREFIX}{jid}")
    assert (await services.admin.get_job(jid)).is_active is True

    _, context = await _tap(services, ADMIN_ID, f"adm_in_js_{jid}")
    await _type(services, "500000", context.user_data)
    assert "به‌روز شد" in _last_reply(tg_env)

    worker = await register(tg_id=6431)
    await services.jobs.apply_job(worker.player_id, jid)
    await _tap(services, ADMIN_ID, f"{callbacks.ADM_W_PREFIX}0")
    assert "کارگر" in _last_edit(tg_env)


# --- Trading / settings / db / logs ---------------------------------------------------------------

async def test_trading_screens(services, tg_env):
    await _tap(services, ADMIN_ID, callbacks.ADM_TRADE)
    assert "معاملات" in _last_edit(tg_env)
    await _tap(services, ADMIN_ID, f"{callbacks.ADM_TS_PREFIX}0")
    assert "فروش" in _last_edit(tg_env)
    await _tap(services, ADMIN_ID, callbacks.ADM_TA)
    assert "بازار" in _last_edit(tg_env)


async def test_settings_and_feature_toggle(services, tg_env):
    await services.admin.ensure_economy_seeded()
    await _tap(services, ADMIN_ID, callbacks.ADM_SETTINGS)
    assert "تنظیمات" in _last_edit(tg_env)

    await _tap(services, ADMIN_ID, f"{callbacks.ADM_TG_PREFIX}jobs")
    assert admin_runtime.feature_enabled("jobs") is False
    assert "خاموش" in _last_edit(tg_env)
    await _tap(services, ADMIN_ID, f"{callbacks.ADM_TG_PREFIX}jobs")
    assert admin_runtime.feature_enabled("jobs") is True

    _, context = await _tap(services, ADMIN_ID, "adm_in_rw_pxd")
    await _type(services, "5000000", context.user_data)
    assert "مقسوم" in _last_reply(tg_env)

    _, context = await _tap(services, ADMIN_ID, "adm_in_mwm")
    await _type(services, "10", context.user_data)
    assert "تسویه" in _last_reply(tg_env)


async def test_db_screens_backup_and_restore(services, db, tg_env, tmp_path, monkeypatch):
    import app.services.admin_service as admin_module

    monkeypatch.setattr(admin_module, "PROJECT_ROOT", tmp_path)
    services.attach_database(db)

    await _tap(services, ADMIN_ID, callbacks.ADM_DB)
    assert "دیتابیس" in _last_edit(tg_env)
    await _tap(services, ADMIN_ID, callbacks.ADM_DB_STATS)
    assert "آمار" in _last_edit(tg_env)

    send_mock = AsyncMock()
    query = CallbackQuery(
        id="q", from_user=make_user(), chat_instance="ci",
        data=callbacks.ADM_DB_BACKUP,
    )
    context = make_context(services)
    context.bot.send_document = send_mock
    state = await admin_panel.admin_callback(
        Update(update_id=1, callback_query=query), context
    )
    assert state == ConversationHandler.END
    assert "بکاپ" in _last_edit(tg_env)
    send_mock.assert_awaited_once()

    backups = await services.admin.list_backups()
    assert len(backups) == 1
    await _tap(services, ADMIN_ID, callbacks.ADM_DB_BACKUPS)
    assert backups[0].filename in _last_edit(tg_env)

    await _tap(
        services, ADMIN_ID,
        f"{callbacks.ADM_DB_RESTORE_PREFIX}{backups[0].filename}",
    )
    assert "بازیابی" in _last_edit(tg_env)
    await _tap(
        services, ADMIN_ID,
        f"{callbacks.ADM_DB_RESTORE_OK_PREFIX}{backups[0].filename}",
    )
    assert "بازیابی شد" in _last_edit(tg_env)
    # The database still answers after the restore.
    assert (await services.admin.list_users(0)).total >= 0


async def test_db_clean_screen_and_purge_flow(services, tg_env):
    await _tap(services, ADMIN_ID, callbacks.ADM_DB_CLEAN)
    assert "پاک‌سازی" in _last_edit(tg_env)

    _, context = await _tap(services, ADMIN_ID, "adm_in_purge_listings")
    state, _ = await _type(services, "30", context.user_data)
    assert state == ConversationHandler.END
    assert "پاک‌سازی" in _last_reply(tg_env)


async def test_log_screens(services, register, tg_env):
    target = await register(tg_id=6441)
    await services.admin.add_money(ADMIN_ID, target.player_id, 100)

    await _tap(services, ADMIN_ID, callbacks.ADM_LOGS)
    assert "لاگ" in _last_edit(tg_env)

    await _tap(services, ADMIN_ID, f"{callbacks.ADM_LOG_PREFIX}admin_0")
    assert "user_add_money" in _last_edit(tg_env)
    await _tap(services, ADMIN_ID, f"{callbacks.ADM_LOG_PREFIX}user__0")
    assert "اقدامات کاربران" in _last_edit(tg_env)
    await _tap(services, ADMIN_ID, f"{callbacks.ADM_LOG_PREFIX}errors_0")
    assert "خطا" in _last_edit(tg_env)


# --- Feature flags ---------------------------------------------------------------------------------

async def test_disabled_features_hide_and_deny(services, register, tg_env):
    await services.admin.ensure_economy_seeded()
    await services.admin.set_feature(ADMIN_ID, "jobs", False)
    await services.admin.set_feature(ADMIN_ID, "housing", False)

    data = {
        b.callback_data
        for row in build_main_menu().inline_keyboard
        for b in row
    }
    assert callbacks.JOBS_MENU not in data
    assert callbacks.HOUSING_MENU not in data

    # Job text trigger is denied without touching the service layer.
    user = make_user(6451)
    message = Message(
        message_id=1, date=datetime.now(), chat=Chat(id=user.id, type=Chat.PRIVATE),
        from_user=user, text="مشاغل",
    )
    await job.jobs_text_handler(
        Update(update_id=1, message=message), make_context(services)
    )
    assert "غیرفعال" in _last_reply(tg_env)

    # Housing callback trigger is denied with an alert.
    query = CallbackQuery(
        id="q", from_user=user, chat_instance="ci", data=callbacks.HOUSING_MENU
    )
    await housing.show_housing_menu(
        Update(update_id=1, callback_query=query), make_context(services)
    )
    assert "غیرفعال" in tg_env.answer.await_args.kwargs["text"]


async def test_registration_counts_toward_handler_wiring():
    """The panel routes (پنل trigger, conversation, router) are all registered."""
    from telegram.ext import (
        ApplicationBuilder,
        CallbackQueryHandler,
        CommandHandler,
        MessageHandler,
    )

    application = ApplicationBuilder().token("123456:ABC-test").build()
    try:
        from app.bot.handlers import register_handlers

        register_handlers(application)
        handlers = application.handlers[0]
        assert any(
            isinstance(h, MessageHandler)
            and h.callback is admin_panel.admin_command
            for h in handlers
        )
        assert not any(
            isinstance(h, CommandHandler) and "admin" in h.commands
            for h in handlers
        )
        assert any(
            type(h).__name__ == "ConversationHandler"
            and h.name == "admin_input"
            for h in handlers
        )
        assert any(
            isinstance(h, CallbackQueryHandler)
            and getattr(h, "pattern", None) is not None
            and "adm_" in str(getattr(h, "pattern", ""))
            for h in handlers
        )
    finally:
        # No network was touched — building never connects.
        pass
