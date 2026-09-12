"""Housing keyboard builders — every housing screen is button-driven."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards import callbacks
from app.bot.keyboards.main_menu import BUTTON_BACK_TO_MAIN
from app.bot.keyboards.realestate import (
    BUTTON_BUILD,
    BUTTON_BUILD_STATUS,
    BUTTON_LANDS_MARKET,
    BUTTON_LANDS_MY,
    BUTTON_RENOVATE,
)
from app.bot.messages.formatters import fa_int

# --- Button labels ------------------------------------------------------------

BUTTON_HOUSING: str = "🏠 خانه"
BUTTON_HOUSES_MY: str = "🏠 خانه‌های من"
BUTTON_HOUSES_MARKET: str = "🏘️ بازار مسکن"
BUTTON_HOUSES_RENTALS: str = "🛏️ خانه‌های اجاره‌ای"
BUTTON_HOUSES_MY_RENTS: str = "📜 قراردادهای اجاره من"
BUTTON_BACK_TO_HOUSING: str = "🔙 منوی خانه"

BUTTON_INFO: str = "ℹ️"
BUTTON_BUY: str = "🛒 خرید"
BUTTON_CONFIRM_BUY: str = "✅ تأیید خرید"
BUTTON_SELL: str = "🏷️ فروش"
BUTTON_RENT_OUT: str = "🔑 اجاره‌دادن"
BUTTON_RENOVATE_HOUSE: str = "🛠️"
BUTTON_CANCEL_SALE: str = "❌ لغو فروش"
BUTTON_CANCEL_RENT: str = "❌ لغو اجاره"
BUTTON_RENT: str = "🔑 اجاره"
BUTTON_CONFIRM_RENT: str = "✅ تأیید اجاره"
BUTTON_PAY_RENT: str = "💵 پرداخت اجاره"
BUTTON_END_CONTRACT: str = "⏹ پایان قرارداد"


def build_housing_menu() -> InlineKeyboardMarkup:
    """The housing main menu — houses, lands, construction and renovation."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    BUTTON_HOUSES_MY, callback_data=callbacks.HOUSES_MY
                ),
                InlineKeyboardButton(
                    BUTTON_HOUSES_MARKET, callback_data=callbacks.HOUSES_MARKET
                ),
            ],
            [
                InlineKeyboardButton(
                    BUTTON_HOUSES_RENTALS, callback_data=callbacks.HOUSES_RENTALS
                ),
                InlineKeyboardButton(
                    BUTTON_HOUSES_MY_RENTS, callback_data=callbacks.HOUSES_MY_RENTS
                ),
            ],
            [
                InlineKeyboardButton(
                    BUTTON_LANDS_MY, callback_data=callbacks.RE_LANDS_MY
                ),
                InlineKeyboardButton(
                    BUTTON_LANDS_MARKET, callback_data=callbacks.RE_LANDS_MARKET
                ),
            ],
            [
                InlineKeyboardButton(
                    BUTTON_BUILD, callback_data=callbacks.RE_BUILD_MENU
                ),
                InlineKeyboardButton(
                    BUTTON_BUILD_STATUS, callback_data=callbacks.RE_STATUS
                ),
            ],
            [
                InlineKeyboardButton(
                    BUTTON_RENOVATE, callback_data=callbacks.RE_RENOV_MENU
                ),
            ],
            [
                InlineKeyboardButton(
                    BUTTON_BACK_TO_MAIN, callback_data=callbacks.BACK_TO_MAIN
                ),
            ],
        ]
    )


def _back_to_housing_row() -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(
            BUTTON_BACK_TO_HOUSING, callback_data=callbacks.HOUSING_MENU
        ),
        InlineKeyboardButton(
            BUTTON_BACK_TO_MAIN, callback_data=callbacks.BACK_TO_MAIN
        ),
    ]


def _house_row(house_id: int, label: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        f"{BUTTON_INFO} {label}", callback_data=f"{callbacks.HOUSE_INFO_PREFIX}{house_id}"
    )


def build_market_list(entries) -> InlineKeyboardMarkup:
    """Purchasable houses — each with an info and a buy button."""
    rows: list[list[InlineKeyboardButton]] = []
    for entry in entries:
        house = entry.house
        label = (
            f"{house.city}، {house.neighborhood} — "
            f"{fa_int(house.area_sqm)} متری ({fa_int(entry.price)})"
        )
        rows.append(
            [
                InlineKeyboardButton(label, callback_data=f"{callbacks.HOUSE_INFO_PREFIX}{house.id}"),
                InlineKeyboardButton(
                    BUTTON_BUY, callback_data=f"{callbacks.HOUSE_BUY_PREFIX}{house.id}"
                ),
            ]
        )
    if not rows:
        rows.append([InlineKeyboardButton("— خالی —", callback_data=callbacks.HOUSING_MENU)])
    rows.append(_back_to_housing_row())
    return InlineKeyboardMarkup(rows)


def build_rentals_list(entries) -> InlineKeyboardMarkup:
    """Rentable houses — each with an info and a rent button."""
    rows: list[list[InlineKeyboardButton]] = []
    for entry in entries:
        house = entry.house
        label = (
            f"{house.city}، {house.neighborhood} — "
            f"{fa_int(house.area_sqm)} متری ({fa_int(entry.monthly_rent)}/ماه)"
        )
        rows.append(
            [
                InlineKeyboardButton(label, callback_data=f"{callbacks.HOUSE_INFO_PREFIX}{house.id}"),
                InlineKeyboardButton(
                    BUTTON_RENT, callback_data=f"{callbacks.RENT_CONFIRM_PREFIX}{house.id}"
                ),
            ]
        )
    if not rows:
        rows.append([InlineKeyboardButton("— خالی —", callback_data=callbacks.HOUSING_MENU)])
    rows.append(_back_to_housing_row())
    return InlineKeyboardMarkup(rows)


def build_my_houses(assets) -> InlineKeyboardMarkup:
    """The player's houses with contextual owner actions."""
    rows: list[list[InlineKeyboardButton]] = []

    listed_sale = {listing.house_id for listing in assets.active_sale_listings}
    listed_rent = {listing.house_id for listing in assets.active_rent_listings}
    rented_out = {contract.house_id for contract in assets.rented_out_contracts}

    for house in assets.houses:
        label = f"{house.city}، {house.neighborhood} ({fa_int(house.area_sqm)} متری)"
        rows.append(
            [
                InlineKeyboardButton(
                    f"ℹ️ {label}",
                    callback_data=f"{callbacks.HOUSE_INFO_PREFIX}{house.id}",
                )
            ]
        )
        actions: list[InlineKeyboardButton] = []
        if house.id in listed_sale:
            actions.append(
                InlineKeyboardButton(
                    BUTTON_CANCEL_SALE,
                    callback_data=f"{callbacks.HOUSE_SELL_CANCEL_PREFIX}{house.id}",
                )
            )
        elif house.id in rented_out:
            actions.append(
                InlineKeyboardButton(
                    BUTTON_END_CONTRACT,
                    callback_data=f"{callbacks.RENT_END_PREFIX}{_contract_id_for(assets, house.id)}",
                )
            )
        elif house.id in listed_rent:
            actions.append(
                InlineKeyboardButton(
                    BUTTON_CANCEL_RENT,
                    callback_data=f"{callbacks.HOUSE_RENT_CANCEL_PREFIX}{house.id}",
                )
            )
        else:
            actions = [
                InlineKeyboardButton(
                    BUTTON_SELL,
                    callback_data=f"{callbacks.HOUSE_SELL_OPTIONS_PREFIX}{house.id}",
                ),
                InlineKeyboardButton(
                    BUTTON_RENT_OUT,
                    callback_data=f"{callbacks.HOUSE_RENTOUT_OPTIONS_PREFIX}{house.id}",
                ),
                InlineKeyboardButton(
                    BUTTON_RENOVATE_HOUSE,
                    callback_data=f"{callbacks.RE_RENOV_OPTS_PREFIX}{house.id}",
                ),
            ]
        rows.append(actions)

    if not rows:
        rows.append([InlineKeyboardButton("— هنوز خانه‌ای نداری —", callback_data=callbacks.HOUSES_MARKET)])
    rows.append(_back_to_housing_row())
    return InlineKeyboardMarkup(rows)


def _contract_id_for(assets, house_id: int) -> int:
    for contract in assets.rented_out_contracts:
        if contract.house_id == house_id:
            return contract.id
    return 0


def build_my_rents(contracts) -> InlineKeyboardMarkup:
    """The player's rental contracts as tenant — pay / end per contract."""
    rows: list[list[InlineKeyboardButton]] = []
    for contract in contracts:
        rows.append(
            [
                InlineKeyboardButton(
                    f"🏠 {contract.house_label or f'خانه #{contract.house_id}'}",
                    callback_data=f"{callbacks.HOUSE_INFO_PREFIX}{contract.house_id}",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    BUTTON_PAY_RENT,
                    callback_data=f"{callbacks.RENT_PAY_PREFIX}{contract.id}",
                ),
                InlineKeyboardButton(
                    BUTTON_END_CONTRACT,
                    callback_data=f"{callbacks.RENT_END_PREFIX}{contract.id}",
                ),
            ]
        )
    if not rows:
        rows.append(
            [
                InlineKeyboardButton(
                    "— قراردادی نداری —", callback_data=callbacks.HOUSES_RENTALS
                )
            ]
        )
    rows.append(_back_to_housing_row())
    return InlineKeyboardMarkup(rows)


def build_house_info(info, viewer_player_id: int | None) -> InlineKeyboardMarkup:
    """Context-aware buttons under a house information screen."""
    rows: list[list[InlineKeyboardButton]] = []
    house = info.house
    is_owner = (
        viewer_player_id is not None and house.owner_player_id == viewer_player_id
    )
    is_tenant = info.tenanted_by_me

    if house.owner_player_id is None:
        # System market — anyone can buy.
        rows.append(
            [
                InlineKeyboardButton(
                    BUTTON_CONFIRM_BUY,
                    callback_data=f"{callbacks.HOUSE_BUY_CONFIRM_PREFIX}{house.id}",
                )
            ]
        )
    elif is_owner and info.active_sale_price is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    BUTTON_CANCEL_SALE,
                    callback_data=f"{callbacks.HOUSE_SELL_CANCEL_PREFIX}{house.id}",
                )
            ]
        )
    elif is_owner and info.active_rent is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    BUTTON_CANCEL_RENT,
                    callback_data=f"{callbacks.HOUSE_RENT_CANCEL_PREFIX}{house.id}",
                )
            ]
        )
    elif is_owner:
        rows.append(
            [
                InlineKeyboardButton(
                    BUTTON_SELL,
                    callback_data=f"{callbacks.HOUSE_SELL_OPTIONS_PREFIX}{house.id}",
                ),
                InlineKeyboardButton(
                    BUTTON_RENT_OUT,
                    callback_data=f"{callbacks.HOUSE_RENTOUT_OPTIONS_PREFIX}{house.id}",
                ),
            ]
        )
    elif is_tenant:
        contract_id = info.contract_id or 0
        rows.append(
            [
                InlineKeyboardButton(
                    BUTTON_PAY_RENT,
                    callback_data=f"{callbacks.RENT_PAY_PREFIX}{contract_id}",
                ),
                InlineKeyboardButton(
                    BUTTON_END_CONTRACT,
                    callback_data=f"{callbacks.RENT_END_PREFIX}{contract_id}",
                ),
            ]
        )
    elif info.active_sale_price is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    BUTTON_BUY,
                    callback_data=f"{callbacks.HOUSE_BUY_PREFIX}{house.id}",
                )
            ]
        )
    elif info.active_rent is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    BUTTON_RENT,
                    callback_data=f"{callbacks.RENT_CONFIRM_PREFIX}{house.id}",
                )
            ]
        )

    rows.append(_back_to_housing_row())
    return InlineKeyboardMarkup(rows)


def build_buy_confirmation(house_id: int) -> InlineKeyboardMarkup:
    """Buy confirmation — no accidental billion-Toman purchases."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    BUTTON_CONFIRM_BUY,
                    callback_data=f"{callbacks.HOUSE_BUY_CONFIRM_PREFIX}{house_id}",
                )
            ],
            _back_to_housing_row(),
        ]
    )


def build_rent_confirmation(house_id: int) -> InlineKeyboardMarkup:
    """Rent confirmation — shows the deposit obligation before signing."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    BUTTON_CONFIRM_RENT,
                    callback_data=f"{callbacks.RENT_CONFIRM_PREFIX}{house_id}",
                )
            ],
            _back_to_housing_row(),
        ]
    )


def build_sale_price_options(sale_options) -> InlineKeyboardMarkup:
    """Asking-price presets around the dynamic market value."""
    rows: list[list[InlineKeyboardButton]] = []
    for per_mille, price in sale_options.price_options:
        percent_label = fa_int(per_mille // 10)
        rows.append(
            [
                InlineKeyboardButton(
                    f"🏷️ {percent_label}٪ ارزش ({fa_int(price)})",
                    callback_data=(
                        f"{callbacks.HOUSE_SELL_SET_PREFIX}{sale_options.house_id}_{per_mille}"
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                BUTTON_CANCEL_SALE,
                callback_data=f"{callbacks.HOUSE_SELL_CANCEL_PREFIX}{sale_options.house_id}",
            )
        ]
    )
    rows.append(_back_to_housing_row())
    return InlineKeyboardMarkup(rows)


def build_rent_options(rent_options) -> InlineKeyboardMarkup:
    """(deposit, rent) presets for renting a house out."""
    rows: list[list[InlineKeyboardButton]] = []
    for deposit_percent, deposit, rent in rent_options.options:
        label = (
            f"🔑 رهن {fa_int(deposit_percent)}٪ + اجاره {fa_int(rent)}"
            if deposit_percent
            else f"🔑 بدون رهن + اجاره {fa_int(rent)}"
        )
        rows.append(
            [
                InlineKeyboardButton(
                    label,
                    callback_data=(
                        f"{callbacks.HOUSE_RENT_SET_PREFIX}"
                        f"{rent_options.house_id}_{deposit_percent}"
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                BUTTON_CANCEL_RENT,
                callback_data=f"{callbacks.HOUSE_RENT_CANCEL_PREFIX}{rent_options.house_id}",
            )
        ]
    )
    rows.append(_back_to_housing_row())
    return InlineKeyboardMarkup(rows)
