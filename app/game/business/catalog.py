"""The predefined business catalog.

This is the single place to tune the player-facing business list. Businesses
are identified by a stable ASCII ``key`` in callbacks and database rows; the
Persian name and all financial values are configuration, not user input.

A business is never created from Telegram input. To add or rebalance one,
change this catalog and deploy the code. Existing owned businesses keep the
snapshot of the terms they started with, while new purchases use the current
catalog values.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BusinessDefinition:
    """One predefined business that players may or may not be able to start."""

    key: str
    name: str
    startup_cost: int
    min_daily_income: int
    max_daily_income: int
    is_available: bool = True

    @property
    def status(self) -> str:
        """Short Persian status used by the player-facing catalog screen."""
        return "فعال" if self.is_available else "فعلاً بسته"

    @property
    def daily_income_range(self) -> tuple[int, int]:
        return self.min_daily_income, self.max_daily_income


# Game-balanced values: the expected payback period is meaningful, while the
# range stays variable. These are exact Toman amounts and are intentionally
# not arbitrary placeholder numbers. Toggle ``is_available`` here when a
# predefined business needs to be temporarily closed.
BUSINESS_CATALOG: tuple[BusinessDefinition, ...] = (
    BusinessDefinition(
        key="local_kiosk",
        name="دکه محلی",
        startup_cost=3_500_000,
        min_daily_income=100_000,
        max_daily_income=220_000,
    ),
    BusinessDefinition(
        key="small_fast_food",
        name="فست‌فود کوچک",
        startup_cost=8_500_000,
        min_daily_income=260_000,
        max_daily_income=520_000,
    ),
    BusinessDefinition(
        key="clothing_store",
        name="فروشگاه پوشاک",
        startup_cost=18_500_000,
        min_daily_income=500_000,
        max_daily_income=1_000_000,
    ),
    BusinessDefinition(
        key="mobile_repair",
        name="تعمیرگاه موبایل",
        startup_cost=27_500_000,
        min_daily_income=750_000,
        max_daily_income=1_600_000,
    ),
    BusinessDefinition(
        key="local_cafe",
        name="کافه محلی",
        startup_cost=42_000_000,
        min_daily_income=1_200_000,
        max_daily_income=2_700_000,
    ),
)

_BY_KEY: dict[str, BusinessDefinition] = {item.key: item for item in BUSINESS_CATALOG}


def list_business_definitions() -> tuple[BusinessDefinition, ...]:
    """Return the complete predefined catalog in its configured order."""
    return BUSINESS_CATALOG


def get_business_definition(key: str) -> BusinessDefinition | None:
    """Return a configured business, or ``None`` for an invalid type."""
    return _BY_KEY.get(key)
