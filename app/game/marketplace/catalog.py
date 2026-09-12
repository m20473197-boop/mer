"""The real asset types supported by ``🧱 دیوار ایران``."""

from __future__ import annotations

from dataclasses import dataclass

ASSET_TYPE_HOUSE: str = "house"
ASSET_TYPE_LAND: str = "land"
ASSET_TYPE_CAR: str = "car"
SUPPORTED_ASSET_TYPES: tuple[str, ...] = (
    ASSET_TYPE_HOUSE,
    ASSET_TYPE_LAND,
    ASSET_TYPE_CAR,
)

LISTING_STATUS_ACTIVE: str = "active"
LISTING_STATUS_SOLD: str = "sold"
LISTING_STATUS_CANCELLED: str = "cancelled"

CATEGORY_LABELS: dict[str, str] = {
    ASSET_TYPE_HOUSE: "🏠 خانه",
    ASSET_TYPE_LAND: "🌍 زمین",
    ASSET_TYPE_CAR: "🚗 ماشین",
}


@dataclass(frozen=True, slots=True)
class MarketplaceCategory:
    """A real, supported asset category shown by the player UI."""

    code: str
    label: str


SUPPORTED_CATEGORIES: tuple[MarketplaceCategory, ...] = tuple(
    MarketplaceCategory(code, CATEGORY_LABELS[code]) for code in SUPPORTED_ASSET_TYPES
)


def is_supported_asset_type(asset_type: str) -> bool:
    """Whether ``asset_type`` maps to an existing supported asset system."""
    return asset_type in SUPPORTED_ASSET_TYPES
