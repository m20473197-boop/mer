"""Inline keyboards for the ``🧱 دیوار ایران`` marketplace."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards import callbacks
from app.bot.keyboards.main_menu import BUTTON_BACK_TO_MAIN
from app.bot.messages.formatters import fa_int
from app.game.marketplace.catalog import (
    ASSET_TYPE_CAR,
    ASSET_TYPE_HOUSE,
    ASSET_TYPE_LAND,
    CATEGORY_LABELS,
)
from app.game.marketplace.dto import (
    MarketplaceFilterState,
    MarketplaceListingData,
    MarketplaceOwnedAssetData,
    MarketplaceSearchResult,
)

BUTTON_DIVAR_BACK: str = "🔙 منوی دیوار ایران"
BUTTON_EMPTY: str = "— موردی پیدا نشد —"


def build_divar_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔎 جستجو", callback_data=callbacks.DIVAR_SEARCH),
                InlineKeyboardButton("🏷️ دسته‌بندی‌ها", callback_data=callbacks.DIVAR_CATEGORIES),
            ],
            [
                InlineKeyboardButton("➕ ثبت آگهی", callback_data=callbacks.DIVAR_CREATE),
                InlineKeyboardButton("📋 آگهی‌های من", callback_data=callbacks.DIVAR_MY_LISTINGS),
            ],
            [InlineKeyboardButton("📋 همه آگهی‌ها", callback_data=callbacks.DIVAR_SHOW_ALL)],
            [InlineKeyboardButton(BUTTON_BACK_TO_MAIN, callback_data=callbacks.BACK_TO_MAIN)],
        ]
    )


def build_divar_categories() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🏠 خانه",
                    callback_data=f"{callbacks.DIVAR_CATEGORY_PREFIX}{ASSET_TYPE_HOUSE}",
                ),
                InlineKeyboardButton(
                    "🌍 زمین",
                    callback_data=f"{callbacks.DIVAR_CATEGORY_PREFIX}{ASSET_TYPE_LAND}",
                ),
                InlineKeyboardButton(
                    "🚗 ماشین",
                    callback_data=f"{callbacks.DIVAR_CATEGORY_PREFIX}{ASSET_TYPE_CAR}",
                ),
            ],
            [InlineKeyboardButton("📋 همه آگهی‌ها", callback_data=callbacks.DIVAR_SHOW_ALL)],
            [InlineKeyboardButton(BUTTON_DIVAR_BACK, callback_data=callbacks.DIVAR_MENU)],
        ]
    )


def build_divar_results(
    result: MarketplaceSearchResult,
    *,
    state_token: str,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for listing in result.listings:
        rows.append(
            [
                InlineKeyboardButton(
                    _compact_label(listing),
                    callback_data=f"{callbacks.DIVAR_DETAIL_PREFIX}{listing.id}",
                )
            ]
        )
    if not rows:
        rows.append([InlineKeyboardButton(BUTTON_EMPTY, callback_data=callbacks.DIVAR_FILTERS)])

    navigation: list[InlineKeyboardButton] = []
    if result.has_previous:
        navigation.append(
            InlineKeyboardButton(
                "⬅️ صفحه قبل",
                callback_data=f"{callbacks.DIVAR_PAGE_PREFIX}{state_token}_{result.page - 1}",
            )
        )
    if result.has_next:
        navigation.append(
            InlineKeyboardButton(
                "➡️ صفحه بعد",
                callback_data=f"{callbacks.DIVAR_PAGE_PREFIX}{state_token}_{result.page + 1}",
            )
        )
    if navigation:
        rows.append(navigation)
    rows.append(
        [
            InlineKeyboardButton("🔎 تغییر جستجو/فیلتر", callback_data=callbacks.DIVAR_FILTERS),
            InlineKeyboardButton(BUTTON_DIVAR_BACK, callback_data=callbacks.DIVAR_MENU),
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_divar_listing_detail(
    listing: MarketplaceListingData,
    *,
    viewer_player_id: int | None,
    back_callback_data: str = callbacks.DIVAR_FILTERS,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if listing.is_active and viewer_player_id != listing.seller_player_id:
        rows.append(
            [InlineKeyboardButton("🛒 خرید", callback_data=f"{callbacks.DIVAR_BUY_PREFIX}{listing.id}")]
        )
    if listing.is_active and viewer_player_id == listing.seller_player_id:
        rows.append(
            [InlineKeyboardButton("❌ لغو آگهی", callback_data=f"{callbacks.DIVAR_CANCEL_PREFIX}{listing.id}")]
        )
    rows.extend(
        [
            [InlineKeyboardButton("🔙 نتایج آگهی‌ها", callback_data=back_callback_data)],
            [InlineKeyboardButton(BUTTON_DIVAR_BACK, callback_data=callbacks.DIVAR_MENU)],
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_divar_owned_assets(
    assets: list[MarketplaceOwnedAssetData],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for asset in assets:
        if asset.asset_type == ASSET_TYPE_HOUSE:
            prefix = callbacks.DIVAR_SELL_HOUSE_PREFIX
        elif asset.asset_type == ASSET_TYPE_LAND:
            prefix = callbacks.DIVAR_SELL_LAND_PREFIX
        else:
            prefix = callbacks.DIVAR_SELL_CAR_PREFIX
        area = f" — {fa_int(asset.area_sqm)} متر" if asset.area_sqm is not None else ""
        rows.append(
            [
                InlineKeyboardButton(
                    f"{asset.label}{area}",
                    callback_data=f"{prefix}{asset.asset_id}",
                )
            ]
        )
    if not rows:
        rows.append([InlineKeyboardButton(BUTTON_EMPTY, callback_data=callbacks.DIVAR_MENU)])
    rows.append([InlineKeyboardButton(BUTTON_DIVAR_BACK, callback_data=callbacks.DIVAR_MENU)])
    return InlineKeyboardMarkup(rows)


def build_divar_my_listings(listings: list[MarketplaceListingData]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for listing in listings:
        rows.append(
            [
                InlineKeyboardButton(
                    f"{_compact_label(listing)} — ❌ لغو",
                    callback_data=f"{callbacks.DIVAR_CANCEL_PREFIX}{listing.id}",
                )
            ]
        )
    if not rows:
        rows.append([InlineKeyboardButton(BUTTON_EMPTY, callback_data=callbacks.DIVAR_MENU)])
    rows.append([InlineKeyboardButton(BUTTON_DIVAR_BACK, callback_data=callbacks.DIVAR_MENU)])
    return InlineKeyboardMarkup(rows)


def build_divar_filters(state: MarketplaceFilterState) -> InlineKeyboardMarkup:
    criteria = state.criteria
    category_label = CATEGORY_LABELS.get(criteria.asset_type, "همه")
    city_label = criteria.city or "همه شهرها"
    rows = [
        [InlineKeyboardButton(f"🏷️ دسته: {category_label}", callback_data=callbacks.DIVAR_FILTERS)],
        [
            InlineKeyboardButton(
                "🏠 خانه",
                callback_data=f"{callbacks.DIVAR_FILTER_CATEGORY_PREFIX}{ASSET_TYPE_HOUSE}",
            ),
            InlineKeyboardButton(
                "🌍 زمین",
                callback_data=f"{callbacks.DIVAR_FILTER_CATEGORY_PREFIX}{ASSET_TYPE_LAND}",
            ),
            InlineKeyboardButton(
                "🚗 ماشین",
                callback_data=f"{callbacks.DIVAR_FILTER_CATEGORY_PREFIX}{ASSET_TYPE_CAR}",
            ),
        ],
        [InlineKeyboardButton(f"📍 شهر: {city_label}", callback_data=callbacks.DIVAR_FILTER_CITY_MENU)],
        [
            InlineKeyboardButton("💰 بازه قیمت", callback_data=callbacks.DIVAR_FILTER_PRICE),
            InlineKeyboardButton("📐 بازه متراژ", callback_data=callbacks.DIVAR_FILTER_AREA),
        ],
        [InlineKeyboardButton("📍 محله", callback_data=callbacks.DIVAR_FILTER_NEIGHBORHOOD)],
        [InlineKeyboardButton("🧹 پاک‌کردن فیلترها", callback_data=callbacks.DIVAR_FILTER_CLEAR)],
        [InlineKeyboardButton("✅ نمایش نتایج", callback_data=callbacks.DIVAR_FILTER_APPLY)],
        [InlineKeyboardButton(BUTTON_DIVAR_BACK, callback_data=callbacks.DIVAR_MENU)],
    ]
    return InlineKeyboardMarkup(rows)


def build_divar_city_filters(cities: list[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton("همه شهرها", callback_data=f"{callbacks.DIVAR_FILTER_CITY_PREFIX}all")]
    ]
    for index, city in enumerate(cities):
        rows.append(
            [
                InlineKeyboardButton(
                    city,
                    callback_data=f"{callbacks.DIVAR_FILTER_CITY_PREFIX}{index}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(BUTTON_DIVAR_BACK, callback_data=callbacks.DIVAR_FILTERS)])
    return InlineKeyboardMarkup(rows)


def _compact_label(listing: MarketplaceListingData) -> str:
    asset = listing.house or listing.land
    if listing.vehicle is not None:
        return (
            f"🚗 #{fa_int(listing.id)} {listing.vehicle.model.name} — "
            f"{fa_int(listing.price)} تومان"
        )
    if asset is None:
        return f"#{fa_int(listing.id)} — آگهی"
    if listing.house is not None:
        return (
            f"🏠 #{fa_int(listing.id)} {asset.city}، {asset.neighborhood} — "
            f"{fa_int(asset.area_sqm)} متر — {fa_int(listing.price)} تومان"
        )
    return (
        f"🌍 #{fa_int(listing.id)} {asset.city}، {asset.neighborhood} — "
        f"{fa_int(asset.area_sqm)} متر — {fa_int(listing.price)} تومان"
    )
