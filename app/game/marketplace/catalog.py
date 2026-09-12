"""The asset types explicitly supported by ``🧱 دیوار ایران``.

There is deliberately no vehicle or generic/fake category: this project
currently has player-owned houses and land, so those are the only assets the
marketplace exposes.
"""

from __future__ import annotations

from dataclasses import dataclass

ASSET_TYPE_HOUSE: str = "house"
ASSET_TYPE_LAND: str = "land"
SUPPORTED_ASSET_TYPES: tuple[str, ...] = (ASSET_TYPE_HOUSE, ASSET_TYPE_LAND)

LISTING_STATUS_ACTIVE: str = "active"
LISTING_STATUS_SOLD: str = "sold"
LISTING_STATUS_CANCELLED: str = "cancelled"

CATEGORY_LABELS: dict[str, str] = {
    ASSET_TYPE_HOUSE: "🏠 خانه",
    ASSET_TYPE_LAND: "🌍 زمین",
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
