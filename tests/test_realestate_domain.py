"""Land / Construction / Renovation domain tests — pricing, costs, durations."""

from __future__ import annotations

import pytest

from app.core import constants
from app.game.housing.dto import HouseData
from app.game.realestate import construction, renovation
from app.game.realestate.land_pricing import (
    LandPricingInput,
    estimate_land_price,
    estimate_land_price_per_sqm,
    location_quality_label,
    quality_label_for,
)
from app.game.realestate.market import current_market_factor
from app.game.housing.construction_year import current_iranian_year
from datetime import datetime, timezone


def make_land(**overrides) -> LandPricingInput:
    base = dict(land_id=1, city="تهران", neighborhood="نارمک", area_sqm=200)
    base.update(overrides)
    return LandPricingInput(**base)


def make_house(**overrides) -> HouseData:
    base = dict(
        id=1,
        city="تهران",
        neighborhood="نارمک",
        area_sqm=100,
        bedrooms=2,
        living_rooms=1,
        bathrooms=1,
        kitchen_type="معمولی",
        construction_year=current_iranian_year() - 12,
        parking=False,
        elevator=False,
        storage=False,
        quality="متوسط",
        owner_player_id=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    base.update(overrides)
    return HouseData(**base)


def make_spec(**overrides) -> construction.BuildingSpec:
    base = dict(
        land_id=1,
        building_type="a",
        floors=3,
        area_sqm=180,
        bedrooms=3,
        quality_token="g",
        parking=True,
        elevator=True,
        storage=True,
    )
    base.update(overrides)
    return construction.BuildingSpec(**base)


# --- Land pricing ------------------------------------------------------------------


def test_land_price_positive_integer_deterministic():
    price = estimate_land_price(make_land())
    assert isinstance(price, int) and price > 0
    assert estimate_land_price(make_land()) == price


def test_land_price_depends_on_city_and_neighborhood():
    tehran = estimate_land_price(make_land(city="تهران", neighborhood="نارمک"))
    yazd = estimate_land_price(make_land(city="یزد", neighborhood="صفائیه"))
    prime = estimate_land_price(make_land(city="تهران", neighborhood="ونک"))
    assert tehran > yazd
    assert prime > tehran  # لوکس neighborhood costs more


def test_land_price_scales_with_size_with_wholesale_discount():
    small = estimate_land_price(make_land(area_sqm=100))
    large = estimate_land_price(make_land(area_sqm=1000))
    assert large > small
    assert large / small < 10  # per-sqm discount for big parcels


def test_land_price_follows_market_factor():
    base = estimate_land_price(make_land())
    inflated = estimate_land_price(make_land(), market_factor=1.5)
    assert inflated > base
    assert 1.4 < inflated / base < 1.6


def test_land_price_uses_live_market_conditions(monkeypatch):
    base = estimate_land_price(make_land())
    monkeypatch.setattr(constants, "ECONOMY_MARKET_CONDITIONS", 1.2)
    assert current_market_factor() == 1.2
    assert estimate_land_price(make_land()) > base  # economy moved every price


def test_land_price_rejects_unknown_locations():
    with pytest.raises(ValueError):
        estimate_land_price(make_land(city="پاریس"))
    with pytest.raises(ValueError):
        estimate_land_price(make_land(neighborhood="مارال‌پارک"))
    with pytest.raises(ValueError):
        estimate_land_price(make_land(area_sqm=0))


def test_land_price_per_sqm_positive():
    per_sqm = estimate_land_price_per_sqm(make_land())
    assert per_sqm > 0
    assert estimate_land_price(make_land()) >= per_sqm * 100  # sanity band


def test_location_quality_labels():
    assert location_quality_label(2.3) == "لوکس"
    assert location_quality_label(1.2) == "عالی"
    assert location_quality_label(0.95) == "خوب"
    assert location_quality_label(0.6) == "متوسط"
    assert quality_label_for("تهران", "ونک") == "لوکس"
    assert quality_label_for("تهران", "نامعلوم") is None


# --- Construction cost & duration ---------------------------------------------------


def test_construction_cost_scales_with_size_quality_floors():
    small = construction.construction_cost(make_spec(area_sqm=90))
    big = construction.construction_cost(make_spec(area_sqm=270))
    medium = construction.construction_cost(make_spec(quality_token="m"))
    luxury = construction.construction_cost(make_spec(quality_token="e"))
    one_floor = construction.construction_cost(make_spec(building_type="v", floors=1, area_sqm=180, elevator=False))
    assert big > small
    assert luxury > medium
    assert construction.construction_cost(make_spec(floors=4)) > one_floor


def test_construction_cost_includes_facilities():
    bare = construction.construction_cost(
        make_spec(parking=False, elevator=False, storage=False, quality_token="m")
    )
    full = construction.construction_cost(make_spec(quality_token="m"))
    assert full > bare


def test_construction_cost_follows_market(monkeypatch):
    base = construction.construction_cost(make_spec())
    monkeypatch.setattr(constants, "ECONOMY_MARKET_CONDITIONS", 2.0)
    assert construction.construction_cost(make_spec()) > base * 1.9


def test_construction_duration_depends_on_spec():
    small = construction.construction_duration_seconds(make_spec(area_sqm=70))
    big = construction.construction_duration_seconds(make_spec(area_sqm=240))
    luxury = construction.construction_duration_seconds(make_spec(quality_token="e"))
    villa = construction.construction_duration_seconds(
        make_spec(building_type="v", floors=1, elevator=False)
    )
    assert big > small
    assert luxury > construction.construction_duration_seconds(make_spec())
    assert villa < big
    assert construction.CONSTRUCTION_MIN_DAYS * 86400 <= villa


def test_size_presets_within_land_capacity():
    presets = construction.size_presets(200, 3)
    assert presets
    for area in presets:
        assert 35 <= area <= 600  # 200 sqm × 3 floors
    assert construction.size_presets(200, 3) == construction.size_presets(200, 3)


def test_validate_spec_accepts_valid_and_rejects_invalid():
    construction.validate_spec(make_spec(), land_area_sqm=100)  # 180 ≤ 100×3 ok
    construction.validate_spec(
        make_spec(
            building_type="v", floors=1, area_sqm=80, bedrooms=2, elevator=False
        ),
        100,
    )
    with pytest.raises(ValueError):
        construction.validate_spec(make_spec(building_type="v"), 100)  # villa 3 floors
    with pytest.raises(ValueError):
        construction.validate_spec(make_spec(area_sqm=999), 100)  # too big
    with pytest.raises(ValueError):
        construction.validate_spec(make_spec(area_sqm=10), 100)  # too small
    with pytest.raises(ValueError):
        construction.validate_spec(make_spec(bedrooms=9), 100)
    with pytest.raises(ValueError):
        construction.validate_spec(make_spec(quality_token="x"), 100)
    with pytest.raises(ValueError):
        construction.validate_spec(make_spec(building_type="z"), 100)


def test_derived_rooms_and_bedroom_bounds():
    assert construction.derived_rooms(120, 2) == (1, 1)
    assert construction.derived_rooms(200, 3)[0] >= 2
    assert construction.bedroom_max(70) == 2
    assert construction.bedroom_max(400) <= construction.MAX_BEDROOMS


def test_villa_cannot_have_elevator():
    with pytest.raises(ValueError):
        construction.validate_spec(
            make_spec(building_type="v", floors=1, elevator=True), 100
        )


# --- Renovation options & application -------------------------------------------------


def test_renovation_options_for_average_old_house():
    house = make_house(bedrooms=1)  # area 100 → room capacity 2, so adding is possible
    options = renovation.available_renovations(house)
    by_type = {o.renovation_type: o for o in options}

    assert by_type[renovation.R_QUALITY].applicable  # متوسط → خوب
    assert by_type[renovation.R_KITCHEN].applicable  # معمولی → مدرن
    assert by_type[renovation.R_BATHROOM].applicable
    assert by_type[renovation.R_ADD_ROOM].applicable
    assert by_type[renovation.R_PARKING].applicable
    assert by_type[renovation.R_ELEVATOR].applicable
    assert by_type[renovation.R_STORAGE].applicable
    assert by_type[renovation.R_MODERNIZE].applicable  # 12 years old


def test_maxed_house_has_fewer_options():
    house = make_house(
        quality="عالی",
        kitchen_type="مدرن",
        bathrooms=renovation.MAX_BATHROOMS,
        parking=True,
        elevator=True,
        storage=True,
        construction_year=current_iranian_year() - 1,
        area_sqm=180,   # room capacity = 5
        bedrooms=5,     # capacity reached → no room to add
    )
    for option in renovation.available_renovations(house):
        assert not option.applicable  # literally nothing left to improve


def test_add_room_blocked_by_area():
    house = make_house(area_sqm=40, bedrooms=1)
    room = next(
        o for o in renovation.available_renovations(house)
        if o.renovation_type == renovation.R_ADD_ROOM
    )
    assert not room.applicable


def test_renovation_costs_take_time_and_money():
    house = make_house()
    for option in renovation.available_renovations(house):
        if option.applicable:
            assert option.cost > 0
            assert option.duration_seconds > 0


def test_renovation_costs_follow_market(monkeypatch):
    house = make_house()
    base = next(
        o for o in renovation.available_renovations(house)
        if o.renovation_type == renovation.R_QUALITY
    )
    monkeypatch.setattr(constants, "ECONOMY_MARKET_CONDITIONS", 1.5)
    inflated = next(
        o for o in renovation.available_renovations(house)
        if o.renovation_type == renovation.R_QUALITY
    )
    assert inflated.cost > base.cost


def test_apply_renovation_changes_expected_fields():
    house = make_house(bedrooms=1)  # spare room capacity for the add-room case
    assert renovation.apply_renovation(house, renovation.R_QUALITY) == {"quality": "خوب"}
    assert renovation.apply_renovation(house, renovation.R_KITCHEN) == {"kitchen_type": "مدرن"}
    assert renovation.apply_renovation(house, renovation.R_BATHROOM) == {"bathrooms": 2}
    assert renovation.apply_renovation(house, renovation.R_ADD_ROOM) == {"bedrooms": 2}
    assert renovation.apply_renovation(house, renovation.R_PARKING) == {"parking": True}
    assert renovation.apply_renovation(house, renovation.R_ELEVATOR) == {"elevator": True}
    assert renovation.apply_renovation(house, renovation.R_STORAGE) == {"storage": True}
    # A 12-year-old house becomes brand new again (year jumps to the current).
    modernized = make_house(construction_year=current_iranian_year() - 12)
    assert renovation.apply_renovation(modernized, renovation.R_MODERNIZE) == {
        "construction_year": current_iranian_year()
    }


def test_apply_renovation_rejects_non_applicable():
    new_house = make_house(construction_year=current_iranian_year() - 1)
    with pytest.raises(ValueError):
        renovation.apply_renovation(new_house, renovation.R_MODERNIZE)
    perfect = make_house(quality="عالی")
    with pytest.raises(ValueError):
        renovation.apply_renovation(perfect, renovation.R_QUALITY)
    with pytest.raises(ValueError):
        renovation.apply_renovation(perfect, "nonexistent")
