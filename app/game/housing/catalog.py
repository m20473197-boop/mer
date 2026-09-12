"""The Iranian housing catalog — cities, neighborhoods and market data.

This module is the *single connection point* for real-world housing market
data. Today it ships a curated, game-balanced snapshot:

* ``CITY_BASE_PRICE_PER_SQM`` — average price per square meter (Toman) per city
* ``CITY_NEIGHBORHOODS``     — neighborhoods per city with a price multiplier

Future integration with live Iranian housing market feeds only needs to
replace/fill these two structures (e.g. refreshed by a sync job) — the
pricing engine in ``pricing.py`` and every other layer keep working
unchanged. All values are exact integers/floats — no floats for money
results (prices are rounded to whole Toman by the pricing engine).
"""

from __future__ import annotations

# Average price per square meter (Toman) for a mid-range apartment.
# Game-balanced so salaries from the Job system make ownership reachable.
CITY_BASE_PRICE_PER_SQM: dict[str, int] = {
    "تهران": 55_000_000,
    "کرج": 28_000_000,
    "مشهد": 25_000_000,
    "اصفهان": 26_000_000,
    "شیراز": 26_000_000,
    "تبریز": 20_000_000,
    "قم": 18_000_000,
    "اهواز": 17_000_000,
    "رشت": 22_000_000,
    "یزد": 19_000_000,
}

# Neighborhoods per city with their price multiplier (1.0 = city average).
CITY_NEIGHBORHOODS: dict[str, dict[str, float]] = {
    "تهران": {
        "ونک": 2.3,
        "سعادت‌آباد": 2.0,
        "شهرک غرب": 1.7,
        "جنت‌آباد": 1.5,
        "یوسف‌آباد": 1.6,
        "پونک": 1.2,
        "نارمک": 1.15,
        "تهرانپارس": 0.95,
        "آزادی": 0.8,
        "شهرری": 0.75,
        "یافت‌آباد": 0.6,
    },
    "کرج": {
        "گوهردشت": 1.3,
        "مهرشهر": 1.25,
        "عظیمیه": 1.15,
        "جهانشهر": 1.1,
        "گردکان": 0.8,
        "همت": 0.9,
    },
    "مشهد": {
        "احمدآباد": 1.5,
        "سجاد": 1.4,
        "هاشمیه": 1.25,
        "وکیل‌آباد": 1.2,
        "قاسم‌آباد": 0.95,
        "طلاب": 0.7,
    },
    "اصفهان": {
        "مرداویج": 1.35,
        "سعادت‌آباد": 1.25,
        "ملک‌شهر": 0.75,
        "خانه اصفهان": 1.1,
        "شاهین‌شهر": 0.9,
        "چهارباغ": 1.3,
    },
    "شیراز": {
        "قصرالدشت": 1.35,
        "معالی‌آباد": 1.3,
        "ستارخان": 1.05,
        "صدرا": 0.8,
        "ملاصدرا": 1.25,
        "امامیه": 0.9,
    },
    "تبریز": {
        "ولیعصر": 1.4,
        "الهی‌پرست": 1.25,
        "زعفرانیه": 1.15,
        "باغمیشه": 1.0,
        "لاکان": 0.9,
        "خیابان شیشمیکان": 0.75,
    },
    "قم": {
        "پردیسان": 1.35,
        "جهان آرا": 1.1,
        "صفائیه": 1.0,
        "سلامت": 0.9,
        "شهرک قدس": 0.8,
    },
    "اهواز": {
        "کیانپارس": 1.4,
        "زیتون کارمندی": 1.15,
        "کیان آباد": 1.0,
        "گلستان": 0.85,
        "حشتوکان": 0.7,
    },
    "رشت": {
        "گلسار": 1.35,
        "منظریه": 1.2,
        "لاکان": 1.05,
        "کوچصفهان جاده": 0.75,
        "چمارسرا": 0.9,
    },
    "یزد": {
        "صفائیه": 1.35,
        "امام شهر": 1.1,
        "علامرودشت": 1.0,
        "آزادشهر": 0.9,
        "شهرک بعثت": 0.8,
    },
}

# Normalization helper — used by seeding, validation and the pricing engine.


def list_cities() -> list[str]:
    """All supported cities (stable order as defined above)."""
    return list(CITY_BASE_PRICE_PER_SQM.keys())


def get_neighborhoods(city: str) -> dict[str, float]:
    """Neighborhood multipliers for ``city`` (empty dict for unknown cities)."""
    return CITY_NEIGHBORHOODS.get(city, {})


def get_neighborhood_multiplier(city: str, neighborhood: str) -> float | None:
    """Multiplier for a neighborhood, or ``None`` if the pair is unknown."""
    return get_neighborhoods(city).get(neighborhood)


def get_base_price_per_sqm(city: str) -> int | None:
    """Base price per square meter for ``city``, or ``None`` if unknown."""
    return CITY_BASE_PRICE_PER_SQM.get(city)


def is_valid_location(city: str, neighborhood: str) -> bool:
    """Whether the (city, neighborhood) pair exists in the catalog."""
    return get_neighborhood_multiplier(city, neighborhood) is not None
