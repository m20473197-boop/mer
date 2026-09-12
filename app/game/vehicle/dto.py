"""Immutable DTOs for the dealership and owned-car screens."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.game.vehicle.catalog import (
    VEHICLE_MODEL_AVAILABLE,
    SHOTI_COMPATIBILITY_TAG,
)


@dataclass(frozen=True, slots=True)
class VehicleModelData:
    """A persisted predefined model, including future compatibility data."""

    model_id: int
    code: str
    name: str
    purchase_price: int
    availability_status: str
    future_compatibility: tuple[str, ...] = ()

    @property
    def is_available(self) -> bool:
        return self.availability_status == VEHICLE_MODEL_AVAILABLE

    @property
    def is_shoti_eligible(self) -> bool:
        return SHOTI_COMPATIBILITY_TAG in self.future_compatibility


@dataclass(frozen=True, slots=True)
class VehicleOwnershipData:
    """One real vehicle owned by one player."""

    ownership_id: int
    owner_player_id: int
    model: VehicleModelData
    purchase_price: int
    purchased_at: datetime
    status: str

    @property
    def is_owned(self) -> bool:
        return self.status == "owned"


@dataclass(frozen=True, slots=True)
class VehiclePurchaseResult:
    """The committed result of one atomic purchase."""

    ownership: VehicleOwnershipData
    wallet_balance_after: int
