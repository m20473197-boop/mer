"""Keyboard architecture tests — only real features are exposed."""

from __future__ import annotations

from telegram import InlineKeyboardMarkup

from app.bot.keyboards import callbacks
from app.bot.keyboards.main_menu import (
    BUTTON_BACK_TO_MAIN,
    BUTTON_BUSINESS,
    BUTTON_DIVAR,
    BUTTON_HOUSING,
    BUTTON_IRAN_MARKET,
    BUTTON_VEHICLE_DEALERSHIP,
    BUTTON_JOBS,
    BUTTON_PROFILE,
    BUTTON_STATUS,
    build_back_to_main,
    build_main_menu,
)


def _flat_buttons(markup: InlineKeyboardMarkup):
    return [button for row in markup.inline_keyboard for button in row]


def test_main_menu_exposes_only_implemented_features():
    buttons = _flat_buttons(build_main_menu())

    assert {b.text for b in buttons} == {
        BUTTON_PROFILE,
        BUTTON_STATUS,
        BUTTON_JOBS,
        BUTTON_BUSINESS,
        BUTTON_IRAN_MARKET,
        BUTTON_DIVAR,
        BUTTON_VEHICLE_DEALERSHIP,
        BUTTON_HOUSING,
    }
    assert {b.callback_data for b in buttons} == {
        callbacks.PROFILE,
        callbacks.STATUS,
        callbacks.JOBS_MENU,
        callbacks.BUSINESS_MENU,
        callbacks.MARKET_MENU,
        callbacks.DIVAR_MENU,
        callbacks.VEHICLE_MENU,
        callbacks.HOUSING_MENU,
    }
    # No fake buttons for future systems (crime, vehicles, ...).
    # Housing and «بازار ایران» are implemented, so both are allowed.
    labels = " ".join(b.text for b in buttons).lower()
    for banned in ("جرم", "وسیله", "fromid", "market", "crime", "vehicle"):
        assert banned not in labels


def test_back_button_returns_to_main_menu():
    buttons = _flat_buttons(build_back_to_main())

    assert len(buttons) == 1
    assert buttons[0].callback_data == callbacks.BACK_TO_MAIN
    assert buttons[0].text == BUTTON_BACK_TO_MAIN


# --- Housing keyboards ---------------------------------------------------------


def _markup_rows(markup: InlineKeyboardMarkup):
    return markup.inline_keyboard


def test_housing_menu_exposes_all_housing_screens():
    from app.bot.keyboards import build_housing_menu

    rows = _markup_rows(build_housing_menu())
    data = [b.callback_data for row in rows for b in row]

    assert callbacks.HOUSES_MY in data          # my houses (assets)
    assert callbacks.HOUSES_MARKET in data      # available houses (buy)
    assert callbacks.HOUSES_RENTALS in data     # available rentals
    assert callbacks.HOUSES_MY_RENTS in data    # my rental contracts
    assert callbacks.BACK_TO_MAIN in data


def test_market_list_has_info_and_buy_buttons_per_house():
    from datetime import datetime, timezone

    from app.bot.keyboards import build_market_list
    from app.game.housing.dto import HouseData, HouseMarketEntry

    house = HouseData(
        id=7,
        city="تهران",
        neighborhood="ونک",
        area_sqm=80,
        bedrooms=2,
        living_rooms=1,
        bathrooms=1,
        kitchen_type="مدرن",
        construction_year=1395,
        parking=True,
        elevator=True,
        storage=False,
        quality="خوب",
        owner_player_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    markup = build_market_list(
        [HouseMarketEntry(house=house, price=1, market_value=1, seller_player_id=None, seller_name=None)]
    )
    data = [b.callback_data for row in _markup_rows(markup) for b in row]
    assert f"{callbacks.HOUSE_INFO_PREFIX}7" in data
    assert f"{callbacks.HOUSE_BUY_PREFIX}7" in data


def test_sale_price_options_cover_presets():
    from app.bot.keyboards import build_sale_price_options
    from app.game.housing.dto import SaleOptions

    options = SaleOptions(
        house_id=3, market_value=1_000_000_000, price_options=((850, 850_000_000), (1000, 1_000_000_000))
    )
    markup = build_sale_price_options(options)
    data = [b.callback_data for row in _markup_rows(markup) for b in row]
    assert f"{callbacks.HOUSE_SELL_SET_PREFIX}3_850" in data
    assert f"{callbacks.HOUSE_SELL_SET_PREFIX}3_1000" in data
    assert f"{callbacks.HOUSE_SELL_CANCEL_PREFIX}3" in data


def test_rent_options_cover_deposit_presets():
    from app.bot.keyboards import build_rent_options
    from app.game.housing.dto import RentOptions

    options = RentOptions(
        house_id=5,
        market_value=1_000_000_000,
        options=((0, 0, 6_000_000), (10, 100_000_000, 5_000_000)),
    )
    markup = build_rent_options(options)
    data = [b.callback_data for row in _markup_rows(markup) for b in row]
    assert f"{callbacks.HOUSE_RENT_SET_PREFIX}5_0" in data
    assert f"{callbacks.HOUSE_RENT_SET_PREFIX}5_10" in data
    assert f"{callbacks.HOUSE_RENT_CANCEL_PREFIX}5" in data
