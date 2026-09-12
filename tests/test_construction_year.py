"""Construction-year (سال ساخت) domain tests — calendar math and validation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.game.housing.construction_year import (
    MIN_CONSTRUCTION_YEAR,
    age_from_construction_year,
    current_iranian_year,
    validate_construction_year,
)


def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def test_iranian_year_after_nowruz():
    # 2026-03-21 (after Nowruz) → 1405
    assert current_iranian_year(_dt(2026, 3, 21)) == 1405
    assert current_iranian_year(_dt(2026, 9, 10)) == 1405  # the worked example


def test_iranian_year_before_nowruz():
    # 2026-03-10 (before Nowruz) → still 1404
    assert current_iranian_year(_dt(2026, 3, 10)) == 1404
    assert current_iranian_year(_dt(2026, 1, 1)) == 1404


def test_year_rollover_arithmetic():
    assert current_iranian_year(_dt(2025, 4, 1)) == 1404
    assert current_iranian_year(_dt(2024, 8, 15)) == 1403


def test_age_from_construction_year():
    # The exact example from the spec: a 1395 build is 10 years old in 1405.
    assert age_from_construction_year(1395, _dt(2026, 9, 10)) == 10
    assert age_from_construction_year(1405, _dt(2026, 9, 10)) == 0


def test_age_never_negative_for_future_years():
    assert age_from_construction_year(1410, _dt(2026, 9, 10)) == 0


def test_validation_accepts_plausible_years():
    validate_construction_year(1395, _dt(2026, 9, 10))
    validate_construction_year(MIN_CONSTRUCTION_YEAR, _dt(2026, 9, 10))
    validate_construction_year(1405, _dt(2026, 9, 10))


def test_validation_rejects_future_and_too_old():
    with pytest.raises(ValueError):
        validate_construction_year(1406, _dt(2026, 9, 10))
    with pytest.raises(ValueError):
        validate_construction_year(MIN_CONSTRUCTION_YEAR - 1, _dt(2026, 9, 10))


def test_pricing_uses_derived_age_not_stored_age():
    """Depreciation must come from the construction year, not a stored age."""
    from app.game.housing import pricing
    from app.game.housing.pricing import HousePricingInput

    def input_for(construction_year: int) -> HousePricingInput:
        return HousePricingInput(
            house_id=42,
            city="تهران",
            neighborhood="نارمک",
            area_sqm=100,
            bedrooms=2,
            living_rooms=1,
            bathrooms=1,
            kitchen_type="معمولی",
            construction_year=construction_year,
            parking=True,
            elevator=True,
            storage=True,
            quality="خوب",
        )

    this_year = current_iranian_year()
    fresh = pricing.estimate_house_price(input_for(this_year))
    ten_years_old = pricing.estimate_house_price(input_for(this_year - 10))
    # ~1.2% depreciation per year over 10 years (with ±3% jitter band).
    assert fresh > ten_years_old
    ratio = ten_years_old / fresh
    assert 0.80 < ratio < 0.94
