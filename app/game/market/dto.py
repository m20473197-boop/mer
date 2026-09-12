"""Data-transfer objects for the player-facing Iranian market."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class IranMarketAssetData:
    """One stored market quote and its latest movement."""

    id: int
    code: str
    display_name: str
    category: str
    current_price: int | None
    previous_price: int | None
    base_value: int | None
    last_successful_update: datetime | None
    last_attempted_update: datetime | None
    is_active: bool
    unit_label: str
    change_amount: int | None
    direction: str | None
    created_at: datetime
    updated_at: datetime

    @property
    def price(self) -> int | None:
        """Short alias for player-facing callers."""
        return self.current_price


@dataclass(frozen=True, slots=True)
class IranMarketHistoryData:
    """One immutable historical market update."""

    id: int
    asset_code: str
    previous_price: int | None
    new_price: int
    change_amount: int
    direction: str
    source: str
    update_type: str
    cycle_id: str
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class IranMarketSnapshotData:
    """The same stored snapshot rendered to every player."""

    assets: tuple[IranMarketAssetData, ...]
    last_successful_update: datetime | None

    def by_code(self, code: str) -> IranMarketAssetData | None:
        return next((asset for asset in self.assets if asset.code == code), None)


@dataclass(frozen=True, slots=True)
class MarketUpdateResult:
    """Result of one scheduler/initialization attempt."""

    attempted: bool
    successful: bool
    cycle_id: str | None
    updated_assets: tuple[str, ...]
    attempted_at: datetime
    completed_at: datetime | None
    error: str | None = None

    @property
    def skipped(self) -> bool:
        return not self.attempted
