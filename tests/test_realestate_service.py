"""Land / Construction / Renovation service tests — full real stack, no mocks.

Covers: buying land (wallet + ownership + transaction history), the whole
construction lifecycle (start, progress, completion, house creation, land
link, audit, XP), cancellation, and the renovation lifecycle with real value
increases from the dynamic pricing engine.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core import constants
from app.game.housing.construction_year import current_iranian_year
from app.database.models.construction_project import ConstructionProject
from app.database.models.land_transaction import LandTransaction
from app.database.models.renovation_project import RenovationProject
from app.game.realestate import construction as construction_domain
from app.game.realestate import renovation as renovation_domain
from app.game.shared.errors import InsufficientFundsError, PlayerNotFoundError
from app.services.realestate_service import (
    AlreadyRenovatingError,
    LandBusyError,
    LandNotAvailableError,
    LandNotFoundError,
    NothingToRenovateError,
    NotProjectOwnerError,
    ProjectNotFoundError,
    RenovationBlockedError,
    SpecInvalidError,
)

BUDGET = 100_000_000_000  # 100 billion Toman — covers anything in the tests


async def _give_money(services, player_id: int, amount: int) -> None:
    from app.database.repositories.player_repository import PlayerRepository

    async with services.players._session_factory() as session:
        await PlayerRepository(session).add_money(player_id, amount)
        await session.commit()


async def _balance(services, player_id: int) -> int:
    return await services.money.get_balance(player_id)


async def _backdate_construction(services, project_id: int, *, fraction: float | None, done: bool = False):
    """Move a project's clock: fraction of the duration elapsed (or finished)."""
    async with services.players._session_factory() as session:
        project = await session.get(ConstructionProject, project_id)
        now = datetime.now(timezone.utc)
        duration = project.duration_seconds
        if done:
            started = now - timedelta(seconds=duration + 60)
            completes = now - timedelta(seconds=30)
        else:
            started = now - timedelta(seconds=duration * fraction)
            completes = now + timedelta(seconds=duration * (1 - fraction))
        project.started_at = started
        project.completes_at = completes
        session.add(project)
        await session.commit()


async def _backdate_renovation(services, project_id: int, *, done: bool = False, fraction: float = 0.5):
    async with services.players._session_factory() as session:
        project = await session.get(RenovationProject, project_id)
        now = datetime.now(timezone.utc)
        duration = project.duration_seconds
        if done:
            project.started_at = now - timedelta(seconds=duration + 60)
            project.completes_at = now - timedelta(seconds=30)
        else:
            project.started_at = now - timedelta(seconds=duration * fraction)
            project.completes_at = now + timedelta(seconds=duration * (1 - fraction))
        session.add(project)
        await session.commit()


@pytest.fixture
async def seeded(services):
    await services.housing.ensure_initial_houses()
    lands = await services.realestate.ensure_initial_lands()
    return services, lands


def apartment_spec(land_id: int, land_area: int, **overrides) -> construction_domain.BuildingSpec:
    base = dict(
        land_id=land_id,
        building_type="a",
        floors=2,
        area_sqm=construction_domain.size_presets(land_area, 2)[0],
        bedrooms=2,
        quality_token="g",
        parking=True,
        elevator=True,
        storage=True,
    )
    base.update(overrides)
    return construction_domain.BuildingSpec(**base)


# --- Land market -----------------------------------------------------------------


async def test_land_seeding_unique_and_complete(seeded):
    services, lands = seeded
    assert len(lands) >= constants.REALESTATE_SEED_LAND_COUNT
    ids = [land.id for land in lands]
    assert len(ids) == len(set(ids))
    for land in lands:
        assert land.owner_player_id is None
        assert land.area_sqm > 0
        assert land.location_quality in ("لوکس", "عالی", "خوب", "متوسط")


async def test_seed_lands_idempotent(services):
    first = await services.realestate.ensure_initial_lands()
    second = await services.realestate.ensure_initial_lands()
    assert len(first) == len(second)


async def test_buy_land_moves_money_and_ownership(seeded, register):
    services, lands = seeded
    player = await register(tg_id=3001)
    await _give_money(services, player.player_id, BUDGET)

    target = lands[0]
    result = await services.realestate.buy_land(player.player_id, target.id)

    assert result.land.owner_player_id == player.player_id
    assert result.balance_after == BUDGET - result.price
    assert result.price > 0

    info = await services.realestate.get_land_info(target.id)
    assert info.land.owner_player_id == player.player_id

    # Transaction history saved
    async with services.players._session_factory() as session:
        txs = (
            (
                await session.execute(
                    select(LandTransaction).where(LandTransaction.land_id == target.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(txs) == 1
        assert txs[0].payer_player_id == player.player_id
        assert txs[0].payee_player_id is None  # system market
        assert txs[0].amount == result.price


async def test_buy_land_without_money_fails(seeded, register):
    services, lands = seeded
    player = await register(tg_id=3002)
    with pytest.raises(InsufficientFundsError):
        await services.realestate.buy_land(player.player_id, lands[0].id)
    info = await services.realestate.get_land_info(lands[0].id)
    assert info.land.owner_player_id is None


async def test_buy_already_owned_land_fails(seeded, register):
    services, lands = seeded
    buyer = await register(tg_id=3003)
    rival = await register(tg_id=3004)
    await _give_money(services, buyer.player_id, BUDGET)
    await services.realestate.buy_land(buyer.player_id, lands[1].id)

    await _give_money(services, rival.player_id, BUDGET)
    with pytest.raises(LandNotAvailableError):
        await services.realestate.buy_land(rival.player_id, lands[1].id)


async def test_buy_unknown_land_fails(seeded, register):
    services, _ = seeded
    player = await register(tg_id=3005)
    with pytest.raises(LandNotFoundError):
        await services.realestate.buy_land(player.player_id, 987654)


async def test_my_lands_lists_parcels_with_value(seeded, register):
    services, lands = seeded
    player = await register(tg_id=3006)
    await _give_money(services, player.player_id, 2 * BUDGET)
    await services.realestate.buy_land(player.player_id, lands[2].id)
    await services.realestate.buy_land(player.player_id, lands[3].id)

    assets = await services.realestate.get_my_lands(player.player_id)
    assert len(assets.lands) == 2
    expected_total = sum(item.market_value for item in assets.lands)
    assert assets.total_market_value == expected_total
    assert all(item.active_construction is None for item in assets.lands)


async def test_my_lands_requires_player(seeded):
    services, _ = seeded
    with pytest.raises(PlayerNotFoundError):
        await services.realestate.get_my_lands(123456)


# --- Construction ------------------------------------------------------------------


async def _buy_land(services, player_id: int, land) -> int:
    await _give_money(services, player_id, BUDGET)
    result = await services.realestate.buy_land(player_id, land.id)
    return result.land.id


async def test_start_construction_pays_and_tracks(seeded, register):
    services, lands = seeded
    player = await register(tg_id=3010)
    land_id = await _buy_land(services, player.player_id, lands[4])

    before = await _balance(services, player.player_id)
    spec = apartment_spec(land_id, lands[4].area_sqm)
    cost = construction_domain.construction_cost(spec)
    duration = construction_domain.construction_duration_seconds(spec)

    result = await services.realestate.start_construction(player.player_id, land_id, spec)

    assert result.cost == cost
    assert result.balance_after == before - cost
    assert result.project.status == "in_progress"
    assert result.project.progress_percent < 1.0  # just started
    assert 0 < result.project.seconds_remaining <= duration

    land_info = await services.realestate.get_land_info(land_id)
    assert land_info.active_construction is not None


async def test_construction_requires_owned_land(seeded, register):
    services, lands = seeded
    stranger = await register(tg_id=3011)
    spec = apartment_spec(lands[5].id, lands[5].area_sqm)
    from app.services.housing_service import NotHouseOwnerError

    with pytest.raises(NotHouseOwnerError):
        await services.realestate.start_construction(stranger.player_id, lands[5].id, spec)


async def test_construction_rejects_invalid_spec(seeded, register):
    services, lands = seeded
    player = await register(tg_id=3012)
    land_id = await _buy_land(services, player.player_id, lands[6])

    too_big = apartment_spec(land_id, lands[6].area_sqm, area_sqm=99999)
    with pytest.raises(SpecInvalidError):
        await services.realestate.start_construction(player.player_id, land_id, too_big)

    villa_with_floors = apartment_spec(land_id, lands[6].area_sqm, building_type="v")
    with pytest.raises(SpecInvalidError):
        await services.realestate.start_construction(player.player_id, land_id, villa_with_floors)

    other_land = apartment_spec(land_id + 1, lands[6].area_sqm)
    with pytest.raises(SpecInvalidError):
        await services.realestate.start_construction(player.player_id, land_id, other_land)


async def test_cannot_double_build_one_land(seeded, register):
    services, lands = seeded
    player = await register(tg_id=3013)
    land_id = await _buy_land(services, player.player_id, lands[7])
    spec = apartment_spec(land_id, lands[7].area_sqm)

    await services.realestate.start_construction(player.player_id, land_id, spec)
    with pytest.raises(LandBusyError):
        await services.realestate.start_construction(player.player_id, land_id, spec)


async def test_construction_progress_reports_fraction(seeded, register):
    services, lands = seeded
    player = await register(tg_id=3014)
    land_id = await _buy_land(services, player.player_id, lands[8])
    spec = apartment_spec(land_id, lands[8].area_sqm)
    started = await services.realestate.start_construction(player.player_id, land_id, spec)

    await _backdate_construction(services, started.project.id, fraction=0.4)
    status = await services.realestate.get_projects_status(player.player_id)
    project = status.constructions[0]

    assert project.status == "in_progress"
    assert 35 <= project.progress_percent <= 45  # ~40%
    duration = construction_domain.construction_duration_seconds(spec)
    assert 0.55 * duration <= project.seconds_remaining <= 0.65 * duration

    # Not due yet — settling must not complete it.
    await services.realestate.settle_due()
    status = await services.realestate.get_projects_status(player.player_id)
    assert status.constructions[0].status == "in_progress"


async def test_construction_completion_creates_house_and_links_land(seeded, register):
    services, lands = seeded
    player = await register(tg_id=3015)
    land_id = await _buy_land(services, player.player_id, lands[9])
    spec = apartment_spec(
        land_id,
        lands[9].area_sqm,
        quality_token="e",
        bedrooms=3,
        parking=True,
        elevator=True,
        storage=True,
    )
    started = await services.realestate.start_construction(player.player_id, land_id, spec)

    await _backdate_construction(services, started.project.id, fraction=None, done=True)
    settled = await services.realestate.settle_due()
    assert settled == 1

    # Land is now built-upon and the project links to the new house.
    info = await services.realestate.get_land_info(land_id)
    assert info.land.built_house_id is not None
    assert info.active_construction is None
    house = info.built_house
    assert house is not None
    assert house.owner_player_id == player.player_id
    assert house.construction_year == current_iranian_year()  # brand new building
    assert house.quality == "عالی"
    assert house.kitchen_type == "مدرن"  # excellent build ships modern kitchen
    assert house.area_sqm == spec.area_sqm
    assert house.parking and house.elevator and house.storage

    # The produced house plugs straight into the Housing system.
    assets = await services.housing.get_player_assets(player.player_id)
    assert any(h.id == house.id for h in assets.houses)
    value = services.realestate.house_value(house)
    assert value > 0

    # Second build attempt on the same land is refused.
    with pytest.raises(LandBusyError):
        await services.realestate.start_construction(
            player.player_id, land_id, apartment_spec(land_id, lands[9].area_sqm)
        )

    # Value audit row written with the created value.
    upgrades = await services.realestate.get_property_upgrades("house", house.id)
    assert len(upgrades) == 1
    assert upgrades[0].upgrade_kind == "construction"
    assert upgrades[0].value_after == value


async def test_completion_grants_xp(seeded, register):
    services, lands = seeded
    player = await register(tg_id=3016)
    land_id = await _buy_land(services, player.player_id, lands[10])
    spec = apartment_spec(land_id, lands[10].area_sqm)
    cost = construction_domain.construction_cost(spec)
    started = await services.realestate.start_construction(player.player_id, land_id, spec)

    await _backdate_construction(services, started.project.id, fraction=None, done=True)
    await services.realestate.settle_due()

    expected_xp = max(
        constants.HOUSING_PURCHASE_XP_MIN,
        min(constants.HOUSING_PURCHASE_XP_MAX, cost // constants.CONSTRUCTION_XP_DIVISOR),
    )
    history = await services.levels.get_xp_history(player.player_id)
    assert any(t.reason == constants.CONSTRUCTION_XP_REASON for t in history)
    profile = await services.players.get_profile(3016)
    assert profile.xp >= expected_xp


async def test_cancel_construction_refunds_and_frees_land(seeded, register):
    services, lands = seeded
    player = await register(tg_id=3017)
    land_id = await _buy_land(services, player.player_id, lands[11])
    spec = apartment_spec(land_id, lands[11].area_sqm)
    started = await services.realestate.start_construction(player.player_id, land_id, spec)

    balance_before = await _balance(services, player.player_id)
    result = await services.realestate.cancel_construction(player.player_id, started.project.id)

    expected_refund = started.cost * constants.CONSTRUCTION_CANCEL_REFUND_PERCENT // 100
    assert result.refund == expected_refund
    assert result.balance_after == balance_before + expected_refund

    status = await services.realestate.get_projects_status(player.player_id)
    assert all(p.status != "in_progress" for p in status.constructions)

    # Land is free again — building works.
    again = await services.realestate.start_construction(player.player_id, land_id, spec)
    assert again.project.status == "in_progress"
    await services.realestate.cancel_construction(player.player_id, again.project.id)


async def test_cancel_requires_owner_and_active_project(seeded, register):
    services, lands = seeded
    owner = await register(tg_id=3018)
    stranger = await register(tg_id=3019)
    land_id = await _buy_land(services, owner.player_id, lands[12])
    spec = apartment_spec(land_id, lands[12].area_sqm)
    started = await services.realestate.start_construction(owner.player_id, land_id, spec)

    with pytest.raises(NotProjectOwnerError):
        await services.realestate.cancel_construction(stranger.player_id, started.project.id)

    await services.realestate.cancel_construction(owner.player_id, started.project.id)
    with pytest.raises(ProjectNotFoundError):
        await services.realestate.cancel_construction(owner.player_id, started.project.id)


# --- Renovation ---------------------------------------------------------------------


async def test_renovation_options_and_completion_raise_value(seeded, register):
    services, lands = seeded
    player = await register(tg_id=3020)
    land_id = await _buy_land(services, player.player_id, lands[13])
    spec = apartment_spec(
        land_id,
        lands[13].area_sqm,
        quality_token="m",
        parking=False,
        elevator=False,
        storage=False,
    )
    started = await services.realestate.start_construction(player.player_id, land_id, spec)
    await _backdate_construction(services, started.project.id, fraction=None, done=True)
    await services.realestate.settle_due()

    house = (await services.realestate.get_land_info(land_id)).built_house
    house_id = house.id
    value_before = services.realestate.house_value(house)

    _dto, _label, value, options = await services.realestate.get_renovation_options(
        player.player_id, house_id
    )
    assert value == value_before
    applicable = {o.renovation_type for o in options if o.applicable}
    # A brand-new basic build: everything except modernize (age 0) is available.
    assert {"q", "k", "ba", "r", "p", "e", "s"} <= applicable
    assert "m" not in applicable

    quality_option = next(o for o in options if o.renovation_type == "q")
    assert quality_option.cost > 0

    result = await services.realestate.start_renovation(player.player_id, house_id, "q")
    assert result.cost == quality_option.cost
    assert result.value_before == value_before
    assert result.project.status == "in_progress"

    await _backdate_renovation(services, result.project.id, done=True)
    settled = await services.realestate.settle_due()
    assert settled == 1

    house_after = (await services.housing.get_house_info(house_id)).house
    assert house_after.quality == "خوب"  # متوسط → خوب

    value_after = services.realestate.house_value(house_after)
    assert value_after > value_before  # THE requirement: renovation raises value

    upgrades = await services.realestate.get_property_upgrades("house", house_id)
    quality_upgrade = next(u for u in upgrades if u.upgrade_kind == "q")
    assert quality_upgrade.value_before == value_before
    assert quality_upgrade.value_after == value_after


async def test_modernize_advances_construction_year(seeded, register):
    services, _ = seeded
    player = await register(tg_id=3021)
    # Buy an old house from the housing market.
    await _give_money(services, player.player_id, BUDGET)
    houses = await services.housing.ensure_initial_houses()
    old_house = next(
        h
        for h in houses
        if current_iranian_year() - h.construction_year
        >= renovation_domain.MODERNIZE_MIN_AGE
    )
    await services.housing.buy_from_market(player.player_id, old_house.id)

    result = await services.realestate.start_renovation(
        player.player_id, old_house.id, renovation_domain.R_MODERNIZE
    )
    await _backdate_renovation(services, result.project.id, done=True)
    await services.realestate.settle_due()

    info = await services.housing.get_house_info(old_house.id)
    expected_year = min(
        current_iranian_year(),
        old_house.construction_year + renovation_domain.MODERNIZE_AGE_REDUCTION,
    )
    assert info.house.construction_year == expected_year


async def test_kitchen_and_facility_renovations_apply(seeded, register):
    services, lands = seeded
    player = await register(tg_id=3022)
    land_id = await _buy_land(services, player.player_id, lands[14])
    spec = apartment_spec(
        land_id, lands[14].area_sqm, quality_token="m",
        parking=False, elevator=False, storage=False,
    )
    started = await services.realestate.start_construction(player.player_id, land_id, spec)
    await _backdate_construction(services, started.project.id, fraction=None, done=True)
    await services.realestate.settle_due()
    house_id = (await services.realestate.get_land_info(land_id)).built_house.id

    # Kitchen renovation
    result = await services.realestate.start_renovation(player.player_id, house_id, "k")
    await _backdate_renovation(services, result.project.id, done=True)
    await services.realestate.settle_due()
    kitchen = (await services.housing.get_house_info(house_id)).house.kitchen_type
    assert kitchen == "مدرن"

    # Parking renovation
    result = await services.realestate.start_renovation(player.player_id, house_id, "p")
    await _backdate_renovation(services, result.project.id, done=True)
    await services.realestate.settle_due()
    assert (await services.housing.get_house_info(house_id)).house.parking is True

    # Bathroom renovation
    result = await services.realestate.start_renovation(player.player_id, house_id, "ba")
    await _backdate_renovation(services, result.project.id, done=True)
    await services.realestate.settle_due()
    assert (await services.housing.get_house_info(house_id)).house.bathrooms >= 2


async def test_renovation_requires_ownership(seeded, register):
    services, _ = seeded
    stranger = await register(tg_id=3023)
    await _give_money(services, stranger.player_id, BUDGET)
    houses = await services.housing.ensure_initial_houses()
    with pytest.raises(Exception):
        await services.realestate.get_renovation_options(stranger.player_id, houses[0].id)
    from app.services.housing_service import NotHouseOwnerError

    with pytest.raises(NotHouseOwnerError):
        await services.realestate.start_renovation(stranger.player_id, houses[0].id, "q")


async def test_renovation_blocked_while_rented(seeded, register):
    services, _ = seeded
    owner = await register(tg_id=3024)
    tenant = await register(tg_id=3025)
    await _give_money(services, owner.player_id, BUDGET)
    await _give_money(services, tenant.player_id, BUDGET)

    houses = await services.housing.ensure_initial_houses()
    await services.housing.buy_from_market(owner.player_id, houses[1].id)
    options = await services.housing.get_rent_options(houses[1].id, owner.player_id)
    _, deposit, rent = options.options[0]
    await services.housing.list_house_for_rent(owner.player_id, houses[1].id, rent, 0)
    await services.housing.rent_house(tenant.player_id, houses[1].id)

    with pytest.raises(RenovationBlockedError):
        await services.realestate.start_renovation(owner.player_id, houses[1].id, "q")


async def test_no_parallel_renovations_on_one_house(seeded, register):
    services, _ = seeded
    player = await register(tg_id=3026)
    await _give_money(services, player.player_id, 2 * BUDGET)
    houses = await services.housing.ensure_initial_houses()
    await services.housing.buy_from_market(player.player_id, houses[2].id)

    await services.realestate.start_renovation(player.player_id, houses[2].id, "q")
    with pytest.raises(AlreadyRenovatingError):
        await services.realestate.start_renovation(player.player_id, houses[2].id, "p")


async def test_non_applicable_renovation_rejected(seeded, register):
    services, lands = seeded
    player = await register(tg_id=3027)
    land_id = await _buy_land(services, player.player_id, lands[15])
    spec = apartment_spec(
        land_id, lands[15].area_sqm, quality_token="e",
        parking=True, elevator=True, storage=True,
    )
    started = await services.realestate.start_construction(player.player_id, land_id, spec)
    await _backdate_construction(services, started.project.id, fraction=None, done=True)
    await services.realestate.settle_due()
    house_id = (await services.realestate.get_land_info(land_id)).built_house.id

    # Perfect brand-new luxury house: quality/kitchen/parking/elevator/storage/modernize all N/A.
    for rtype in ("q", "k", "p", "e", "s", "m"):
        with pytest.raises(NothingToRenovateError):
            await services.realestate.start_renovation(player.player_id, house_id, rtype)


async def test_renovation_without_money_fails(seeded, register):
    services, _ = seeded
    player = await register(tg_id=3028)
    houses = await services.housing.ensure_initial_houses()
    await _give_money(services, player.player_id, BUDGET)
    await services.housing.buy_from_market(player.player_id, houses[3].id)
    # Drain the wallet.
    balance = await _balance(services, player.player_id)
    await services.money.remove_money(player.player_id, balance)

    with pytest.raises(InsufficientFundsError):
        await services.realestate.start_renovation(player.player_id, houses[3].id, "q")


# --- Integration: market/economy knob ---------------------------------------------------


async def test_market_conditions_move_land_prices(seeded, monkeypatch):
    services, lands = seeded
    land = lands[0]
    from app.game.realestate.land_pricing import LandPricingInput, estimate_land_price

    pricing_input = LandPricingInput(
        land_id=land.id, city=land.city, neighborhood=land.neighborhood, area_sqm=land.area_sqm
    )
    base = estimate_land_price(pricing_input)
    monkeypatch.setattr(constants, "ECONOMY_MARKET_CONDITIONS", 1.3)
    inflated = estimate_land_price(pricing_input)
    assert inflated > base  # economic changes reprice every parcel
