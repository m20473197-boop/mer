"""Deterministic seeding of the initial system-market houses.

The houses the bank/developer market starts with. Everything is generated
from a fixed seed so every installation gets the same starter catalog and
tests stay deterministic. Seeded houses are ownerless — they sit on the
system market until a player buys them.

Houses carry a **construction year** (سال ساخت, Solar Hijri); the age used
for the quality roll is derived from it internally.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from app.core import constants
from app.game.housing.catalog import CITY_NEIGHBORHOODS, list_cities
from app.game.housing.construction_year import current_iranian_year

# Areas (sqm) the starter market cycles through.
_AREAS: tuple[int, ...] = (45, 55, 65, 75, 85, 100, 120, 140, 165, 200, 240)

_KITCHEN_TYPES: tuple[str, ...] = ("مدرن", "معمولی", "قدیمی")

# Big cities where mid/high-rise (and thus elevators) are the norm.
_HIGH_RISE_CITIES: frozenset[str] = frozenset({"تهران", "کرج", "مشهد", "اصفهان"})


@dataclass(frozen=True, slots=True)
class HouseSeedSpec:
    """One house specification for the starter market."""

    city: str
    neighborhood: str
    area_sqm: int
    bedrooms: int
    living_rooms: int
    bathrooms: int
    kitchen_type: str
    construction_year: int
    parking: bool
    elevator: bool
    storage: bool
    quality: str


def _quality_for_age(rng: random.Random, age: int) -> str:
    if age <= 3:
        return rng.choice(("عالی", "عالی", "خوب"))
    if age <= 10:
        return rng.choice(("عالی", "خوب", "خوب", "متوسط"))
    if age <= 20:
        return rng.choice(("خوب", "متوسط", "متوسط"))
    return rng.choice(("متوسط", "ضعیف"))


def build_seed_specs(count: int | None = None) -> list[HouseSeedSpec]:
    """Build the deterministic starter-market house list."""
    total = count if count is not None else constants.HOUSING_SEED_COUNT
    cities = list_cities()
    current_year = current_iranian_year()
    age_choices = (0, 1, 2, 3, 5, 8, 12, 15, 20, 25, 30)
    specs: list[HouseSeedSpec] = []

    for index in range(total):
        rng = random.Random(1404 + index)  # stable per-house dice
        city = cities[index % len(cities)]
        neighborhoods = list(CITY_NEIGHBORHOODS.get(city, {}).keys())
        neighborhood = neighborhoods[index % len(neighborhoods)]

        area = _AREAS[index % len(_AREAS)]
        bedrooms = min(4, max(1, area // 55))
        living_rooms = 1 if area < 150 else 2
        bathrooms = 1 if area < 110 else 2
        kitchen = rng.choices(_KITCHEN_TYPES, weights=(4, 4, 2), k=1)[0]
        age = rng.choice(age_choices)
        construction_year = current_year - age
        parking = area >= 70 or rng.random() < 0.35
        elevator = city in _HIGH_RISE_CITIES and area >= 60 and age <= 15
        storage = rng.random() < 0.5
        quality = _quality_for_age(rng, age)

        specs.append(
            HouseSeedSpec(
                city=city,
                neighborhood=neighborhood,
                area_sqm=area,
                bedrooms=bedrooms,
                living_rooms=living_rooms,
                bathrooms=bathrooms,
                kitchen_type=kitchen,
                construction_year=construction_year,
                parking=parking,
                elevator=elevator,
                storage=storage,
                quality=quality,
            )
        )
    return specs
