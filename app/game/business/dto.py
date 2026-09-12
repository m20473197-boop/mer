"""Data-transfer objects for the Business System."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class BusinessDefinitionData:
    """A predefined business shown before the player buys it."""

    key: str
    name: str
    startup_cost: int
    min_daily_income: int
    max_daily_income: int
    is_available: bool

    @property
    def status(self) -> str:
        return "فعال" if self.is_available else "فعلاً بسته"


@dataclass(frozen=True, slots=True)
class BusinessData:
    """An owned business and its persisted balance."""

    id: int
    owner_player_id: int
    business_type: str
    name: str
    startup_cost: int
    min_daily_income: int
    max_daily_income: int
    is_active: bool
    balance: int
    latest_daily_income: int
    last_income_date: date | None
    started_at: datetime
    created_at: datetime
    updated_at: datetime

    @property
    def latest_income(self) -> int:
        """Compatibility-friendly short name for the latest daily amount."""
        return self.latest_daily_income


@dataclass(frozen=True, slots=True)
class BusinessStartResult:
    """Outcome of paying for and starting a predefined business."""

    business: BusinessData
    startup_cost: int
    wallet_balance_after: int


@dataclass(frozen=True, slots=True)
class BusinessIncomeResult:
    """Outcome of trying to generate one day's income."""

    business: BusinessData
    generated: bool
    amount_added: int
    income_date: date

    @property
    def already_generated(self) -> bool:
        return not self.generated
