"""Immutable DTOs for the player-facing Divar marketplace."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - imports are only for type checkers
    from app.game.housing.dto import HouseData
    from app.game.realestate.dto import LandData

from app.game.marketplace.catalog import LISTING_STATUS_ACTIVE


@dataclass(frozen=True, slots=True)
class MarketplaceSearchCriteria:
    """All search/filter values used by one paginated query."""

    asset_type: str | None = None
    city: str | None = None
    neighborhood: str | None = None
    min_price: int | None = None
    max_price: int | None = None
    min_area_sqm: int | None = None
    max_area_sqm: int | None = None
    bedrooms: int | None = None
    construction_year: int | None = None
    quality: str | None = None
    text_terms: tuple[str, ...] = ()

    def with_page_independent_filters(self, **changes: object) -> "MarketplaceSearchCriteria":
        """Return a copy while keeping the immutable criteria contract."""
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class MarketplaceSearchResult:
    """One database-paginated active-listing page."""

    listings: tuple["MarketplaceListingData", ...]
    page: int
    page_size: int
    total: int

    @property
    def has_previous(self) -> bool:
        return self.page > 0

    @property
    def has_next(self) -> bool:
        return (self.page + 1) * self.page_size < self.total


@dataclass(frozen=True, slots=True)
class MarketplaceListingData:
    """A listing plus the real underlying house or land DTO."""

    id: int
    seller_player_id: int
    seller_name: str
    asset_type: str
    asset_id: int
    price: int
    status: str
    created_at: datetime
    sold_at: datetime | None
    buyer_player_id: int | None
    house: "HouseData | None" = None
    land: "LandData | None" = None

    @property
    def is_active(self) -> bool:
        return self.status == LISTING_STATUS_ACTIVE

    @property
    def asset(self) -> "HouseData | LandData | None":
        return self.house if self.house is not None else self.land

    @property
    def asset_label(self) -> str:
        if self.house is not None:
            return f"خانه #{self.house.id}"
        if self.land is not None:
            return f"زمین #{self.land.id}"
        return f"دارایی #{self.asset_id}"


@dataclass(frozen=True, slots=True)
class MarketplaceOwnedAssetData:
    """One actual asset eligible for a new Divar listing."""

    asset_type: str
    asset_id: int
    label: str
    location: str
    area_sqm: int


@dataclass(frozen=True, slots=True)
class MarketplaceCreateResult:
    """Outcome of creating an active listing."""

    listing: MarketplaceListingData


@dataclass(frozen=True, slots=True)
class MarketplaceCancelResult:
    """Outcome of cancelling an unsold listing."""

    listing_id: int
    asset_type: str
    asset_id: int


@dataclass(frozen=True, slots=True)
class MarketplacePurchaseResult:
    """Outcome of one atomic purchase."""

    listing: MarketplaceListingData
    buyer_player_id: int
    seller_player_id: int
    price: int
    buyer_balance_after: int


@dataclass(frozen=True, slots=True)
class MarketplaceFilterState:
    """UI-facing search state stored server-side, never in callback payloads."""

    criteria: MarketplaceSearchCriteria = MarketplaceSearchCriteria()
    search_query: str = ""

    def with_criteria(self, criteria: MarketplaceSearchCriteria) -> "MarketplaceFilterState":
        return replace(self, criteria=criteria)
