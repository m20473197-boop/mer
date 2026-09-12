"""The construction planning domain (pure math — no I/O).

A player builds on their own land by choosing a complete blueprint:

* building type — ``آپارتمانی`` (2–4 floors) or ``ویلایی`` (1 floor)
* total built area (capped by the land area × floors)
* number of bedrooms (bathrooms/living rooms derive from area & bedrooms)
* quality level — ``متوسط`` / ``خوب`` / ``عالی`` (the material grade:
  اقتصادی / استاندارد / لوکس)
* facilities — parking, elevator (apartments only), storage

Both the **cost** and the **duration** are computed dynamically from the
blueprint and the live market conditions (material prices):

    cost = area × cost_per_sqm(quality/materials)
         × floor_factor × market_factor
         + parking + storage + elevator×floors + modern-kitchen premium

    duration = DAYS_PER_100_SQM × area/100 × quality_time_factor
             × floor_time_factor    (clamped to [MIN_DAYS, MAX_DAYS])

Nothing is a fixed price — the future Economy system moves
``market.current_market_factor()`` and all construction costs follow.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.game.realestate.market import current_market_factor

# --- Building types (tokens are ASCII for compact callback data) -------------
TYPE_APARTMENT: str = "a"
TYPE_VILLA: str = "v"

BUILDING_TYPE_LABELS: dict[str, str] = {
    TYPE_APARTMENT: "آپارتمانی",
    TYPE_VILLA: "ویلایی",
}

VILLA_FLOORS: int = 1
APARTMENT_MIN_FLOORS: int = 2
APARTMENT_MAX_FLOORS: int = 4

# --- Quality / material grades ----------------------------------------------
QUALITY_TOKENS: dict[str, str] = {
    "m": "متوسط",
    "g": "خوب",
    "e": "عالی",
}
MATERIAL_LABELS: dict[str, str] = {
    "m": "مصالح اقتصادی",
    "g": "مصالح استاندارد",
    "e": "مصالح لوکس",
}

# Construction cost per square meter of built area, by material grade (Toman).
COST_PER_SQM: dict[str, int] = {
    "m": 12_000_000,
    "g": 15_000_000,
    "e": 19_000_000,
}

# Multi-floor structures cost more per sqm (structure, stairs, shafts).
FLOOR_COST_FACTOR_PER_EXTRA_FLOOR: float = 0.04

# Facility cost add-ons (Toman).
PARKING_COST: int = 150_000_000
STORAGE_COST: int = 60_000_000
ELEVATOR_COST_PER_FLOOR: int = 120_000_000
KITCHEN_MODERN_PREMIUM_PER_SQM: int = 1_200_000

# --- Duration ----------------------------------------------------------------
CONSTRUCTION_DAYS_PER_100_SQM: float = 2.0
QUALITY_TIME_FACTORS: dict[str, float] = {"m": 1.0, "g": 1.15, "e": 1.3}
FLOOR_TIME_FACTOR_PER_EXTRA_FLOOR: float = 0.10
CONSTRUCTION_MIN_DAYS: float = 1.0
CONSTRUCTION_MAX_DAYS: float = 21.0
SECONDS_PER_DAY: int = 86_400

# --- Validation bounds --------------------------------------------------------
MIN_AREA_PER_FLOOR: int = 35
MAX_BEDROOMS: int = 6
MAX_BATHROOMS: int = 3
MAX_LIVING_ROOMS: int = 2

# Round blueprint sizes to clean 5-sqm steps.
SIZE_ROUNDING_STEP: int = 5


@dataclass(frozen=True, slots=True)
class BuildingSpec:
    """A full blueprint chosen by the player for one construction project."""

    land_id: int
    building_type: str          # TYPE_APARTMENT | TYPE_VILLA
    floors: int
    area_sqm: int               # total built area across all floors
    bedrooms: int
    quality_token: str          # "m" | "g" | "e"
    parking: bool
    elevator: bool
    storage: bool

    @property
    def building_type_label(self) -> str:
        return BUILDING_TYPE_LABELS[self.building_type]

    @property
    def quality(self) -> str:
        return QUALITY_TOKENS[self.quality_token]

    @property
    def kitchen_type(self) -> str:
        """Excellent builds ship with a modern kitchen, others standard."""
        return "مدرن" if self.quality_token == "e" else "معمولی"

    @property
    def footprint_sqm(self) -> int:
        """Average ground footprint per floor."""
        return -(-self.area_sqm // max(1, self.floors))  # ceil division


def bedroom_max(area_sqm: int) -> int:
    """Most bedrooms a blueprint of this total area can sensibly have."""
    return max(1, min(MAX_BEDROOMS, area_sqm // 35))


def derived_rooms(area_sqm: int, bedrooms: int) -> tuple[int, int]:
    """(bathrooms, living_rooms) implied by the area and bedroom count."""
    bathrooms = 1 if bedrooms <= 2 else 2
    if area_sqm >= 180:
        bathrooms = min(MAX_BATHROOMS, bathrooms + 1)
    living_rooms = 2 if area_sqm >= 150 else 1
    return bathrooms, living_rooms


def size_presets(land_area_sqm: int, floors: int) -> tuple[int, ...]:
    """Total-built-area choices for a land, as clean 5-sqm steps."""
    max_total = land_area_sqm * floors
    presets = {
        max(35, (max_total * percent // 100 // SIZE_ROUNDING_STEP) * SIZE_ROUNDING_STEP)
        for percent in (40, 60, 80, 100)
    }
    return tuple(sorted(presets))


def validate_spec(spec: BuildingSpec, land_area_sqm: int) -> None:
    """Validate a blueprint against the land it will be built on.

    Raises:
        ValueError: If any part of the blueprint is impossible.
    """
    if spec.building_type == TYPE_VILLA:
        if spec.floors != VILLA_FLOORS:
            raise ValueError("villa blueprints have exactly one floor")
        if spec.elevator:
            raise ValueError("villas cannot have an elevator")
    elif spec.building_type == TYPE_APARTMENT:
        if not APARTMENT_MIN_FLOORS <= spec.floors <= APARTMENT_MAX_FLOORS:
            raise ValueError(
                f"apartment floors must be {APARTMENT_MIN_FLOORS}..{APARTMENT_MAX_FLOORS}"
            )
    else:
        raise ValueError(f"unknown building type: {spec.building_type!r}")

    max_total = land_area_sqm * spec.floors
    if not MIN_AREA_PER_FLOOR <= spec.area_sqm <= max_total:
        raise ValueError(f"area must be within [35, {max_total}] sqm")
    if spec.footprint_sqm < MIN_AREA_PER_FLOOR:
        raise ValueError(
            f"each floor needs at least {MIN_AREA_PER_FLOOR} sqm of footprint"
        )
    if not 1 <= spec.bedrooms <= bedroom_max(spec.area_sqm):
        raise ValueError(f"bedrooms must be within [1, {bedroom_max(spec.area_sqm)}]")
    if spec.quality_token not in QUALITY_TOKENS:
        raise ValueError(f"unknown quality token: {spec.quality_token!r}")


def construction_cost(
    spec: BuildingSpec, *, market_factor: float | None = None
) -> int:
    """Total construction cost in Toman (exact integer).

    Depends on size, material grade (quality), floor count, facilities,
    kitchen grade and the live material-market factor.
    """
    factor = market_factor if market_factor is not None else current_market_factor()
    floor_factor = 1.0 + FLOOR_COST_FACTOR_PER_EXTRA_FLOOR * (spec.floors - 1)

    cost = (
        spec.area_sqm
        * COST_PER_SQM[spec.quality_token]
        * floor_factor
        * factor
    )
    if spec.parking:
        cost += PARKING_COST * factor
    if spec.storage:
        cost += STORAGE_COST * factor
    if spec.elevator:
        cost += ELEVATOR_COST_PER_FLOOR * spec.floors * factor
    if spec.kitchen_type == "مدرن":
        cost += spec.area_sqm * KITCHEN_MODERN_PREMIUM_PER_SQM * factor

    step = 1_000_000
    return max(step, int(cost // step) * step)


def construction_duration_seconds(spec: BuildingSpec) -> int:
    """How long the construction takes, in seconds."""
    days = (
        CONSTRUCTION_DAYS_PER_100_SQM
        * (spec.area_sqm / 100.0)
        * QUALITY_TIME_FACTORS[spec.quality_token]
        * (1.0 + FLOOR_TIME_FACTOR_PER_EXTRA_FLOOR * (spec.floors - 1))
    )
    days = min(CONSTRUCTION_MAX_DAYS, max(CONSTRUCTION_MIN_DAYS, days))
    return int(days * SECONDS_PER_DAY)
