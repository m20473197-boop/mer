"""Admin-panel data transfer objects (frozen, no I/O)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Generic, TypeVar

from app.game.housing.dto import HouseData
from app.game.realestate.dto import LandData

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Page(Generic[T]):
    """One page of an admin list."""

    items: tuple[T, ...]
    page: int
    per_page: int
    total: int
    total_pages: int

    @property
    def has_prev(self) -> bool:
        return self.page > 0

    @property
    def has_next(self) -> bool:
        return self.page + 1 < self.total_pages


def paginate(items: list[T], page: int, per_page: int) -> Page[T]:
    """Slice an in-memory list into a :class:`Page` (clamps the page)."""
    total = len(items)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    return Page(
        items=tuple(items[start : start + per_page]),
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
    )


@dataclass(frozen=True, slots=True)
class DashboardStats:
    """Everything the 📊 dashboard screen shows."""

    total_users: int
    active_users_24h: int
    banned_users: int
    total_money: int
    houses_count: int
    lands_count: int
    jobs_count: int
    active_sale_listings: int
    active_rent_listings: int
    active_contracts: int
    active_constructions: int
    active_renovations: int
    active_events: int
    market_factor: float
    db_dialect: str
    db_size_bytes: int | None
    db_ping_ms: float
    db_tables: int
    uptime_seconds: int
    python_version: str


@dataclass(frozen=True, slots=True)
class AdminPlayerSummary:
    """One row of the user list / search results."""

    player_id: int
    telegram_user_id: int
    username: str | None
    display_name: str
    level: int
    xp: int
    money: int
    is_banned: bool


@dataclass(frozen=True, slots=True)
class AdminPlayerDetail:
    """The full «view user profile» screen."""

    summary: AdminPlayerSummary
    houses_count: int
    lands_count: int
    job_name: str | None
    employer: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class UserTxEntry:
    """One normalized money-movement row for history screens."""

    kind: str  # sale_buy, sale_sell, house_tx, land_tx, rent
    label: str
    amount: int
    incoming: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class MarketAssetData:
    """One economy asset (currency / gold / crypto)."""

    id: int
    code: str
    name: str
    category: str
    price: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AssetPriceTickData:
    """One historical price point of an asset."""

    price: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class EconomicEventData:
    """One economic event / crisis."""

    id: int
    name: str
    description: str
    multiplier: float
    starts_at: datetime
    ends_at: datetime
    is_active: bool
    is_live: bool
    created_by: int


@dataclass(frozen=True, slots=True)
class EconomyOverview:
    """The 💰 economy screen: knobs + assets + live events."""

    base_market_conditions: float
    inflation_rate: float
    events_multiplier: float
    effective_factor: float
    assets: tuple[MarketAssetData, ...]
    live_events: tuple[EconomicEventData, ...]


@dataclass(frozen=True, slots=True)
class HouseAdminEntry:
    """One row of the admin house list."""

    id: int
    city: str
    neighborhood: str
    area_sqm: int
    owner_player_id: int | None
    owner_name: str | None
    market_value: int
    has_override: bool


@dataclass(frozen=True, slots=True)
class LandAdminEntry:
    """One row of the admin land list."""

    id: int
    city: str
    neighborhood: str
    area_sqm: int
    owner_player_id: int | None
    owner_name: str | None
    market_value: int
    built_house_id: int | None
    has_override: bool


@dataclass(frozen=True, slots=True)
class ListingAdminEntry:
    """One active listing for estate/trading management."""

    listing_id: int
    house_id: int
    house_label: str
    listing_type: str
    price: int
    deposit: int
    owner_player_id: int | None
    owner_name: str | None


@dataclass(frozen=True, slots=True)
class ContractAdminEntry:
    """One rental contract for estate management."""

    contract_id: int
    house_id: int
    house_label: str
    owner_name: str
    tenant_name: str
    monthly_rent: int
    deposit: int
    is_active: bool
    next_due_at: datetime


@dataclass(frozen=True, slots=True)
class JobAdminEntry:
    """One job for jobs management."""

    id: int
    name: str
    description: str
    hourly_salary: int
    employer: str
    cooldown: int
    required_level: int
    is_active: bool
    workers_count: int


@dataclass(frozen=True, slots=True)
class WorkerEntry:
    """One active worker (player × job)."""

    player_id: int
    telegram_user_id: int
    display_name: str
    job_id: int
    job_name: str
    total_earnings: int
    started_at: datetime


@dataclass(frozen=True, slots=True)
class SaleAdminEntry:
    """One completed sale for trading management."""

    sale_id: int
    house_id: int
    house_label: str
    seller_name: str | None
    buyer_name: str
    price: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SettingsOverview:
    """The ⚙️ bot-settings screen: every tunable in one place."""

    market_conditions: float
    inflation_rate: float
    purchase_xp_divisor: int
    purchase_xp_min: int
    purchase_xp_max: int
    construction_xp_divisor: int
    min_work_minutes: int
    jobs_enabled: bool
    housing_enabled: bool
    realestate_enabled: bool


@dataclass(frozen=True, slots=True)
class DBStats:
    """The 🗄 database-statistics screen."""

    dialect: str
    file_size_bytes: int | None
    tables: int
    total_rows: int
    counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class BackupInfo:
    """One database backup file."""

    filename: str
    size_bytes: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AdminAuditEntry:
    """One admin-action log row."""

    id: int
    admin_telegram_id: int
    action: str
    target_type: str | None
    target_id: int | None
    details: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class HouseDetailAdmin:
    """The full admin view of one house."""

    house: HouseData
    market_value: int
    owner_name: str | None
    active_sale_price: int | None
    active_rent: tuple[int, int] | None  # (deposit, monthly_rent)
    active_contract_id: int | None
    tenant_name: str | None


@dataclass(frozen=True, slots=True)
class LandDetailAdmin:
    """The full admin view of one land parcel."""

    land: LandData
    market_value: int
    price_per_sqm: int
    owner_name: str | None
