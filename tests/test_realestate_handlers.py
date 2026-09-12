"""Land / Construction / Renovation handler tests — button flows simulated.

Follows the established pattern: PTB objects simulated, the full real
service/repository/database stack underneath.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import CallbackQuery, InlineKeyboardMarkup, Update, User
from telegram.error import BadRequest

from app.bot.handlers import realestate
from app.bot.keyboards import callbacks
from app.database.models.construction_project import ConstructionProject
from app.game.housing.construction_year import current_iranian_year
from app.game.realestate import construction as construction_domain


def make_user(tg_id: int, first_name: str = "علی", username: str | None = "ali") -> User:
    return User(id=tg_id, first_name=first_name, is_bot=False, username=username)


def make_query(tg_id: int, data: str) -> CallbackQuery:
    return CallbackQuery(
        id=f"q-{tg_id}-{abs(hash(data)) % 10**8}",
        from_user=make_user(tg_id),
        chat_instance="ci",
        data=data,
    )


def make_update(query: CallbackQuery) -> Update:
    return Update(update_id=1, callback_query=query)


def make_context(services) -> MagicMock:
    context = MagicMock()
    context.application.bot_data = {"services": services}
    return context


def flat_callbacks(markup: InlineKeyboardMarkup) -> set[str]:
    return {
        b.callback_data
        for row in markup.inline_keyboard
        for b in row
        if b.callback_data is not None
    }


@pytest.fixture
async def tg_env(services, monkeypatch):
    await services.housing.ensure_initial_houses()
    lands = await services.realestate.ensure_initial_lands()
    answer_mock, edit_mock = AsyncMock(), AsyncMock()
    monkeypatch.setattr(CallbackQuery, "answer", answer_mock)
    monkeypatch.setattr(CallbackQuery, "edit_message_text", edit_mock)
    return services, lands, answer_mock, edit_mock


async def _register(services, tg_id: int, name: str = "علی") -> int:
    result = await services.players.register_or_get(
        telegram_user_id=tg_id, username=name, display_name=name
    )
    return result.player_id


async def _give_money(services, player_id: int, amount: int) -> None:
    from app.database.repositories.player_repository import PlayerRepository

    async with services.players._session_factory() as session:
        await PlayerRepository(session).add_money(player_id, amount)
        await session.commit()


# --- Land market screens ------------------------------------------------------------


async def test_lands_market_screen(tg_env):
    services, lands, _, edit_mock = tg_env
    await _register(services, 4001)

    query = make_query(4001, callbacks.RE_LANDS_MARKET)
    await realestate.show_lands_market(make_update(query), make_context(services))

    text = edit_mock.await_args.kwargs["text"]
    assert "زمین‌های موجود" in text
    data = flat_callbacks(edit_mock.await_args.kwargs["reply_markup"])
    assert f"{callbacks.RE_LAND_INFO_PREFIX}{lands[0].id}" in data
    assert f"{callbacks.RE_LAND_BUY_PREFIX}{lands[0].id}" in data


async def test_land_info_screen(tg_env):
    services, lands, _, edit_mock = tg_env
    await _register(services, 4002)

    query = make_query(4002, f"{callbacks.RE_LAND_INFO_PREFIX}{lands[0].id}")
    await realestate.show_land_info(make_update(query), make_context(services))

    text = edit_mock.await_args.kwargs["text"]
    for expected in ("شهر", "محله", "مساحت", "کیفیت موقعیت", "ارزش لحظه‌ای"):
        assert expected in text


async def test_full_land_purchase_flow(tg_env):
    services, lands, _, edit_mock = tg_env
    player_id = await _register(services, 4003)
    await _give_money(services, player_id, 100_000_000_000)

    # Confirmation screen
    query = make_query(4003, f"{callbacks.RE_LAND_BUY_PREFIX}{lands[0].id}")
    await realestate.show_land_buy_confirmation(make_update(query), make_context(services))
    assert "تأیید خرید زمین" in edit_mock.await_args.kwargs["text"]

    # Execute the purchase
    query = make_query(4003, f"{callbacks.RE_LAND_BUY_OK_PREFIX}{lands[0].id}")
    await realestate.confirm_land_buy(make_update(query), make_context(services))
    text = edit_mock.await_args_list[-1].kwargs["text"]
    assert "صاحب زمین شدی" in text

    info = await services.realestate.get_land_info(lands[0].id)
    assert info.land.owner_player_id == player_id
    profile = await services.players.get_profile(4003)
    assert profile.money == 100_000_000_000 - info.market_value


async def test_land_purchase_without_money_fails_friendly(tg_env):
    services, lands, _, edit_mock = tg_env
    await _register(services, 4004)  # zero balance

    query = make_query(4004, f"{callbacks.RE_LAND_BUY_OK_PREFIX}{lands[0].id}")
    await realestate.confirm_land_buy(make_update(query), make_context(services))

    text = edit_mock.await_args.kwargs["text"]
    assert "پول کافی" in text


async def test_my_lands_screen_shows_build_button(tg_env):
    services, lands, _, edit_mock = tg_env
    player_id = await _register(services, 4005)
    await _give_money(services, player_id, 100_000_000_000)
    await services.realestate.buy_land(player_id, lands[1].id)

    query = make_query(4005, callbacks.RE_LANDS_MY)
    await realestate.show_my_lands(make_update(query), make_context(services))

    text = edit_mock.await_args.kwargs["text"]
    assert "زمین‌های تو" in text
    data = flat_callbacks(edit_mock.await_args.kwargs["reply_markup"])
    assert f"{callbacks.RE_BUILD_LAND_PREFIX}{lands[1].id}" in data


# --- Construction wizard -----------------------------------------------------------------


async def test_full_construction_wizard_flow(tg_env):
    services, lands, _, edit_mock = tg_env
    player_id = await _register(services, 4006)
    await _give_money(services, player_id, 100_000_000_000)
    await services.realestate.buy_land(player_id, lands[2].id)
    land_area = lands[2].area_sqm

    # Step 1: choose building type
    query = make_query(4006, f"{callbacks.RE_BUILD_LAND_PREFIX}{lands[2].id}")
    await realestate.show_build_type_picker(make_update(query), make_context(services))
    data = flat_callbacks(edit_mock.await_args.kwargs["reply_markup"])
    spec_cb = f"{callbacks.RE_BUILD_SPEC_PREFIX}{lands[2].id}_a"
    assert spec_cb in data

    # Step 2: choose floors
    query = make_query(4006, spec_cb)
    await realestate.show_build_step(make_update(query), make_context(services))
    data = flat_callbacks(edit_mock.await_args.kwargs["reply_markup"])
    floors_cb = f"{callbacks.RE_BUILD_SPEC_PREFIX}{lands[2].id}_a_3"
    assert floors_cb in data

    # Step 3: choose size
    query = make_query(4006, floors_cb)
    await realestate.show_build_step(make_update(query), make_context(services))
    data = flat_callbacks(edit_mock.await_args.kwargs["reply_markup"])
    presets = construction_domain.size_presets(land_area, 3)
    assert len(data) >= len(presets)
    size = presets[0]
    size_cb = f"{callbacks.RE_BUILD_SPEC_PREFIX}{lands[2].id}_a_3_{size}"
    assert size_cb in data

    # Step 4: choose bedrooms
    query = make_query(4006, size_cb)
    await realestate.show_build_step(make_update(query), make_context(services))
    data = flat_callbacks(edit_mock.await_args.kwargs["reply_markup"])
    rooms_cb = f"{callbacks.RE_BUILD_SPEC_PREFIX}{lands[2].id}_a_3_{size}_2"
    assert rooms_cb in data

    # Step 5: choose quality
    query = make_query(4006, rooms_cb)
    await realestate.show_build_step(make_update(query), make_context(services))
    data = flat_callbacks(edit_mock.await_args.kwargs["reply_markup"])
    quality_cb = f"{callbacks.RE_BUILD_SPEC_PREFIX}{lands[2].id}_a_3_{size}_2_g"
    assert quality_cb in data

    # Step 6: choose facilities
    query = make_query(4006, quality_cb)
    await realestate.show_build_step(make_update(query), make_context(services))
    data = flat_callbacks(edit_mock.await_args.kwargs["reply_markup"])
    confirm_cb = (
        f"{callbacks.RE_BUILD_CONFIRM_PREFIX}{lands[2].id}_a_3_{size}_2_g_P1E1S1"
    )
    assert confirm_cb in data

    # Confirmation screen shows cost and duration
    query = make_query(4006, confirm_cb)
    await realestate.show_construction_confirmation(
        make_update(query), make_context(services)
    )
    text = edit_mock.await_args.kwargs["text"]
    assert "شناسنامه ساخت" in text
    assert "هزینه ساخت" in text
    assert "مدت ساخت" in text

    # Execute: the project really starts and money really moved
    profile_before = await services.players.get_profile(4006)
    query = make_query(
        4006, f"{callbacks.RE_BUILD_EXEC_PREFIX}{lands[2].id}_a_3_{size}_2_g_P1E1S1"
    )
    await realestate.confirm_construction(make_update(query), make_context(services))
    text = edit_mock.await_args_list[-1].kwargs["text"]
    assert "ساخت‌وساز شروع شد" in text

    status = await services.realestate.get_projects_status(player_id)
    assert len(status.constructions) == 1
    project = status.constructions[0]
    assert project.status == "in_progress"
    assert project.area_sqm == size
    assert project.floors == 3

    profile_after = await services.players.get_profile(4006)
    assert profile_after.money == profile_before.money - project.cost_total


async def test_villa_flow_skips_floors_step(tg_env):
    services, lands, _, edit_mock = tg_env
    player_id = await _register(services, 4007)
    await _give_money(services, player_id, 100_000_000_000)
    await services.realestate.buy_land(player_id, lands[3].id)

    query = make_query(4007, f"{callbacks.RE_BUILD_SPEC_PREFIX}{lands[3].id}_v")
    await realestate.show_build_step(make_update(query), make_context(services))

    text = edit_mock.await_args.kwargs["text"]
    assert "متراژ" in text  # straight to the size step
    data = flat_callbacks(edit_mock.await_args.kwargs["reply_markup"])
    size = construction_domain.size_presets(lands[3].area_sqm, 1)[0]
    assert f"{callbacks.RE_BUILD_SPEC_PREFIX}{lands[3].id}_v_1_{size}" in data


async def test_construction_cancel_flow(tg_env):
    services, lands, _, edit_mock = tg_env
    player_id = await _register(services, 4008)
    await _give_money(services, player_id, 100_000_000_000)
    await services.realestate.buy_land(player_id, lands[4].id)
    spec = construction_domain.BuildingSpec(
        land_id=lands[4].id,
        building_type="v",
        floors=1,
        area_sqm=construction_domain.size_presets(lands[4].area_sqm, 1)[0],
        bedrooms=2,
        quality_token="m",
        parking=False,
        elevator=False,
        storage=False,
    )
    started = await services.realestate.start_construction(player_id, lands[4].id, spec)

    balance_before = await services.money.get_balance(player_id)
    query = make_query(4008, f"{callbacks.RE_BUILD_CANCEL_PREFIX}{started.project.id}")
    await realestate.cancel_construction(make_update(query), make_context(services))

    text = edit_mock.await_args.kwargs["text"]
    assert "لغو شد" in text
    expected_refund = started.cost * 70 // 100
    assert await services.money.get_balance(player_id) == balance_before + expected_refund


async def test_construction_completion_via_status_screen(tg_env):
    services, lands, _, edit_mock = tg_env
    player_id = await _register(services, 4009)
    await _give_money(services, player_id, 100_000_000_000)
    await services.realestate.buy_land(player_id, lands[5].id)
    spec = construction_domain.BuildingSpec(
        land_id=lands[5].id,
        building_type="v",
        floors=1,
        area_sqm=construction_domain.size_presets(lands[5].area_sqm, 1)[0],
        bedrooms=2,
        quality_token="m",
        parking=True,
        elevator=False,
        storage=True,
    )
    started = await services.realestate.start_construction(player_id, lands[5].id, spec)

    # Backdate to 40% progress → the status screen shows the progress bar.
    async with services.players._session_factory() as session:
        project = await session.get(ConstructionProject, started.project.id)
        now = datetime.now(timezone.utc)
        project.started_at = now - timedelta(seconds=project.duration_seconds * 0.4)
        project.completes_at = now + timedelta(seconds=project.duration_seconds * 0.6)
        session.add(project)
        await session.commit()

    query = make_query(4009, callbacks.RE_STATUS)
    await realestate.show_status(make_update(query), make_context(services))
    text = edit_mock.await_args.kwargs["text"]
    assert "در حال ساخت" in text
    assert "▓" in text and "░" in text
    assert "زمان باقی‌مانده" in text

    # Finish it, then open the status screen again → house created.
    async with services.players._session_factory() as session:
        project = await session.get(ConstructionProject, started.project.id)
        now = datetime.now(timezone.utc)
        project.started_at = now - timedelta(seconds=project.duration_seconds + 60)
        project.completes_at = now - timedelta(seconds=30)
        session.add(project)
        await session.commit()

    query = make_query(4009, callbacks.RE_STATUS)
    await realestate.show_status(make_update(query), make_context(services))
    text = edit_mock.await_args.kwargs["text"]
    assert "تکمیل شده" in text
    assert "خانه آماده" in text

    info = await services.realestate.get_land_info(lands[5].id)
    assert info.land.built_house_id is not None


# --- Renovation flow --------------------------------------------------------------------------


async def test_full_renovation_flow(tg_env):
    services, lands, _, edit_mock = tg_env
    player_id = await _register(services, 4010)
    await _give_money(services, player_id, 100_000_000_000)

    houses = await services.housing.ensure_initial_houses()
    old_house = next(h for h in houses if current_iranian_year() - h.construction_year >= 5)
    await services.housing.buy_from_market(player_id, old_house.id)

    # Renovation menu lists the house
    query = make_query(4010, callbacks.RE_RENOV_MENU)
    await realestate.show_renov_menu(make_update(query), make_context(services))
    text = edit_mock.await_args.kwargs["text"]
    assert "بازسازی خانه" in text
    assert f"{callbacks.RE_RENOV_OPTS_PREFIX}{old_house.id}" in flat_callbacks(
        edit_mock.await_args.kwargs["reply_markup"]
    )

    # Options screen quotes modernize (the house is old)
    query = make_query(4010, f"{callbacks.RE_RENOV_OPTS_PREFIX}{old_house.id}")
    await realestate.show_renovation_options(make_update(query), make_context(services))
    data = flat_callbacks(edit_mock.await_args.kwargs["reply_markup"])
    modernize_cb = f"{callbacks.RE_RENOV_CONFIRM_PREFIX}{old_house.id}_m"
    assert modernize_cb in data

    # Confirmation screen
    query = make_query(4010, modernize_cb)
    await realestate.show_renovation_confirmation(
        make_update(query), make_context(services)
    )
    text = edit_mock.await_args.kwargs["text"]
    assert "نوسازی" in text

    # Execute → project created, money moved
    balance_before = await services.money.get_balance(player_id)
    query = make_query(4010, f"{callbacks.RE_RENOV_OK_PREFIX}{old_house.id}_m")
    await realestate.confirm_renovation(make_update(query), make_context(services))
    text = edit_mock.await_args_list[-1].kwargs["text"]
    assert "بازسازی شروع شد" in text

    status = await services.realestate.get_projects_status(player_id)
    assert len(status.renovations) == 1
    renovation = status.renovations[0]
    assert renovation.renovation_type == "m"
    assert await services.money.get_balance(player_id) == balance_before - renovation.cost


async def test_renovation_blocked_for_rented_house_shows_friendly(tg_env):
    services, _, _, edit_mock = tg_env
    owner_id = await _register(services, 4011, "مالک")
    tenant_id = await _register(services, 4012, "مستاجر")
    await _give_money(services, owner_id, 100_000_000_000)
    await _give_money(services, tenant_id, 100_000_000_000)

    houses = await services.housing.ensure_initial_houses()
    await services.housing.buy_from_market(owner_id, houses[4].id)
    options = await services.housing.get_rent_options(houses[4].id, owner_id)
    _, deposit, rent = options.options[0]
    await services.housing.list_house_for_rent(owner_id, houses[4].id, rent, 0)
    await services.housing.rent_house(tenant_id, houses[4].id)

    query = make_query(4011, f"{callbacks.RE_RENOV_OK_PREFIX}{houses[4].id}_q")
    await realestate.confirm_renovation(make_update(query), make_context(services))
    text = edit_mock.await_args.kwargs["text"]
    assert "مستأجر" in text


# --- Housing menu integration ------------------------------------------------------------------


async def test_housing_menu_includes_real_estate_section(services):
    from app.bot.keyboards.housing import build_housing_menu

    data = flat_callbacks(build_housing_menu())
    assert callbacks.RE_LANDS_MY in data
    assert callbacks.RE_LANDS_MARKET in data
    assert callbacks.RE_BUILD_MENU in data
    assert callbacks.RE_STATUS in data
    assert callbacks.RE_RENOV_MENU in data


async def test_text_trigger_status_screen(services, monkeypatch):
    from telegram import Chat, Message

    await services.housing.ensure_initial_houses()
    await services.realestate.ensure_initial_lands()
    await _register(services, 4012)
    reply_mock = AsyncMock()
    monkeypatch.setattr(Message, "reply_text", reply_mock)

    user = make_user(4012)
    message = Message(
        message_id=1,
        date=datetime.now(),
        chat=Chat(id=user.id, type=Chat.PRIVATE),
        from_user=user,
        text="وضعیت ساخت",
    )
    await realestate.status_text_handler(
        Update(update_id=1, message=message), make_context(services)
    )
    reply_mock.assert_awaited_once()
    assert "پروژه" in reply_mock.await_args.args[0]  # text passed positionally


async def test_identical_edit_race_is_tolerated(services, monkeypatch):
    await services.realestate.ensure_initial_lands()
    await _register(services, 4013)
    answer_mock = AsyncMock()

    async def not_modified(*args, **kwargs):
        raise BadRequest("Message is not modified")

    monkeypatch.setattr(CallbackQuery, "answer", answer_mock)
    monkeypatch.setattr(CallbackQuery, "edit_message_text", not_modified)

    query = make_query(4013, callbacks.RE_LANDS_MARKET)
    await realestate.show_lands_market(make_update(query), make_context(services))
    answer_mock.assert_awaited_once()  # no crash despite BadRequest
