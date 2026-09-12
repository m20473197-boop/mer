"""Dynamic pricing engine tests — no fixed prices anywhere."""

from __future__ import annotations

import pytest

from app.game.housing import pricing
from app.game.housing.catalog import CITY_BASE_PRICE_PER_SQM
from app.game.housing.construction_year import current_iranian_year
from app.game.housing.pricing import HousePricingInput

_BASE_YEAR = current_iranian_year()


def make_input(**overrides) -> HousePricingInput:
    base = dict(
        house_id=1,
        city="تهران",
        neighborhood="نارمک",
        area_sqm=80,
        bedrooms=2,
        living_rooms=1,
        bathrooms=1,
        kitchen_type="معمولی",
        construction_year=_BASE_YEAR - 5,
        parking=True,
        elevator=True,
        storage=True,
        quality="خوب",
    )
    base.update(overrides)
    return HousePricingInput(**base)


def test_price_is_positive_exact_integer():
    price = pricing.estimate_house_price(make_input())
    assert isinstance(price, int)
    assert price > 0


def test_price_is_deterministic_per_house():
    """The same house always has the same price (stable jitter)."""
    assert pricing.estimate_house_price(make_input()) == pricing.estimate_house_price(
        make_input()
    )


def test_price_depends_on_city():
    """Identical houses in different cities get different prices."""
    tehran = pricing.estimate_house_price(make_input(city="تهران", neighborhood="نارمک"))
    yazd = pricing.estimate_house_price(make_input(city="یزد", neighborhood="صفائیه"))
    assert tehran > yazd > 0


def test_price_depends_on_neighborhood():
    expensive = pricing.estimate_house_price(
        make_input(city="تهران", neighborhood="ونک")
    )
    cheap = pricing.estimate_house_price(
        make_input(city="تهران", neighborhood="یافت‌آباد")
    )
    assert expensive > cheap


def test_price_scales_with_area():
    small = pricing.estimate_house_price(make_input(area_sqm=50))
    large = pricing.estimate_house_price(make_input(area_sqm=120))
    assert large > small
    # But not perfectly linear — the size discount kicks in for large homes.
    per_sqm_small = small / 50
    per_sqm_large = large / 120
    assert per_sqm_large < per_sqm_small


def test_construction_year_depreciates_price_with_floor():
    this_year = current_iranian_year()
    new = pricing.estimate_house_price(make_input(construction_year=this_year))
    mid = pricing.estimate_house_price(make_input(construction_year=this_year - 15))
    old = pricing.estimate_house_price(make_input(construction_year=this_year - 30))
    # The 45% floor is reached at ~46 years and stops further depreciation.
    floored = pricing.estimate_house_price(make_input(construction_year=this_year - 50))
    # 1330 is the oldest accepted year (~75 years old) — still on the floor.
    ancient = pricing.estimate_house_price(make_input(construction_year=1330))
    assert new > mid > old > floored
    assert floored == ancient  # the floor keeps very old houses sellable


def test_future_construction_year_is_rejected():
    with pytest.raises(ValueError):
        pricing.estimate_house_price(
            make_input(construction_year=current_iranian_year() + 1)
        )


def test_too_old_construction_year_is_rejected():
    with pytest.raises(ValueError):
        pricing.estimate_house_price(make_input(construction_year=1300))


def test_facilities_increase_price():
    base = make_input(parking=False, elevator=False, storage=False, area_sqm=80)
    full = make_input(parking=True, elevator=True, storage=True, area_sqm=80)
    assert pricing.estimate_house_price(full) > pricing.estimate_house_price(base)


def test_more_bedrooms_and_bathrooms_increase_price():
    base = pricing.estimate_house_price(make_input(bedrooms=1, bathrooms=1))
    more = pricing.estimate_house_price(make_input(bedrooms=3, bathrooms=2))
    assert more > base


def test_kitchen_type_ordering():
    modern = pricing.estimate_house_price(make_input(kitchen_type="مدرن"))
    normal = pricing.estimate_house_price(make_input(kitchen_type="معمولی"))
    old = pricing.estimate_house_price(make_input(kitchen_type="قدیمی"))
    assert modern > normal > old


def test_quality_ordering():
    excellent = pricing.estimate_house_price(make_input(quality="عالی"))
    good = pricing.estimate_house_price(make_input(quality="خوب"))
    average = pricing.estimate_house_price(make_input(quality="متوسط"))
    weak = pricing.estimate_house_price(make_input(quality="ضعیف"))
    assert excellent > good > average > weak


def test_unknown_location_is_rejected():
    with pytest.raises(ValueError):
        pricing.estimate_house_price(make_input(city="پاریس"))
    with pytest.raises(ValueError):
        pricing.estimate_house_price(make_input(neighborhood="مارال‌پارک"))


def test_zero_area_is_rejected():
    with pytest.raises(ValueError):
        pricing.estimate_house_price(make_input(area_sqm=0))


def test_jitter_varies_between_houses():
    prices = {
        pricing.estimate_house_price(make_input(house_id=house_id))
        for house_id in range(50)
    }
    assert len(prices) > 1  # houses differ a little even with identical specs


def test_market_factor_scales_price():
    base = pricing.estimate_house_price(make_input())
    boosted = pricing.estimate_house_price(make_input(), market_factor=1.5)
    assert boosted > base
    ratio = boosted / base
    assert 1.4 < ratio < 1.6  # jitter keeps it approximately proportional


def test_price_rounded_to_clean_step():
    price = pricing.estimate_house_price(make_input())
    assert price % pricing.PRICE_ROUNDING_STEP == 0


def test_prices_in_realistic_band_for_catalog():
    """Sanity: a mid Tehran flat lands in a plausible multi-billion band."""
    price = pricing.estimate_house_price(make_input(house_id=11))
    raw = CITY_BASE_PRICE_PER_SQM["تهران"] * 80
    assert 0.3 * raw < price < 3 * raw


# --- Rent estimation --------------------------------------------------------------


def test_estimated_rent_is_positive_and_proportional():
    rent_small = pricing.estimate_monthly_rent(make_input(area_sqm=50))
    rent_large = pricing.estimate_monthly_rent(make_input(area_sqm=150))
    assert rent_small > 0
    assert rent_large > rent_small


def test_rent_rounded_to_clean_step():
    rent = pricing.estimate_monthly_rent(make_input())
    assert rent % pricing.RENT_ROUNDING_STEP == 0


def test_higher_deposit_lowers_monthly_rent():
    value = 1_000_000_000
    deposit0, rent0 = pricing.suggested_deposit_and_rent(value, deposit_percent=0)
    deposit20, rent20 = pricing.suggested_deposit_and_rent(value, deposit_percent=20)
    assert deposit0 == 0
    assert deposit20 == 200_000_000
    assert rent20 < rent0
    assert rent0 > 0


def test_negative_deposit_clamped():
    deposit, rent = pricing.suggested_deposit_and_rent(1_000_000_000, deposit_percent=-5)
    assert deposit == 0
    assert rent > 0
