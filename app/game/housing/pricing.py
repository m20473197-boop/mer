"""The dynamic house pricing engine (pure math — no I/O).

Prices are **never fixed**: every price is computed from the house's own
attributes and the market catalog each time it is needed:

    price = base_per_sqm(city)
          × neighborhood_multiplier
          × area                          ← raw volume
          × size_factor(area)             ← slight discount for very large homes
          × age_factor(construction_year) ← depreciation with a floor
          × facility_factor               ← parking / elevator / storage / rooms
          × kitchen_factor(type)
          × quality_factor(level)
          × market_factor                 ← live-market override (default 1.0)
          × deterministic jitter          ← ±3% seeded by house id

The building's age is never stored — it is derived internally from the
construction year (سال ساخت):

    building_age = current_iranian_year() − construction_year

The result is rounded down to a clean 100,000-Toman step.

Because the whole computation is a pure function of (house attributes ×
catalog data), connecting a live feed of the real Iranian housing market
later only means updating ``app/game/housing/catalog.py`` (or passing a
``market_factor``) — no other layer changes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.game.housing.catalog import (
    get_base_price_per_sqm,
    get_neighborhood_multiplier,
)
from app.game.housing.construction_year import (
    age_from_construction_year,
    validate_construction_year,
)

# --- Tunable factors ---------------------------------------------------------

# Very large homes are slightly cheaper per square meter.
SIZE_DISCOUNT_THRESHOLD_SQM: int = 100
SIZE_DISCOUNT_LARGE: float = 0.95
SIZE_DISCOUNT_HUGE_THRESHOLD_SQM: int = 200
SIZE_DISCOUNT_HUGE: float = 0.90

# Building age depreciation: 1.2% per year, floored at 45% of new value.
AGE_DEPRECIATION_PER_YEAR: float = 0.012
AGE_FACTOR_FLOOR: float = 0.45

# Facility bonuses (multiplicative additive parts, in percent).
PARKING_BONUS: float = 0.05
ELEVATOR_BONUS: float = 0.06
STORAGE_BONUS: float = 0.03
EXTRA_BATHROOM_BONUS: float = 0.03   # per bathroom beyond the first
LIVING_ROOM_BONUS: float = 0.02      # per living room
BEDROOM_BONUS: float = 0.02          # per bedroom beyond the first (small)

# Kitchen types (Persian) → multiplier.
KITCHEN_FACTORS: dict[str, float] = {
    "مدرن": 1.05,
    "معمولی": 1.00,
    "قدیمی": 0.93,
}
DEFAULT_KITCHEN_FACTOR: float = 1.00

# Quality levels (Persian) → multiplier.
QUALITY_FACTORS: dict[str, float] = {
    "عالی": 1.18,
    "خوب": 1.00,
    "متوسط": 0.88,
    "ضعیف": 0.75,
}
DEFAULT_QUALITY_FACTOR: float = 1.00

# Deterministic per-house jitter bounds (so identical houses still differ a
# little, while every house keeps one stable price).
JITTER_MAX_RELATIVE: float = 0.03

# Price rounding: all prices land on a clean step.
PRICE_ROUNDING_STEP: int = 100_000

# Monthly rent yield applied to the property value (Iranian-style rent with
# optional deposit; a higher deposit lowers the monthly rent).
RENT_YIELD_WITHOUT_DEPOSIT: float = 0.006      # 0.6% of value per month
RENT_YIELD_DISCOUNT_PER_DEPOSIT_PERCENT: float = 0.0001  # per 1% deposit
RENT_ROUNDING_STEP: int = 50_000


@dataclass(frozen=True, slots=True)
class HousePricingInput:
    """Everything the pricing engine needs to know about one house."""

    house_id: int
    city: str
    neighborhood: str
    area_sqm: int
    bedrooms: int
    living_rooms: int
    bathrooms: int
    kitchen_type: str
    construction_year: int     # سال ساخت (Solar Hijri, e.g. 1395)
    parking: bool
    elevator: bool
    storage: bool
    quality: str


def _size_factor(area_sqm: int) -> float:
    if area_sqm > SIZE_DISCOUNT_HUGE_THRESHOLD_SQM:
        return SIZE_DISCOUNT_HUGE
    if area_sqm > SIZE_DISCOUNT_THRESHOLD_SQM:
        return SIZE_DISCOUNT_LARGE
    return 1.0


def _age_factor(construction_year: int) -> float:
    """Depreciation derived from the construction year (not a stored age)."""
    building_age = age_from_construction_year(construction_year)
    if building_age <= 0:
        return 1.0
    factor = 1.0 - building_age * AGE_DEPRECIATION_PER_YEAR
    return max(AGE_FACTOR_FLOOR, factor)


def _facility_factor(input_: HousePricingInput) -> float:
    factor = 1.0
    if input_.parking:
        factor += PARKING_BONUS
    if input_.elevator:
        factor += ELEVATOR_BONUS
    if input_.storage:
        factor += STORAGE_BONUS
    factor += max(0, input_.bathrooms - 1) * EXTRA_BATHROOM_BONUS
    factor += max(0, input_.living_rooms) * LIVING_ROOM_BONUS
    factor += max(0, input_.bedrooms - 1) * BEDROOM_BONUS
    return factor


def _kitchen_factor(kitchen_type: str) -> float:
    return KITCHEN_FACTORS.get(kitchen_type, DEFAULT_KITCHEN_FACTOR)


def _quality_factor(quality: str) -> float:
    return QUALITY_FACTORS.get(quality, DEFAULT_QUALITY_FACTOR)


def _deterministic_jitter(house_id: int) -> float:
    """A stable pseudo-random factor in ``[1 - JITTER_MAX, 1 + JITTER_MAX]``.

    Hashing the house id keeps the price *stable* for a given house (it does
    not change between views) while still varying between houses.
    """
    digest = hashlib.sha256(f"house-price:{house_id}".encode()).digest()
    raw = int.from_bytes(digest[:8], "big") / 2**64  # in [0, 1)
    span = 2 * JITTER_MAX_RELATIVE
    return 1.0 - JITTER_MAX_RELATIVE + raw * span


def _round_to_step(amount: float, step: int) -> int:
    """Round down to the nearest ``step`` (exact integer Toman)."""
    return max(0, int(amount // step) * step)


def estimate_house_price(
    house: HousePricingInput, *, market_factor: float = 1.0
) -> int:
    """Full dynamic market value of a house in Toman (exact integer).

    Args:
        house: The house attributes.
        market_factor: Optional live-market multiplier (e.g. inflation index
            from a future real-data connection). Defaults to a flat market.

    Raises:
        ValueError: If the city or neighborhood is not in the catalog, the
            construction year is implausible, or an attribute is broken
            (non-positive area, ...).
    """
    base_per_sqm = get_base_price_per_sqm(house.city)
    if base_per_sqm is None:
        raise ValueError(f"unknown city: {house.city!r}")
    neighborhood_multiplier = get_neighborhood_multiplier(
        house.city, house.neighborhood
    )
    if neighborhood_multiplier is None:
        raise ValueError(
            f"unknown neighborhood {house.neighborhood!r} in {house.city!r}"
        )
    if house.area_sqm <= 0:
        raise ValueError("area_sqm must be positive")
    validate_construction_year(house.construction_year)

    price = (
        base_per_sqm
        * neighborhood_multiplier
        * house.area_sqm
        * _size_factor(house.area_sqm)
        * _age_factor(house.construction_year)
        * _facility_factor(house)
        * _kitchen_factor(house.kitchen_type)
        * _quality_factor(house.quality)
        * market_factor
        * _deterministic_jitter(house.house_id)
    )
    return max(PRICE_ROUNDING_STEP, _round_to_step(price, PRICE_ROUNDING_STEP))


def suggested_deposit_and_rent(
    house_value: int, *, deposit_percent: int
) -> tuple[int, int]:
    """Iranian-style (deposit, monthly rent) pair for one house.

    ``deposit_percent`` is the share of the house value asked as refundable
    deposit (رهن); each point of deposit lowers the monthly rent, which is
    how real Iranian rentals balance رهن against اجاره.
    """
    if deposit_percent < 0:
        deposit_percent = 0
    deposit = _round_to_step(
        house_value * deposit_percent / 100.0, PRICE_ROUNDING_STEP
    )
    monthly_rate = RENT_YIELD_WITHOUT_DEPOSIT - (
        deposit_percent * RENT_YIELD_DISCOUNT_PER_DEPOSIT_PERCENT
    )
    monthly_rate = max(0.001, monthly_rate)
    monthly_rent = _round_to_step(house_value * monthly_rate, RENT_ROUNDING_STEP)
    return deposit, monthly_rent


def estimate_monthly_rent(
    house: HousePricingInput, *, market_factor: float = 1.0
) -> int:
    """Suggested monthly rent (no deposit) — derived from the dynamic price."""
    value = estimate_house_price(house, market_factor=market_factor)
    _, rent = suggested_deposit_and_rent(value, deposit_percent=0)
    return rent
