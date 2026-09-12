"""Focused safety coverage for the player-to-player Divar marketplace."""

from __future__ import annotations

import asyncio

import pytest

from app.database.repositories.house_repository import HouseRepository
from app.game.marketplace.catalog import (
    ASSET_TYPE_CAR,
    ASSET_TYPE_HOUSE,
    ASSET_TYPE_LAND,
    LISTING_STATUS_SOLD,
    SUPPORTED_ASSET_TYPES,
)
from app.game.marketplace.dto import MarketplaceSearchCriteria
from app.game.marketplace.search import parse_search_query, parse_range_input
from app.game.shared.errors import InsufficientFundsError
from app.services.divar_service import (
    MarketplaceAssetNotOwnedError,
    MarketplaceCannotBuyOwnListingError,
    MarketplaceInvalidPriceError,
    MarketplaceListingAlreadyExistsError,
    MarketplaceListingNotActiveError,
)


async def _players_and_house(services):
    seller = await services.players.register_or_get(
        telegram_user_id=7101, username="seller", display_name="فروشنده"
    )
    buyer = await services.players.register_or_get(
        telegram_user_id=7102, username="buyer", display_name="خریدار"
    )
    async with services.players._session_factory() as session:  # noqa: SLF001
        house = await HouseRepository(session).create(
            city="تهران",
            neighborhood="ونک",
            area_sqm=120,
            bedrooms=2,
            living_rooms=1,
            bathrooms=1,
            kitchen_type="مدرن",
            construction_year=1400,
            parking=True,
            elevator=True,
            storage=True,
            quality="خوب",
            owner_player_id=seller.player_id,
        )
        await session.commit()
    return seller, buyer, house


@pytest.mark.asyncio
async def test_divar_accepts_only_real_supported_assets_and_blocks_duplicates(services):
    seller, buyer, house = await _players_and_house(services)
    assert SUPPORTED_ASSET_TYPES == (ASSET_TYPE_HOUSE, ASSET_TYPE_LAND, ASSET_TYPE_CAR)

    with pytest.raises(MarketplaceAssetNotOwnedError):
        await services.divar.create_listing(buyer.player_id, ASSET_TYPE_HOUSE, house.id, 100)
    with pytest.raises(MarketplaceInvalidPriceError):
        await services.divar.create_listing(seller.player_id, ASSET_TYPE_HOUSE, house.id, 0)

    await services.divar.create_listing(seller.player_id, ASSET_TYPE_HOUSE, house.id, 10_000)
    with pytest.raises(MarketplaceListingAlreadyExistsError):
        await services.divar.create_listing(seller.player_id, ASSET_TYPE_HOUSE, house.id, 11_000)


@pytest.mark.asyncio
async def test_divar_search_is_filtered_and_hydrates_the_real_house(services):
    seller, buyer, house = await _players_and_house(services)
    listing = await services.divar.create_listing(
        seller.player_id, ASSET_TYPE_HOUSE, house.id, 15_000
    )

    criteria = MarketplaceSearchCriteria(
        asset_type=ASSET_TYPE_HOUSE,
        city="تهران",
        min_area_sqm=100,
        max_area_sqm=130,
        bedrooms=2,
        min_price=10_000,
        max_price=20_000,
    )
    result = await services.divar.search(criteria, page=0, page_size=1)
    assert result.total == 1
    assert result.listings[0].id == listing.listing.id
    assert result.listings[0].house is not None
    assert result.listings[0].house.id == house.id

    assert parse_search_query("خانه تهران ۲ خواب ۱۰۰ تا ۲۰۰ متر").bedrooms == 2
    assert parse_range_input("۷.۵ میلیارد") == (7_500_000_000, 7_500_000_000)


@pytest.mark.asyncio
async def test_divar_purchase_credits_seller_transfers_asset_and_keeps_history(services):
    seller, buyer, house = await _players_and_house(services)
    await services.money.add_money(buyer.player_id, 20_000)
    listing = await services.divar.create_listing(
        seller.player_id, ASSET_TYPE_HOUSE, house.id, 12_000
    )

    result = await services.divar.purchase(buyer.player_id, listing.listing.id)
    assert result.listing.status == LISTING_STATUS_SOLD
    assert result.listing.buyer_player_id == buyer.player_id
    assert await services.money.get_balance(seller.player_id) == 12_000
    assert await services.money.get_balance(buyer.player_id) == 8_000

    async with services.players._session_factory() as session:  # noqa: SLF001
        transferred = await HouseRepository(session).get_by_id(house.id)
        assert transferred is not None and transferred.owner_player_id == buyer.player_id
    assert (await services.divar.search()).total == 0
    assert (await services.divar.get_listing(listing.listing.id)).status == LISTING_STATUS_SOLD


@pytest.mark.asyncio
async def test_divar_failed_purchase_does_not_move_money_or_ownership(services):
    seller, buyer, house = await _players_and_house(services)
    listing = await services.divar.create_listing(
        seller.player_id, ASSET_TYPE_HOUSE, house.id, 12_000
    )

    with pytest.raises(InsufficientFundsError):
        await services.divar.purchase(buyer.player_id, listing.listing.id)
    assert await services.money.get_balance(seller.player_id) == 0
    assert await services.money.get_balance(buyer.player_id) == 0
    detail = await services.divar.get_listing(listing.listing.id)
    assert detail.is_active


@pytest.mark.asyncio
async def test_concurrent_divar_buyers_have_one_winner(services):
    seller, buyer_one, house = await _players_and_house(services)
    buyer_two = await services.players.register_or_get(
        telegram_user_id=7103, username="buyer2", display_name="خریدار دوم"
    )
    await services.money.add_money(buyer_one.player_id, 100)
    await services.money.add_money(buyer_two.player_id, 100)
    listing = await services.divar.create_listing(
        seller.player_id, ASSET_TYPE_HOUSE, house.id, 100
    )

    async def buy(player_id: int):
        try:
            return await services.divar.purchase(player_id, listing.listing.id)
        except Exception as exc:  # the loser gets a safe domain conflict
            return exc

    outcomes = await asyncio.gather(buy(buyer_one.player_id), buy(buyer_two.player_id))
    assert sum(not isinstance(outcome, Exception) for outcome in outcomes) == 1
    assert await services.money.get_balance(seller.player_id) == 100
    balance_one = await services.money.get_balance(buyer_one.player_id)
    balance_two = await services.money.get_balance(buyer_two.player_id)
    assert balance_one + balance_two == 100


@pytest.mark.asyncio
async def test_seller_cannot_buy_own_divar_listing(services):
    seller, buyer, house = await _players_and_house(services)
    listing = await services.divar.create_listing(
        seller.player_id, ASSET_TYPE_HOUSE, house.id, 100
    )
    with pytest.raises(MarketplaceCannotBuyOwnListingError):
        await services.divar.purchase(seller.player_id, listing.listing.id)


async def _players_and_cars(services, *, two_cars: bool = False):
    seller = await services.players.register_or_get(
        telegram_user_id=7201 if two_cars else 7211,
        username="carseller2" if two_cars else "carseller",
        display_name="فروشنده ماشین",
    )
    buyer = await services.players.register_or_get(
        telegram_user_id=7202 if two_cars else 7212,
        username="carbuyer2" if two_cars else "carbuyer",
        display_name="خریدار ماشین",
    )
    price = 780_000_000 + (700_000_000 if two_cars else 0)
    await services.money.add_money(seller.player_id, price)
    first = await services.vehicles.purchase(seller.player_id, 1)
    second = None
    if two_cars:
        second = await services.vehicles.purchase(seller.player_id, 2)
    return seller, buyer, first.ownership, second.ownership if second else None


@pytest.mark.asyncio
async def test_divar_car_assets_are_owned_real_rows_and_searchable(services):
    seller, buyer, first, second = await _players_and_cars(services, two_cars=True)
    owned = await services.divar.get_owned_assets(seller.player_id)
    assert {
        (asset.asset_type, asset.asset_id) for asset in owned
    } == {
        (ASSET_TYPE_CAR, first.ownership_id),
        (ASSET_TYPE_CAR, second.ownership_id),
    }

    first_listing = await services.divar.create_listing(
        seller.player_id, ASSET_TYPE_CAR, first.ownership_id, 500_000_000
    )
    second_listing = await services.divar.create_listing(
        seller.player_id, ASSET_TYPE_CAR, second.ownership_id, 600_000_000
    )
    assert first_listing.listing.vehicle is not None
    assert first_listing.listing.vehicle.ownership_id == first.ownership_id
    with pytest.raises(MarketplaceListingAlreadyExistsError):
        await services.divar.create_listing(
            seller.player_id, ASSET_TYPE_CAR, first.ownership_id, 550_000_000
        )
    with pytest.raises(MarketplaceAssetNotOwnedError):
        await services.divar.create_listing(
            buyer.player_id, ASSET_TYPE_CAR, first.ownership_id, 550_000_000
        )

    page = await services.divar.search(
        MarketplaceSearchCriteria(asset_type=ASSET_TYPE_CAR), page=0, page_size=1
    )
    assert page.total == 2 and len(page.listings) == 1 and page.has_next
    next_page = await services.divar.search(
        MarketplaceSearchCriteria(asset_type=ASSET_TYPE_CAR), page=1, page_size=1
    )
    assert len(next_page.listings) == 1 and not next_page.has_next

    parsed = parse_search_query("ماشین پراید")
    assert parsed.asset_type == ASSET_TYPE_CAR
    assert (await services.divar.search(parsed, page_size=10)).total == 2
    price_filtered = await services.divar.search(
        MarketplaceSearchCriteria(
            asset_type=ASSET_TYPE_CAR,
            min_price=550_000_000,
            max_price=650_000_000,
        )
    )
    assert price_filtered.total == 1
    assert price_filtered.listings[0].id == second_listing.listing.id


@pytest.mark.asyncio
async def test_divar_car_purchase_is_atomic_transfers_ownership_and_closes_listing(services):
    seller, buyer, ownership, _ = await _players_and_cars(services)
    listing = await services.divar.create_listing(
        seller.player_id, ASSET_TYPE_CAR, ownership.ownership_id, 500_000_000
    )
    await services.money.add_money(buyer.player_id, 500_000_000)

    result = await services.divar.purchase(buyer.player_id, listing.listing.id)
    assert result.listing.status == LISTING_STATUS_SOLD
    assert result.listing.vehicle is not None
    assert result.listing.vehicle.owner_player_id == buyer.player_id
    assert await services.money.get_balance(seller.player_id) == 500_000_000
    assert await services.money.get_balance(buyer.player_id) == 0
    assert await services.vehicles.get_owned_vehicle(
        buyer.player_id, ownership.ownership_id
    )
    assert await services.vehicles.get_owned_vehicles(seller.player_id) == []
    assert (await services.divar.search()).total == 0

    with pytest.raises(MarketplaceListingNotActiveError):
        await services.divar.purchase(buyer.player_id, listing.listing.id)
