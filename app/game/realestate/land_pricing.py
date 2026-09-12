"""The dynamic land pricing engine (pure math — no I/O).

Like house prices, land prices are **never fixed**. Every valuation is
computed from the parcel's own attributes and the shared market catalog:

    price = base_house_price_per_sqm(city) × LAND_VALUE_RATIO
          × neighborhood_multiplier
          × area
          × size_factor(area)          ← wholesale discount for big parcels
          × market_factor              ← economy knob (inflation/boom hook)
          × deterministic jitter       ← ±4%, stable per land id

Land trades at a fraction (``LAND_VALUE_RATIO``) of the built apartment price
per square meter of the same city — the classic Iranian زمین vs ساختمان
relationship — and reacts to every future market-data refresh of the housing
catalog automatically.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.game.housing.catalog import (
    get_base_price_per_sqm,
    get_neighborhood_multiplier,
)
from app.game.realestate.market import current_market_factor

# Land value as a share of the built apartment price per square meter.
LAND_VALUE_RATIO: float = 0.45

# Large parcels are slightly cheaper per square meter (wholesale effect).
SIZE_DISCOUNT_THRESHOLD_SQM: int = 500
SIZE_DISCOUNT_LARGE: float = 0.92
SIZE_DISCOUNT_HUGE_THRESHOLD_SQM: int = 1000
SIZE_DISCOUNT_HUGE: float = 0.85

# Deterministic per-land jitter bounds (stable price per land, variety across
# parcels).
JITTER_MAX_RELATIVE: float = 0.04

# Land prices land on clean million-Toman steps.
PRICE_ROUNDING_STEP: int = 1_000_000

# Location quality labels derived from the neighborhood multiplier.
QUALITY_LUXURY: str = "لوکس"
QUALITY_EXCELLENT: str = "عالی"
QUALITY_GOOD: str = "خوب"
QUALITY_AVERAGE: str = "متوسط"


@dataclass(frozen=True, slots=True)
class LandPricingInput:
    """Everything the land pricing engine needs to know about one parcel."""

    land_id: int
    city: str
    neighborhood: str
    area_sqm: int


def location_quality_label(neighborhood_multiplier: float) -> str:
    """A human label for how prime the location is (display only)."""
    if neighborhood_multiplier >= 1.5:
        return QUALITY_LUXURY
    if neighborhood_multiplier >= 1.15:
        return QUALITY_EXCELLENT
    if neighborhood_multiplier >= 0.85:
        return QUALITY_GOOD
    return QUALITY_AVERAGE


def quality_label_for(city: str, neighborhood: str) -> str | None:
    """Location quality label for a (city, neighborhood) pair, if known."""
    multiplier = get_neighborhood_multiplier(city, neighborhood)
    if multiplier is None:
        return None
    return location_quality_label(multiplier)


def _size_factor(area_sqm: int) -> float:
    if area_sqm > SIZE_DISCOUNT_HUGE_THRESHOLD_SQM:
        return SIZE_DISCOUNT_HUGE
    if area_sqm > SIZE_DISCOUNT_THRESHOLD_SQM:
        return SIZE_DISCOUNT_LARGE
    return 1.0


def _deterministic_jitter(land_id: int) -> float:
    """A stable pseudo-random factor in ``[1 - JITTER_MAX, 1 + JITTER_MAX]``."""
    digest = hashlib.sha256(f"land-price:{land_id}".encode()).digest()
    raw = int.from_bytes(digest[:8], "big") / 2**64  # in [0, 1)
    span = 2 * JITTER_MAX_RELATIVE
    return 1.0 - JITTER_MAX_RELATIVE + raw * span


def estimate_land_price(
    land: LandPricingInput, *, market_factor: float | None = None
) -> int:
    """Full dynamic market value of a land parcel (exact integer Toman).

    Args:
        land: The parcel attributes.
        market_factor: Explicit economy multiplier; ``None`` uses the live
            market conditions (``market.current_market_factor``).

    Raises:
        ValueError: If the city or neighborhood is unknown or the area is
            implausible.
    """
    base_per_sqm = get_base_price_per_sqm(land.city)
    if base_per_sqm is None:
        raise ValueError(f"unknown city: {land.city!r}")
    neighborhood_multiplier = get_neighborhood_multiplier(land.city, land.neighborhood)
    if neighborhood_multiplier is None:
        raise ValueError(
            f"unknown neighborhood {land.neighborhood!r} in {land.city!r}"
        )
    if land.area_sqm <= 0:
        raise ValueError("area_sqm must be positive")

    factor = market_factor if market_factor is not None else current_market_factor()
    price = (
        base_per_sqm
        * LAND_VALUE_RATIO
        * neighborhood_multiplier
        * land.area_sqm
        * _size_factor(land.area_sqm)
        * factor
        * _deterministic_jitter(land.land_id)
    )
    return max(PRICE_ROUNDING_STEP, int(price // PRICE_ROUNDING_STEP) * PRICE_ROUNDING_STEP)


def estimate_land_price_per_sqm(
    land: LandPricingInput, *, market_factor: float | None = None
) -> int:
    """Current price per square meter of one parcel (rounded to 10k steps)."""
    total = estimate_land_price(land, market_factor=market_factor)
    return max(10_000, (total // land.area_sqm // 10_000) * 10_000)
