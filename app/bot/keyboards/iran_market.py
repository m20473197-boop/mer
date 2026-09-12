"""Inline keyboards for ``📈 بازار ایران``."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards import callbacks
from app.bot.keyboards.main_menu import BUTTON_BACK_TO_MAIN
from app.game.market.catalog import ASSET_HOUSING, IRAN_MARKET_ASSET_CATALOG
from app.game.market.dto import IranMarketAssetData


BUTTON_MARKET_BACK: str = "🔙 بازار ایران"


def build_iran_market_menu(
    assets: tuple[IranMarketAssetData, ...] | list[IranMarketAssetData],
) -> InlineKeyboardMarkup:
    by_code = {asset.code: asset for asset in assets}
    rows: list[list[InlineKeyboardButton]] = []
    for definition in IRAN_MARKET_ASSET_CATALOG:
        asset = by_code.get(definition.code)
        label = definition.display_name
        if asset is None or asset.current_price is None:
            label = f"{label} — در انتظار قیمت"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{_emoji(definition.category)} {label}",
                    callback_data=f"{callbacks.MARKET_ASSET_PREFIX}{definition.code}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                BUTTON_BACK_TO_MAIN, callback_data=callbacks.BACK_TO_MAIN
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_iran_market_detail(
    asset: IranMarketAssetData | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if (
        asset is not None
        and asset.category != ASSET_HOUSING
        and asset.current_price is not None
    ):
        rows.append(
            [
                InlineKeyboardButton(
                    "🛒 خرید",
                    callback_data=f"{callbacks.MARKET_BUY_PREFIX}{asset.code}",
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    BUTTON_MARKET_BACK, callback_data=callbacks.MARKET_MENU
                )
            ],
            [
                InlineKeyboardButton(
                    BUTTON_BACK_TO_MAIN, callback_data=callbacks.BACK_TO_MAIN
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(rows)


def _emoji(category: str) -> str:
    return {
        "currency": "💵",
        "gold": "🪙",
        "coin": "🪙",
        "housing": "🏠",
    }.get(category, "📈")
