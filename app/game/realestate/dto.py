"""Data transfer objects for the Land / Construction / Renovation system."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.game.housing.dto import HouseData

# Project statuses
STATUS_IN_PROGRESS: str = "in_progress"
STATUS_COMPLETED: str = "completed"
STATUS_CANCELLED: str = "cancelled"


@dataclass(frozen=True, slots=True)
class LandData:
    """A land parcel with its unique ID and location quality."""

    id: int
    city: str
    neighborhood: str
    area_sqm: int
    location_quality: str
    owner_player_id: int | None
    built_house_id: int | None
    created_at: datetime
    updated_at: datetime
    price_override_per_mille: int | None = None


@dataclass(frozen=True, slots=True)
class LandMarketEntry:
    """One purchasable parcel with its live dynamic price."""

    land: LandData
    price: int            # current dynamic market price (Toman)
    price_per_sqm: int


@dataclass(frozen=True, slots=True)
class LandInfoData:
    """The «اطلاعات ملک» screen for one parcel."""

    land: LandData
    market_value: int
    price_per_sqm: int
    owner_name: str | None
    built_house: HouseData | None
    active_construction: "ConstructionProjectData | None"


@dataclass(frozen=True, slots=True)
class LandPurchaseResult:
    """Outcome of buying a parcel."""

    buyer_player_id: int
    land: LandData
    price: int
    balance_after: int


@dataclass(frozen=True, slots=True)
class ConstructionProjectData:
    """A construction project with live progress."""

    id: int
    land_id: int
    house_id: int | None
    owner_player_id: int
    status: str
    building_type_label: str
    floors: int
    area_sqm: int
    bedrooms: int
    bathrooms: int
    living_rooms: int
    kitchen_type: str
    quality: str
    parking: bool
    elevator: bool
    storage: bool
    cost_total: int
    started_at: datetime
    completes_at: datetime
    completed_at: datetime | None
    progress_percent: float
    seconds_remaining: int | None  # None once finished/cancelled
    land_label: str = ""


@dataclass(frozen=True, slots=True)
class LandWithStatus:
    """One owned parcel plus its live construction state."""

    land: LandData
    market_value: int
    active_construction: ConstructionProjectData | None


@dataclass(frozen=True, slots=True)
class PlayerLandsData:
    """The player's land assets («زمین‌های من»)."""

    player_id: int
    lands: tuple[LandWithStatus, ...]
    total_market_value: int


@dataclass(frozen=True, slots=True)
class ConstructionStartResult:
    """Outcome of starting a construction project."""

    project: ConstructionProjectData
    land: LandData
    cost: int
    balance_after: int


@dataclass(frozen=True, slots=True)
class ConstructionCancelResult:
    """Outcome of cancelling a construction project."""

    project_id: int
    refund: int
    balance_after: int


@dataclass(frozen=True, slots=True)
class RenovationProjectData:
    """A renovation project with live progress."""

    id: int
    house_id: int
    owner_player_id: int
    renovation_type: str
    title: str
    description: str
    cost: int
    status: str
    started_at: datetime
    completes_at: datetime
    completed_at: datetime | None
    progress_percent: float
    seconds_remaining: int | None
    house_label: str


@dataclass(frozen=True, slots=True)
class RenovationStartResult:
    """Outcome of starting a renovation."""

    project: RenovationProjectData
    house: HouseData
    cost: int
    balance_after: int
    value_before: int


@dataclass(frozen=True, slots=True)
class ProjectsStatusData:
    """The «وضعیت ساخت» screen payload."""

    constructions: tuple[ConstructionProjectData, ...]
    renovations: tuple[RenovationProjectData, ...]


@dataclass(frozen=True, slots=True)
class PropertyUpgradeData:
    """One recorded value-changing event on a property (audit trail)."""

    id: int
    property_type: str
    property_id: int
    player_id: int | None
    upgrade_kind: str
    description: str
    value_before: int | None
    value_after: int | None
    cost: int
    created_at: datetime
