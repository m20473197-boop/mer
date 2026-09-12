"""Data transfer objects for the Housing system.

DTOs keep the Telegram layer decoupled from ORM models — handlers never
touch database objects directly (same contract as the player/job DTOs).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class HouseData:
    """A house with its full, realistic property list."""

    id: int
    city: str
    neighborhood: str
    area_sqm: int
    bedrooms: int
    living_rooms: int
    bathrooms: int
    kitchen_type: str
    construction_year: int          # سال ساخت (Solar Hijri, e.g. 1395)
    parking: bool
    elevator: bool
    storage: bool
    quality: str
    owner_player_id: int | None
    created_at: datetime
    updated_at: datetime
    price_override_per_mille: int | None = None


@dataclass(frozen=True, slots=True)
class HouseMarketEntry:
    """One purchasable house — either from the system market or a player."""

    house: HouseData
    price: int                  # current asking price (Toman)
    market_value: int           # dynamic estimated value (Toman)
    seller_player_id: int | None  # None → system market (bank/developer)
    seller_name: str | None       # display name, None for the system market


@dataclass(frozen=True, slots=True)
class HouseRentalEntry:
    """One rentable house offered by another player."""

    house: HouseData
    monthly_rent: int
    deposit: int
    owner_player_id: int
    owner_name: str


@dataclass(frozen=True, slots=True)
class HouseInfoData:
    """Full information screen for one house."""

    house: HouseData
    market_value: int
    estimated_rent: int
    owner_name: str | None            # None → still on the system market
    active_sale_price: int | None     # asking price when listed for sale
    active_rent: tuple[int, int] | None  # (monthly_rent, deposit) when listed
    tenant_name: str | None           # tenant display name when rented out
    tenanted_by_me: bool
    contract_id: int | None = None    # active rental contract (tenant actions)


@dataclass(frozen=True, slots=True)
class HouseListingData:
    """A sale or rent listing."""

    id: int
    house_id: int
    owner_player_id: int | None
    listing_type: str          # "sale" | "rent"
    price: int                 # sale price or monthly rent
    deposit: int               # rent listings only
    status: str                # "active" | "closed"
    created_at: datetime
    closed_at: datetime | None


@dataclass(frozen=True, slots=True)
class SaleOptions:
    """Suggested sale prices (button presets) around the dynamic value."""

    house_id: int
    market_value: int
    price_options: tuple[tuple[int, int], ...]  # (per-mille, price)


@dataclass(frozen=True, slots=True)
class RentOptions:
    """Suggested (deposit, rent) presets for renting a house out."""

    house_id: int
    market_value: int
    options: tuple[tuple[int, int, int], ...]  # (deposit%, deposit, monthly rent)


@dataclass(frozen=True, slots=True)
class PurchaseResult:
    """Outcome of buying a house (market or player)."""

    buyer_player_id: int
    house: HouseData
    price: int
    seller_player_id: int | None  # None → system market
    balance_after: int
    xp_granted: int


@dataclass(frozen=True, slots=True)
class ListForSaleResult:
    """Outcome of putting a house up for sale."""

    house: HouseData
    price: int
    market_value: int


@dataclass(frozen=True, slots=True)
class ListForRentResult:
    """Outcome of putting a house up for rent."""

    house: HouseData
    monthly_rent: int
    deposit: int
    market_value: int


@dataclass(frozen=True, slots=True)
class RentalContractData:
    """A rental contract between an owner and a tenant."""

    id: int
    house_id: int
    owner_player_id: int
    tenant_player_id: int
    monthly_rent: int
    deposit: int
    started_at: datetime
    next_due_at: datetime
    is_active: bool
    ended_at: datetime | None
    created_at: datetime
    # Joined display fields
    house_label: str = ""
    owner_name: str = ""
    tenant_name: str = ""


@dataclass(frozen=True, slots=True)
class RentPaymentResult:
    """Outcome of paying one month of rent."""

    contract_id: int
    house_id: int
    amount: int
    next_due_at: datetime
    tenant_balance_after: int
    owner_balance_after: int


@dataclass(frozen=True, slots=True)
class EndContractResult:
    """Outcome of ending a rental contract."""

    contract_id: int
    house_id: int
    ended_by_player_id: int
    tenant_player_id: int
    owner_player_id: int


@dataclass(frozen=True, slots=True)
class PlayerAssetsData:
    """The housing assets of a player (owned houses as assets)."""

    player_id: int
    houses: tuple[HouseData, ...]
    total_market_value: int
    active_sale_listings: tuple[HouseListingData, ...]
    active_rent_listings: tuple[HouseListingData, ...]
    rented_out_contracts: tuple[RentalContractData, ...]


@dataclass(frozen=True, slots=True)
class HouseSaleRecordData:
    """One completed sale (audit trail)."""

    id: int
    house_id: int
    seller_player_id: int | None
    buyer_player_id: int
    price: int
    created_at: datetime
