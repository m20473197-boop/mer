"""Focused safety coverage for حاج ممد's fixed car dealership."""

from __future__ import annotations

import asyncio

import pytest

from app.game.shared.errors import InsufficientFundsError
from app.services.vehicle_service import (
    VehicleAlreadyOwnedError,
    VehicleModelNotFoundError,
    VehicleOwnershipLimitReachedError,
    VehicleService,
)

EXPECTED_CARS = (
    ("پراید ۱۳۱", 780_000_000),
    ("پراید ۱۱۱", 700_000_000),
    ("تیبا", 1_059_000_000),
    ("تیبا ۲", 1_060_000_000),
    ("ساینا", 1_420_000_000),
    ("کوییک", 1_430_000_000),
    ("پژو ۴۰۵", 1_220_000_000),
    ("پژو پارس", 1_693_000_000),
    ("پژو ۲۰۶", 1_200_000_000),
    ("پژو ۲۰۷", 2_050_000_000),
    ("سمند", 1_650_000_000),
    ("سمند سورن", 1_860_000_000),
    ("دنا", 2_460_000_000),
    ("دنا پلاس", 3_375_000_000),
    ("رانا", 1_900_000_000),
    ("زانتیا", 1_200_000_000),
    ("ال۹۰", 1_500_000_000),
    ("شاهین", 2_200_000_000),
)


@pytest.mark.asyncio
async def test_fixed_catalog_prices_and_shoti_metadata(services):
    models = await services.vehicles.get_catalog()
    assert [(model.name, model.purchase_price) for model in models] == list(EXPECTED_CARS)
    assert [model.name for model in models if model.is_shoti_eligible] == [
        "پژو ۴۰۵",
        "پژو پارس",
        "سمند",
        "زانتیا",
    ]
    with pytest.raises(VehicleModelNotFoundError):
        await services.vehicles.get_model(999)


@pytest.mark.asyncio
async def test_purchase_is_persisted_and_my_cars_is_owner_scoped(services, db):
    player = await services.players.register_or_get(
        telegram_user_id=8101, username="carbuyer", display_name="خریدار ماشین"
    )
    await services.money.add_money(player.player_id, 1_220_000_000)

    result = await services.vehicles.purchase(player.player_id, 7)
    assert result.ownership.model.name == "پژو ۴۰۵"
    assert result.ownership.purchase_price == 1_220_000_000
    assert await services.money.get_balance(player.player_id) == 0
    assert len(await services.vehicles.get_owned_vehicles(player.player_id)) == 1

    # A new service registry/session sees the same persisted ownership.
    from app.services import ServiceRegistry

    restarted_services = ServiceRegistry(db.session_factory)
    owned_after_restart = await restarted_services.vehicles.get_owned_vehicles(
        player.player_id
    )
    assert owned_after_restart[0].ownership_id == result.ownership.ownership_id
    assert owned_after_restart[0].model.name == "پژو ۴۰۵"


@pytest.mark.asyncio
async def test_insufficient_balance_and_duplicate_purchase_are_safe(services):
    player = await services.players.register_or_get(
        telegram_user_id=8102, username="poor", display_name="بدون پول"
    )
    with pytest.raises(InsufficientFundsError):
        await services.vehicles.purchase(player.player_id, 1)
    assert await services.vehicles.get_owned_vehicles(player.player_id) == []

    await services.money.add_money(player.player_id, 1_560_000_000)
    outcomes = await asyncio.gather(
        services.vehicles.purchase(player.player_id, 1),
        services.vehicles.purchase(player.player_id, 1),
        return_exceptions=True,
    )
    assert sum(not isinstance(outcome, Exception) for outcome in outcomes) == 1
    assert sum(
        isinstance(outcome, (VehicleAlreadyOwnedError, InsufficientFundsError))
        for outcome in outcomes
    ) == 1
    assert await services.money.get_balance(player.player_id) == 780_000_000
    assert len(await services.vehicles.get_owned_vehicles(player.player_id)) == 1


@pytest.mark.asyncio
async def test_vehicle_ownership_limit_is_configurable(services):
    player = await services.players.register_or_get(
        telegram_user_id=8103, username="limited", display_name="محدود"
    )
    await services.money.add_money(player.player_id, 2_000_000_000)
    limited_service = VehicleService(
        services.players._session_factory,  # noqa: SLF001 - fixture wiring only
        money_service=services.money,
        ownership_limit=1,
    )
    await limited_service.purchase(player.player_id, 1)
    with pytest.raises(VehicleOwnershipLimitReachedError):
        await limited_service.purchase(player.player_id, 2)
