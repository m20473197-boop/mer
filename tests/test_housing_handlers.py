"""Housing handler tests — Telegram layer simulated, real services underneath.

Follows the same approach as ``test_handlers.py``: PTB Update/CallbackQuery
objects are simulated, the full service/repository/database stack is real.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import CallbackQuery, InlineKeyboardMarkup, Update, User
from telegram.error import BadRequest

from app.bot.handlers import housing
from app.bot.keyboards import callbacks


def make_user(tg_id: int, first_name: str = "علی", username: str | None = "ali") -> User:
    return User(id=tg_id, first_name=first_name, is_bot=False, username=username)


def make_query(tg_id: int, data: str) -> CallbackQuery:
    return CallbackQuery(
        id=f"q-{tg_id}-{data}", from_user=make_user(tg_id), chat_instance="ci", data=data
    )


def make_update(query: CallbackQuery) -> Update:
    return Update(update_id=1, callback_query=query)


def make_context(services) -> MagicMock:
    context = MagicMock()
    context.application.bot_data = {"services": services}
    return context


def flat_callback_data(markup: InlineKeyboardMarkup) -> set[str]:
    return {b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data}


@pytest.fixture
async def tg_env(services, monkeypatch):
    """Mock Telegram API methods and seed the starter market."""
    houses = await services.housing.ensure_initial_houses()
    answer_mock, edit_mock = AsyncMock(), AsyncMock()
    monkeypatch.setattr(CallbackQuery, "answer", answer_mock)
    monkeypatch.setattr(CallbackQuery, "edit_message_text", edit_mock)
    return services, houses, answer_mock, edit_mock


async def _register_player(services, tg_id: int, name: str = "علی") -> int:
    result = await services.players.register_or_get(
        telegram_user_id=tg_id, username=name, display_name=name
    )
    return result.player_id


async def _give_money(services, player_id: int, amount: int) -> None:
    from app.database.repositories.player_repository import PlayerRepository

    async with services.players._session_factory() as session:
        await PlayerRepository(session).add_money(player_id, amount)
        await session.commit()


# --- Menu ------------------------------------------------------------------------


async def test_housing_menu_callback(tg_env):
    services, _, _, edit_mock = tg_env
    query = make_query(2001, callbacks.HOUSING_MENU)
    await housing.show_housing_menu(make_update(query), make_context(services))

    text = edit_mock.await_args.kwargs["text"]
    assert "منوی خانه" in text
    data = flat_callback_data(edit_mock.await_args.kwargs["reply_markup"])
    assert {callbacks.HOUSES_MY, callbacks.HOUSES_MARKET, callbacks.HOUSES_RENTALS} <= data


# --- Market & buying -----------------------------------------------------------------


async def test_market_shows_houses_with_buy_buttons(tg_env):
    services, houses, _, edit_mock = tg_env
    await _register_player(services, 2002)
    query = make_query(2002, callbacks.HOUSES_MARKET)
    await housing.show_market(make_update(query), make_context(services))

    text = edit_mock.await_args.kwargs["text"]
    assert "بازار مسکن" in text or "موجود برای خرید" in text
    data = flat_callback_data(edit_mock.await_args.kwargs["reply_markup"])
    assert f"{callbacks.HOUSE_INFO_PREFIX}{houses[0].id}" in data
    assert f"{callbacks.HOUSE_BUY_PREFIX}{houses[0].id}" in data


async def test_full_buy_flow_from_buttons(tg_env):
    services, houses, _, edit_mock = tg_env
    player_id = await _register_player(services, 2003)
    await _give_money(services, player_id, 50_000_000_000)

    # Confirmation screen first
    query = make_query(2003, f"{callbacks.HOUSE_BUY_PREFIX}{houses[0].id}")
    await housing.show_buy_confirmation(make_update(query), make_context(services))
    confirm_text = edit_mock.await_args.kwargs["text"]
    assert "تأیید خرید" in confirm_text
    assert f"{callbacks.HOUSE_BUY_CONFIRM_PREFIX}{houses[0].id}" in flat_callback_data(
        edit_mock.await_args.kwargs["reply_markup"]
    )

    # Confirm — purchase executes
    query = make_query(2003, f"{callbacks.HOUSE_BUY_CONFIRM_PREFIX}{houses[0].id}")
    await housing.confirm_buy(make_update(query), make_context(services))
    bought_text = edit_mock.await_args_list[-1].kwargs["text"]
    assert "صاحب" in bought_text  # congrats message

    # Ownership + wallet really changed
    info = await services.housing.get_house_info(houses[0].id)
    assert info.house.owner_player_id == player_id
    profile = await services.players.get_profile(2003)
    assert profile.money == 50_000_000_000 - info.market_value


async def test_buy_without_money_shows_friendly_error(tg_env):
    services, houses, _, edit_mock = tg_env
    await _register_player(services, 2004)  # zero balance

    query = make_query(2004, f"{callbacks.HOUSE_BUY_CONFIRM_PREFIX}{houses[0].id}")
    await housing.confirm_buy(make_update(query), make_context(services))

    text = edit_mock.await_args.kwargs["text"]
    assert "پول کافی" in text


# --- Selling flow (buttons) -------------------------------------------------------------


async def test_full_sell_flow_from_buttons(tg_env):
    services, houses, _, edit_mock = tg_env
    player_id = await _register_player(services, 2005)
    await _give_money(services, player_id, 50_000_000_000)
    await services.housing.buy_from_market(player_id, houses[1].id)

    # Open sale options
    query = make_query(2005, f"{callbacks.HOUSE_SELL_OPTIONS_PREFIX}{houses[1].id}")
    await housing.show_sale_options(make_update(query), make_context(services))
    markup = edit_mock.await_args.kwargs["reply_markup"]
    assert f"{callbacks.HOUSE_SELL_SET_PREFIX}{houses[1].id}_1150" in flat_callback_data(markup)

    # Choose the 115% preset
    query = make_query(2005, f"{callbacks.HOUSE_SELL_SET_PREFIX}{houses[1].id}_1150")
    await housing.confirm_sell(make_update(query), make_context(services))
    text = edit_mock.await_args.kwargs["text"]
    assert "آگهی" in text and "فروش" in text

    # The listing really exists at 115% of the market value
    info = await services.housing.get_house_info(houses[1].id, player_id)
    assert info.active_sale_price == info.market_value * 1150 // 1000 // 100_000 * 100_000


async def test_cancel_sale_from_buttons(tg_env):
    services, houses, _, edit_mock = tg_env
    player_id = await _register_player(services, 2006)
    await _give_money(services, player_id, 50_000_000_000)
    await services.housing.buy_from_market(player_id, houses[2].id)
    options = await services.housing.get_sale_options(houses[2].id, player_id)
    await services.housing.list_house_for_sale(
        player_id, houses[2].id, dict(options.price_options)[1000]
    )

    query = make_query(2006, f"{callbacks.HOUSE_SELL_CANCEL_PREFIX}{houses[2].id}")
    await housing.cancel_sale(make_update(query), make_context(services))

    info = await services.housing.get_house_info(houses[2].id, player_id)
    assert info.active_sale_price is None


# --- Renting flow (buttons) ---------------------------------------------------------------


async def test_full_rent_out_and_rent_flow_between_players(tg_env):
    services, houses, _, edit_mock = tg_env
    owner_id = await _register_player(services, 2007, "صاحبخانه")
    tenant_id = await _register_player(services, 2008, "مستاجر")
    await _give_money(services, owner_id, 50_000_000_000)
    await _give_money(services, tenant_id, 20_000_000_000)
    await services.housing.buy_from_market(owner_id, houses[3].id)

    # Owner: open rent options
    query = make_query(2007, f"{callbacks.HOUSE_RENTOUT_OPTIONS_PREFIX}{houses[3].id}")
    await housing.show_rentout_options(make_update(query), make_context(services))
    assert f"{callbacks.HOUSE_RENT_SET_PREFIX}{houses[3].id}_10" in flat_callback_data(
        edit_mock.await_args.kwargs["reply_markup"]
    )

    # Owner: choose 10% deposit preset
    query = make_query(2007, f"{callbacks.HOUSE_RENT_SET_PREFIX}{houses[3].id}_10")
    await housing.confirm_rent_out(make_update(query), make_context(services))
    assert "اجاره" in edit_mock.await_args.kwargs["text"]

    info = await services.housing.get_house_info(houses[3].id)
    rent, deposit = info.active_rent

    # Tenant: confirmation screen
    query = make_query(2008, f"{callbacks.RENT_CONFIRM_PREFIX}{houses[3].id}")
    await housing.show_rent_confirmation(make_update(query), make_context(services))
    assert "تأیید اجاره" in edit_mock.await_args.kwargs["text"]

    # Tenant: signs the contract
    owner_before = await services.money.get_balance(owner_id)
    tenant_before = await services.money.get_balance(tenant_id)
    query = make_query(2008, f"{callbacks.RENT_CONFIRM_PREFIX}{houses[3].id}")
    await housing.confirm_rent(make_update(query), make_context(services))
    assert "قرارداد" in edit_mock.await_args.kwargs["text"]

    # Deposit really moved tenant -> owner
    assert await services.money.get_balance(tenant_id) == tenant_before - deposit
    assert await services.money.get_balance(owner_id) == owner_before + deposit

    # Tenant sees the contract with pay/end buttons
    contracts = await services.housing.get_my_rental_contracts(tenant_id)
    assert len(contracts) == 1
    contract_id = contracts[0].id

    # Tenant pays the rent via the button
    owner_before = await services.money.get_balance(owner_id)
    tenant_before = await services.money.get_balance(tenant_id)
    query = make_query(2008, f"{callbacks.RENT_PAY_PREFIX}{contract_id}")
    await housing.pay_rent(make_update(query), make_context(services))
    assert "اجاره پرداخت شد" in edit_mock.await_args.kwargs["text"]
    assert await services.money.get_balance(tenant_id) == tenant_before - contracts[0].monthly_rent
    assert await services.money.get_balance(owner_id) == owner_before + contracts[0].monthly_rent

    # Tenant ends the contract via the button
    query = make_query(2008, f"{callbacks.RENT_END_PREFIX}{contract_id}")
    await housing.end_rent_contract(make_update(query), make_context(services))
    assert "تمام شد" in edit_mock.await_args.kwargs["text"]

    contracts = await services.housing.get_my_rental_contracts(tenant_id)
    assert contracts == []


async def test_my_rents_screen_lists_contracts(tg_env):
    services, houses, _, edit_mock = tg_env
    owner_id = await _register_player(services, 2009)
    tenant_id = await _register_player(services, 2010)
    await _give_money(services, owner_id, 50_000_000_000)
    await _give_money(services, tenant_id, 20_000_000_000)
    await services.housing.buy_from_market(owner_id, houses[4].id)
    options = await services.housing.get_rent_options(houses[4].id, owner_id)
    _, deposit, rent = options.options[0]
    await services.housing.list_house_for_rent(owner_id, houses[4].id, rent, 0)
    await services.housing.rent_house(tenant_id, houses[4].id)

    query = make_query(2010, callbacks.HOUSES_MY_RENTS)
    await housing.show_my_rents(make_update(query), make_context(services))

    text = edit_mock.await_args.kwargs["text"]
    assert "قرارداد" in text
    contracts = await services.housing.get_my_rental_contracts(tenant_id)
    assert f"{callbacks.RENT_PAY_PREFIX}{contracts[0].id}" in flat_callback_data(
        edit_mock.await_args.kwargs["reply_markup"]
    )


# --- Info screen ------------------------------------------------------------------------


async def test_house_info_shows_all_properties(tg_env):
    services, houses, _, edit_mock = tg_env
    await _register_player(services, 2011)

    query = make_query(2011, f"{callbacks.HOUSE_INFO_PREFIX}{houses[0].id}")
    await housing.show_house_info(make_update(query), make_context(services))

    text = edit_mock.await_args.kwargs["text"]
    for expected in ("شهر", "محله", "متراژ", "خواب", "سرویس", "آشپزخانه", "سال ساخت",
                     "پارکینگ", "آسانسور", "انباری", "کیفیت", "ارزش لحظه‌ای"):
        assert expected in text


# --- Unregistered users -------------------------------------------------------------------


async def test_market_for_unregistered_user_is_safe(tg_env):
    services, _, _, edit_mock = tg_env
    query = make_query(2999, callbacks.HOUSES_MARKET)  # never registered
    await housing.show_market(make_update(query), make_context(services))

    text = edit_mock.await_args.kwargs["text"]
    assert "ثبت‌نام" in text or "بازار" in text  # friendly message, no crash


# --- Text trigger ---------------------------------------------------------------------------


async def test_housing_text_trigger_opens_menu(services, monkeypatch):
    from telegram import Chat, Message

    await services.housing.ensure_initial_houses()
    await _register_player(services, 2012)
    reply_mock = AsyncMock()
    monkeypatch.setattr(Message, "reply_text", reply_mock)

    user = make_user(2012)
    message = Message(
        message_id=1,
        date=datetime.now(),
        chat=Chat(id=user.id, type=Chat.PRIVATE),
        from_user=user,
        text="خانه",
    )
    await housing.housing_text_handler(Update(update_id=1, message=message), make_context(services))

    reply_mock.assert_awaited_once()
    assert "منوی خانه" in reply_mock.await_args.kwargs["text"]


# --- Identical edit races are tolerated ---------------------------------------------------------


async def test_identical_edit_is_tolerated(services, monkeypatch):
    await services.housing.ensure_initial_houses()
    await _register_player(services, 2013)
    answer_mock = AsyncMock()

    async def edit_conflict(*args, **kwargs):
        raise BadRequest("Message is not modified")

    monkeypatch.setattr(CallbackQuery, "answer", answer_mock)
    monkeypatch.setattr(CallbackQuery, "edit_message_text", edit_conflict)

    query = make_query(2013, callbacks.HOUSING_MENU)
    # Must not raise despite the BadRequest
    await housing.show_housing_menu(make_update(query), make_context(services))
    answer_mock.assert_awaited_once()
