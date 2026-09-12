"""Housing system service tests — ownership, P2P sale, P2P rent, transfers.

These run the full real stack (service -> repository -> SQLite) with no
mocks, so every assertion checks actual persisted game state.
"""

from __future__ import annotations

from datetime import timezone

import pytest
from sqlalchemy import select

from app.core import constants
from app.game.housing.construction_year import current_iranian_year
from app.database.models.house_listing import HouseListing
from app.database.models.house_sale import HouseSale
from app.database.models.house_transaction import HouseTransaction
from app.database.models.rental_contract import RentalContract
from app.game.shared.errors import InsufficientFundsError, PlayerNotFoundError
from app.services.housing_service import (
    AlreadyRentingError,
    CannotBuyOwnHouseError,
    CannotRentOwnHouseError,
    ContractNotFoundError,
    HouseAlreadyListedError,
    HouseNotAvailableError,
    HouseNotFoundError,
    HouseRentedOutError,
    NotContractPartyError,
    NotHouseOwnerError,
    NotListedForRentError,
    NotListedForSaleError,
    PriceOutOfBoundsError,
)

# Budgets sized so any starter-market house is affordable — the tests target
# the transaction logic, not the price ladder.
BUYER_BUDGET = 50_000_000_000      # 50 billion Toman
TENANT_BUDGET = 20_000_000_000     # 20 billion Toman


async def _give_money(services, player_id: int, amount: int) -> None:
    from app.database.repositories.player_repository import PlayerRepository

    async with services.players._session_factory() as session:
        await PlayerRepository(session).add_money(player_id, amount)
        await session.commit()


async def _balance(services, player_id: int) -> int:
    return await services.money.get_balance(player_id)


@pytest.fixture
async def seeded(services):
    """Service registry with the starter market seeded."""
    houses = await services.housing.ensure_initial_houses()
    return services, houses


# --- Seeding & catalog --------------------------------------------------------------


async def test_seed_creates_market_houses(seeded):
    services, houses = seeded
    assert len(houses) >= constants.HOUSING_SEED_COUNT


async def test_seed_is_idempotent(services):
    first = await services.housing.ensure_initial_houses()
    second = await services.housing.ensure_initial_houses()
    assert len(first) == len(second)


async def test_every_house_has_unique_id_and_full_properties(seeded):
    services, houses = seeded
    ids = [h.id for h in houses]
    assert len(ids) == len(set(ids))  # unique IDs

    for house in houses:
        assert house.city
        assert house.neighborhood
        assert house.area_sqm > 0
        assert house.bedrooms >= 1
        assert house.living_rooms >= 1
        assert house.bathrooms >= 1
        assert house.kitchen_type in ("مدرن", "معمولی", "قدیمی")
        assert 1330 <= house.construction_year <= current_iranian_year()
        assert isinstance(house.parking, bool)
        assert isinstance(house.elevator, bool)
        assert isinstance(house.storage, bool)
        assert house.quality in ("عالی", "خوب", "متوسط", "ضعیف")
        assert house.owner_player_id is None  # starter market houses are unowned


async def test_house_not_found_error(seeded):
    services, _ = seeded
    with pytest.raises(HouseNotFoundError):
        await services.housing.get_house(99999)


# --- Buying from the system market -----------------------------------------------------


async def test_buy_from_market_transfers_money_and_ownership(seeded, register):
    services, houses = seeded
    player = await register(tg_id=1001)
    await _give_money(services, player.player_id, BUYER_BUDGET)

    target = houses[0]
    expected = await services.housing.get_house_info(target.id)

    result = await services.housing.buy_from_market(player.player_id, target.id)

    assert result.price == expected.market_value
    assert result.house.owner_player_id == player.player_id
    assert result.balance_after == BUYER_BUDGET - result.price

    # Ownership persisted
    info = await services.housing.get_house_info(target.id)
    assert info.house.owner_player_id == player.player_id

    # Sale + transaction audit trail persisted
    async with services.players._session_factory() as session:
        sales = (
            (await session.execute(select(HouseSale).where(HouseSale.house_id == target.id)))
            .scalars()
            .all()
        )
        assert len(sales) == 1
        assert sales[0].buyer_player_id == player.player_id
        assert sales[0].seller_player_id is None  # system market

        txs = (
            (
                await session.execute(
                    select(HouseTransaction).where(
                        HouseTransaction.house_id == target.id,
                        HouseTransaction.transaction_type == "market_purchase",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(txs) == 1
        assert txs[0].amount == result.price


async def test_buy_from_market_without_money_fails(seeded, register):
    services, houses = seeded
    player = await register(tg_id=1002)  # starting money = 0

    with pytest.raises(InsufficientFundsError):
        await services.housing.buy_from_market(player.player_id, houses[0].id)

    # Nothing changed
    info = await services.housing.get_house_info(houses[0].id)
    assert info.house.owner_player_id is None
    assert await _balance(services, player.player_id) == 0


async def test_buy_owned_house_is_rejected(seeded, register):
    services, houses = seeded
    player = await register(tg_id=1003)
    await _give_money(services, player.player_id, BUYER_BUDGET)
    await services.housing.buy_from_market(player.player_id, houses[1].id)

    with pytest.raises(HouseNotAvailableError):
        await services.housing.buy_from_market(player.player_id, houses[1].id)


async def test_buying_grants_xp_via_level_service(seeded, register):
    services, houses = seeded
    player = await register(tg_id=1004)
    await _give_money(services, player.player_id, BUYER_BUDGET)

    result = await services.housing.buy_from_market(player.player_id, houses[2].id)

    expected_xp = max(
        constants.HOUSING_PURCHASE_XP_MIN,
        min(
            constants.HOUSING_PURCHASE_XP_MAX,
            result.price // constants.HOUSING_PURCHASE_XP_DIVISOR,
        ),
    )
    assert result.xp_granted == expected_xp

    history = await services.levels.get_xp_history(player.player_id)
    assert any(t.reason == constants.HOUSING_PURCHASE_XP_REASON for t in history)

    profile = await services.players.get_profile(1004)
    assert profile.xp >= expected_xp  # level/XP system really progressed


# --- Player-to-player selling ------------------------------------------------------------


async def test_list_for_sale_and_market_visibility(seeded, register):
    services, houses = seeded
    owner = await register(tg_id=1010)
    buyer = await register(tg_id=1011)
    await _give_money(services, owner.player_id, BUYER_BUDGET)
    await services.housing.buy_from_market(owner.player_id, houses[3].id)

    options = await services.housing.get_sale_options(houses[3].id, owner.player_id)
    price = dict(options.price_options)[1150]
    await services.housing.list_house_for_sale(owner.player_id, houses[3].id, price)

    market_for_buyer = await services.housing.get_available_houses_for_sale(buyer.player_id)
    match = [e for e in market_for_buyer if e.house.id == houses[3].id]
    assert len(match) == 1
    assert match[0].price == price
    assert match[0].seller_player_id == owner.player_id
    assert match[0].seller_name == "علی"

    # The owner does not see their own listing in the market
    market_for_owner = await services.housing.get_available_houses_for_sale(owner.player_id)
    assert all(e.house.id != houses[3].id for e in market_for_owner)


async def test_list_for_sale_requires_ownership(seeded, register):
    services, houses = seeded
    stranger = await register(tg_id=1012)
    with pytest.raises(NotHouseOwnerError):
        await services.housing.list_house_for_sale(stranger.player_id, houses[4].id, 100)


async def test_list_for_sale_price_bounds(seeded, register):
    services, houses = seeded
    owner = await register(tg_id=1013)
    await _give_money(services, owner.player_id, BUYER_BUDGET)
    await services.housing.buy_from_market(owner.player_id, houses[5].id)

    info = await services.housing.get_house_info(houses[5].id)
    market_value = info.market_value

    with pytest.raises(PriceOutOfBoundsError):
        await services.housing.list_house_for_sale(
            owner.player_id,
            houses[5].id,
            market_value * constants.HOUSING_SALE_MIN_PER_MILLE // 1000 - 1,
        )
    with pytest.raises(PriceOutOfBoundsError):
        await services.housing.list_house_for_sale(
            owner.player_id,
            houses[5].id,
            market_value * constants.HOUSING_SALE_MAX_PER_MILLE // 1000 + 1,
        )


async def test_cannot_double_list(seeded, register):
    services, houses = seeded
    owner = await register(tg_id=1014)
    await _give_money(services, owner.player_id, BUYER_BUDGET)
    await services.housing.buy_from_market(owner.player_id, houses[6].id)
    options = await services.housing.get_sale_options(houses[6].id, owner.player_id)
    price = dict(options.price_options)[1000]

    await services.housing.list_house_for_sale(owner.player_id, houses[6].id, price)
    with pytest.raises(HouseAlreadyListedError):
        await services.housing.list_house_for_sale(owner.player_id, houses[6].id, price)


async def test_p2p_sale_moves_money_and_ownership_atomically(seeded, register):
    services, houses = seeded
    owner = await register(tg_id=1015, display_name="فروشنده")
    buyer = await register(tg_id=1016, display_name="خریدار")
    await _give_money(services, owner.player_id, BUYER_BUDGET)
    await _give_money(services, buyer.player_id, BUYER_BUDGET)

    await services.housing.buy_from_market(owner.player_id, houses[7].id)
    options = await services.housing.get_sale_options(houses[7].id, owner.player_id)
    price = dict(options.price_options)[1000]
    await services.housing.list_house_for_sale(owner.player_id, houses[7].id, price)

    owner_before = await _balance(services, owner.player_id)
    buyer_before = await _balance(services, buyer.player_id)

    result = await services.housing.buy_from_player(buyer.player_id, houses[7].id)

    assert result.price == price
    assert result.seller_player_id == owner.player_id

    # Exact money transfer between the two players
    assert await _balance(services, buyer.player_id) == buyer_before - price
    assert await _balance(services, owner.player_id) == owner_before + price

    # Ownership transferred
    info = await services.housing.get_house_info(houses[7].id)
    assert info.house.owner_player_id == buyer.player_id
    assert info.owner_name == "خریدار"

    # Listing closed + audit trail
    async with services.players._session_factory() as session:
        listing = (
            (
                await session.execute(
                    select(HouseListing).where(
                        HouseListing.house_id == houses[7].id,
                        HouseListing.listing_type == "sale",
                    )
                )
            )
            .scalars()
            .one()
        )
        assert listing.status == "closed"
        assert listing.closed_at is not None

        sales = (
            (await session.execute(select(HouseSale).where(HouseSale.house_id == houses[7].id)))
            .scalars()
            .all()
        )
        # Two records: the owner's market purchase + the P2P sale.
        assert len(sales) == 2
        p2p = [s for s in sales if s.seller_player_id == owner.player_id]
        assert len(p2p) == 1
        assert p2p[0].buyer_player_id == buyer.player_id

        tx = (
            (
                await session.execute(
                    select(HouseTransaction).where(
                        HouseTransaction.transaction_type == "player_purchase",
                        HouseTransaction.house_id == houses[7].id,
                    )
                )
            )
            .scalars()
            .one()
        )
        assert tx.payer_player_id == buyer.player_id
        assert tx.payee_player_id == owner.player_id
        assert tx.amount == price


async def test_buyer_cannot_buy_own_house(seeded, register):
    services, houses = seeded
    owner = await register(tg_id=1017)
    await _give_money(services, owner.player_id, BUYER_BUDGET)
    await services.housing.buy_from_market(owner.player_id, houses[8].id)
    options = await services.housing.get_sale_options(houses[8].id, owner.player_id)
    await services.housing.list_house_for_sale(
        owner.player_id, houses[8].id, dict(options.price_options)[1000]
    )
    with pytest.raises(CannotBuyOwnHouseError):
        await services.housing.buy_from_player(owner.player_id, houses[8].id)


async def test_buy_unlisted_player_house_fails(seeded, register):
    services, houses = seeded
    owner = await register(tg_id=1018)
    buyer = await register(tg_id=1019)
    await _give_money(services, owner.player_id, BUYER_BUDGET)
    await services.housing.buy_from_market(owner.player_id, houses[9].id)

    with pytest.raises(NotListedForSaleError):
        await services.housing.buy_from_player(buyer.player_id, houses[9].id)


async def test_cancel_sale_listing(seeded, register):
    services, houses = seeded
    owner = await register(tg_id=1020)
    await _give_money(services, owner.player_id, BUYER_BUDGET)
    await services.housing.buy_from_market(owner.player_id, houses[10].id)
    options = await services.housing.get_sale_options(houses[10].id, owner.player_id)
    await services.housing.list_house_for_sale(
        owner.player_id, houses[10].id, dict(options.price_options)[1000]
    )

    await services.housing.cancel_sale_listing(owner.player_id, houses[10].id)

    stranger = await register(tg_id=1021)
    market = await services.housing.get_available_houses_for_sale(stranger.player_id)
    assert all(e.house.id != houses[10].id for e in market)

    # The house stays with the owner
    info = await services.housing.get_house_info(houses[10].id)
    assert info.house.owner_player_id == owner.player_id


# --- Renting out / renting (player-to-player) ----------------------------------------------


async def test_list_for_rent_and_rentals_visibility(seeded, register):
    services, houses = seeded
    owner = await register(tg_id=1030, display_name="صاحبخانه")
    tenant = await register(tg_id=1031)
    await _give_money(services, owner.player_id, BUYER_BUDGET)
    await services.housing.buy_from_market(owner.player_id, houses[11].id)

    options = await services.housing.get_rent_options(houses[11].id, owner.player_id)
    deposit_pct, deposit, rent = options.options[1]
    await services.housing.list_house_for_rent(owner.player_id, houses[11].id, rent, deposit)

    rentals = await services.housing.get_available_rentals(tenant.player_id)
    match = [e for e in rentals if e.house.id == houses[11].id]
    assert len(match) == 1
    assert match[0].monthly_rent == rent
    assert match[0].deposit == deposit
    assert match[0].owner_name == "صاحبخانه"

    # The owner does not see their own listing
    own = await services.housing.get_available_rentals(owner.player_id)
    assert all(e.house.id != houses[11].id for e in own)


async def test_list_for_rent_requires_ownership(seeded, register):
    services, houses = seeded
    stranger = await register(tg_id=1032)
    with pytest.raises(NotHouseOwnerError):
        await services.housing.list_house_for_rent(stranger.player_id, houses[12].id, 1_000_000)


async def test_rent_price_bounds(seeded, register):
    services, houses = seeded
    owner = await register(tg_id=1033)
    await _give_money(services, owner.player_id, BUYER_BUDGET)
    await services.housing.buy_from_market(owner.player_id, houses[13].id)

    info = await services.housing.get_house_info(houses[13].id)
    market_value = info.market_value
    rent_max = market_value * constants.HOUSING_RENT_MAX_PER_MILLE // 1000

    with pytest.raises(PriceOutOfBoundsError):
        await services.housing.list_house_for_rent(
            owner.player_id, houses[13].id, rent_max + max(1, market_value // 10), 0
        )
    with pytest.raises(PriceOutOfBoundsError):
        await services.housing.list_house_for_rent(
            owner.player_id,
            houses[13].id,
            rent_max // 2,
            market_value * constants.HOUSING_DEPOSIT_MAX_PER_MILLE // 1000 + 1,
        )


async def test_p2p_rent_creates_contract_and_moves_deposit(seeded, register):
    services, houses = seeded
    owner = await register(tg_id=1034, display_name="موچر")
    tenant = await register(tg_id=1035, display_name="مستاجر")
    await _give_money(services, owner.player_id, BUYER_BUDGET)
    await _give_money(services, tenant.player_id, TENANT_BUDGET)

    await services.housing.buy_from_market(owner.player_id, houses[14].id)
    options = await services.housing.get_rent_options(houses[14].id, owner.player_id)
    deposit_pct, deposit, rent = options.options[2]
    await services.housing.list_house_for_rent(owner.player_id, houses[14].id, rent, deposit)

    owner_before = await _balance(services, owner.player_id)
    tenant_before = await _balance(services, tenant.player_id)

    contract = await services.housing.rent_house(tenant.player_id, houses[14].id)

    # Deposit moved tenant -> owner
    assert await _balance(services, tenant.player_id) == tenant_before - deposit
    assert await _balance(services, owner.player_id) == owner_before + deposit

    # Contract stores tenant and owner information
    assert contract.tenant_player_id == tenant.player_id
    assert contract.owner_player_id == owner.player_id
    assert contract.monthly_rent == rent
    assert contract.deposit == deposit
    assert contract.is_active is True

    # Listing closed; contract persisted
    async with services.players._session_factory() as session:
        listing = (
            (
                await session.execute(
                    select(HouseListing).where(
                        HouseListing.house_id == houses[14].id,
                        HouseListing.listing_type == "rent",
                    )
                )
            )
            .scalars()
            .one()
        )
        assert listing.status == "closed"

        row = (
            (
                await session.execute(
                    select(RentalContract).where(RentalContract.house_id == houses[14].id)
                )
            )
            .scalars()
            .one()
        )
        assert row.tenant_player_id == tenant.player_id
        assert row.owner_player_id == owner.player_id
        assert row.is_active is True

        tx = (
            (
                await session.execute(
                    select(HouseTransaction).where(
                        HouseTransaction.transaction_type == "rent_deposit",
                        HouseTransaction.house_id == houses[14].id,
                    )
                )
            )
            .scalars()
            .one()
        )
        assert tx.amount == deposit
        assert tx.payer_player_id == tenant.player_id
        assert tx.payee_player_id == owner.player_id

    # No longer in the rentals list
    rentals = await services.housing.get_available_rentals(tenant.player_id)
    assert all(e.house.id != houses[14].id for e in rentals)


async def test_rent_without_deposit_needs_no_money(seeded, register):
    services, houses = seeded
    owner = await register(tg_id=1045)
    tenant = await register(tg_id=1046)  # zero balance

    await _give_money(services, owner.player_id, BUYER_BUDGET)
    await services.housing.buy_from_market(owner.player_id, houses[28].id)
    options = await services.housing.get_rent_options(houses[28].id, owner.player_id)
    _, deposit, rent = options.options[0]
    assert deposit == 0
    await services.housing.list_house_for_rent(owner.player_id, houses[28].id, rent, 0)

    contract = await services.housing.rent_house(tenant.player_id, houses[28].id)
    assert contract.deposit == 0
    assert await _balance(services, tenant.player_id) == 0  # nothing was charged


async def test_cannot_rent_own_house(seeded, register):
    services, houses = seeded
    owner = await register(tg_id=1036)
    await _give_money(services, owner.player_id, BUYER_BUDGET)
    await services.housing.buy_from_market(owner.player_id, houses[15].id)
    options = await services.housing.get_rent_options(houses[15].id, owner.player_id)
    _, deposit, rent = options.options[0]
    await services.housing.list_house_for_rent(owner.player_id, houses[15].id, rent, deposit)

    with pytest.raises(CannotRentOwnHouseError):
        await services.housing.rent_house(owner.player_id, houses[15].id)


async def test_cannot_rent_second_house(seeded, register):
    services, houses = seeded
    owner1 = await register(tg_id=1037)
    owner2 = await register(tg_id=1038)
    tenant = await register(tg_id=1039)
    await _give_money(services, owner1.player_id, BUYER_BUDGET)
    await _give_money(services, owner2.player_id, BUYER_BUDGET)
    await _give_money(services, tenant.player_id, TENANT_BUDGET)

    await services.housing.buy_from_market(owner1.player_id, houses[16].id)
    await services.housing.buy_from_market(owner2.player_id, houses[17].id)

    opt1 = await services.housing.get_rent_options(houses[16].id, owner1.player_id)
    _, dep1, rent1 = opt1.options[0]
    await services.housing.list_house_for_rent(owner1.player_id, houses[16].id, rent1, dep1)

    opt2 = await services.housing.get_rent_options(houses[17].id, owner2.player_id)
    _, dep2, rent2 = opt2.options[0]
    await services.housing.list_house_for_rent(owner2.player_id, houses[17].id, rent2, dep2)

    await services.housing.rent_house(tenant.player_id, houses[16].id)
    with pytest.raises(AlreadyRentingError):
        await services.housing.rent_house(tenant.player_id, houses[17].id)


async def test_rent_unlisted_house_fails(seeded, register):
    services, houses = seeded
    tenant = await register(tg_id=1040)
    with pytest.raises(NotListedForRentError):
        await services.housing.rent_house(tenant.player_id, houses[18].id)


# --- Rent payments ------------------------------------------------------------------------


async def test_rent_payment_moves_money_and_advances_due_date(seeded, register):
    services, houses = seeded
    owner = await register(tg_id=1050)
    tenant = await register(tg_id=1051)
    await _give_money(services, owner.player_id, BUYER_BUDGET)
    await _give_money(services, tenant.player_id, TENANT_BUDGET)

    await services.housing.buy_from_market(owner.player_id, houses[19].id)
    options = await services.housing.get_rent_options(houses[19].id, owner.player_id)
    _, deposit, rent = options.options[0]
    await services.housing.list_house_for_rent(owner.player_id, houses[19].id, rent, 0)
    contract = await services.housing.rent_house(tenant.player_id, houses[19].id)

    owner_before = await _balance(services, owner.player_id)
    tenant_before = await _balance(services, tenant.player_id)

    payment = await services.housing.pay_rent(tenant.player_id, contract.id)

    assert payment.amount == rent
    assert payment.tenant_balance_after == tenant_before - rent
    assert payment.owner_balance_after == owner_before + rent
    assert payment.next_due_at > contract.next_due_at

    async with services.players._session_factory() as session:
        tx = (
            (
                await session.execute(
                    select(HouseTransaction).where(
                        HouseTransaction.transaction_type == "rent_payment",
                        HouseTransaction.contract_id == contract.id,
                    )
                )
            )
            .scalars()
            .one()
        )
        assert tx.amount == rent

        row = await session.get(RentalContract, contract.id)
        # SQLite returns naive UTC datetimes — compare the instant, not the tz.
        assert row.next_due_at.replace(tzinfo=timezone.utc) == payment.next_due_at


async def test_rent_payment_requires_tenant(seeded, register):
    services, houses = seeded
    owner = await register(tg_id=1052)
    tenant = await register(tg_id=1053)
    stranger = await register(tg_id=1054)
    await _give_money(services, owner.player_id, BUYER_BUDGET)
    await _give_money(services, tenant.player_id, TENANT_BUDGET)

    await services.housing.buy_from_market(owner.player_id, houses[20].id)
    options = await services.housing.get_rent_options(houses[20].id, owner.player_id)
    _, deposit, rent = options.options[0]
    await services.housing.list_house_for_rent(owner.player_id, houses[20].id, rent, 0)
    contract = await services.housing.rent_house(tenant.player_id, houses[20].id)

    with pytest.raises(NotContractPartyError):
        await services.housing.pay_rent(stranger.player_id, contract.id)


async def test_rent_payment_without_money_fails(seeded, register):
    services, houses = seeded
    owner = await register(tg_id=1055)
    tenant = await register(tg_id=1056)
    await _give_money(services, owner.player_id, BUYER_BUDGET)
    await _give_money(services, tenant.player_id, TENANT_BUDGET)

    await services.housing.buy_from_market(owner.player_id, houses[21].id)
    options = await services.housing.get_rent_options(houses[21].id, owner.player_id)
    _, deposit, rent = options.options[0]
    await services.housing.list_house_for_rent(owner.player_id, houses[21].id, rent, 0)
    contract = await services.housing.rent_house(tenant.player_id, houses[21].id)

    # Drain the tenant's wallet below the monthly rent.
    balance = await _balance(services, tenant.player_id)
    await services.money.remove_money(tenant.player_id, balance - rent + 1)
    owner_before = await _balance(services, owner.player_id)

    with pytest.raises(InsufficientFundsError):
        await services.housing.pay_rent(tenant.player_id, contract.id)

    # Owner received nothing.
    assert await _balance(services, owner.player_id) == owner_before


async def test_pay_nonexistent_or_ended_contract_fails(seeded, register):
    services, _ = seeded
    tenant = await register(tg_id=1057)
    with pytest.raises(ContractNotFoundError):
        await services.housing.pay_rent(tenant.player_id, 424242)


# --- Ending contracts ---------------------------------------------------------------------


async def test_tenant_can_end_contract_and_relist_house(seeded, register):
    services, houses = seeded
    owner = await register(tg_id=1060)
    tenant = await register(tg_id=1061)
    await _give_money(services, owner.player_id, BUYER_BUDGET)
    await _give_money(services, tenant.player_id, TENANT_BUDGET)

    await services.housing.buy_from_market(owner.player_id, houses[22].id)
    options = await services.housing.get_rent_options(houses[22].id, owner.player_id)
    _, deposit, rent = options.options[0]
    await services.housing.list_house_for_rent(owner.player_id, houses[22].id, rent, 0)
    contract = await services.housing.rent_house(tenant.player_id, houses[22].id)

    # While rented out, selling is blocked.
    with pytest.raises(HouseRentedOutError):
        await services.housing.list_house_for_sale(
            owner.player_id, houses[22].id, contract.monthly_rent * 1000
        )

    result = await services.housing.end_rental_contract(tenant.player_id, contract.id)
    assert result.tenant_player_id == tenant.player_id

    async with services.players._session_factory() as session:
        row = await session.get(RentalContract, contract.id)
        assert row.is_active is False
        assert row.ended_at is not None

    # House is free again: listing for sale now works.
    sale_options = await services.housing.get_sale_options(houses[22].id, owner.player_id)
    price = dict(sale_options.price_options)[1000]
    await services.housing.list_house_for_sale(owner.player_id, houses[22].id, price)


async def test_owner_can_end_contract(seeded, register):
    services, houses = seeded
    owner = await register(tg_id=1062)
    tenant = await register(tg_id=1063)
    await _give_money(services, owner.player_id, BUYER_BUDGET)
    await _give_money(services, tenant.player_id, TENANT_BUDGET)

    await services.housing.buy_from_market(owner.player_id, houses[23].id)
    options = await services.housing.get_rent_options(houses[23].id, owner.player_id)
    _, deposit, rent = options.options[0]
    await services.housing.list_house_for_rent(owner.player_id, houses[23].id, rent, 0)
    contract = await services.housing.rent_house(tenant.player_id, houses[23].id)

    await services.housing.end_rental_contract(owner.player_id, contract.id)

    contracts = await services.housing.get_my_rental_contracts(tenant.player_id)
    assert contracts == []


async def test_stranger_cannot_end_contract(seeded, register):
    services, houses = seeded
    owner = await register(tg_id=1064)
    tenant = await register(tg_id=1065)
    stranger = await register(tg_id=1066)
    await _give_money(services, owner.player_id, BUYER_BUDGET)
    await _give_money(services, tenant.player_id, TENANT_BUDGET)

    await services.housing.buy_from_market(owner.player_id, houses[24].id)
    options = await services.housing.get_rent_options(houses[24].id, owner.player_id)
    _, deposit, rent = options.options[0]
    await services.housing.list_house_for_rent(owner.player_id, houses[24].id, rent, 0)
    contract = await services.housing.rent_house(tenant.player_id, houses[24].id)

    with pytest.raises(NotContractPartyError):
        await services.housing.end_rental_contract(stranger.player_id, contract.id)


async def test_end_unknown_contract_fails(seeded, register):
    services, _ = seeded
    player = await register(tg_id=1067)
    with pytest.raises(ContractNotFoundError):
        await services.housing.end_rental_contract(player.player_id, 999999)


# --- Assets & integration --------------------------------------------------------------------


async def test_player_assets_reflect_ownership_and_listings(seeded, register):
    services, houses = seeded
    owner = await register(tg_id=1070)
    tenant = await register(tg_id=1071)
    await _give_money(services, owner.player_id, 2 * BUYER_BUDGET)
    await _give_money(services, tenant.player_id, TENANT_BUDGET)

    first = await services.housing.buy_from_market(owner.player_id, houses[25].id)
    second = await services.housing.buy_from_market(owner.player_id, houses[26].id)

    assets = await services.housing.get_player_assets(owner.player_id)
    assert len(assets.houses) == 2
    assert assets.total_market_value == first.price + second.price

    # List one for sale, rent the other out
    sale_opts = await services.housing.get_sale_options(first.house.id, owner.player_id)
    await services.housing.list_house_for_sale(
        owner.player_id, first.house.id, dict(sale_opts.price_options)[1000]
    )
    rent_opts = await services.housing.get_rent_options(second.house.id, owner.player_id)
    _, deposit, rent = rent_opts.options[0]
    await services.housing.list_house_for_rent(owner.player_id, second.house.id, rent, deposit)
    await services.housing.rent_house(tenant.player_id, second.house.id)

    assets = await services.housing.get_player_assets(owner.player_id)
    assert len(assets.active_sale_listings) == 1
    assert assets.active_sale_listings[0].house_id == first.house.id
    # The rent listing closed the moment the tenant signed the contract.
    assert len(assets.active_rent_listings) == 0
    assert len(assets.rented_out_contracts) == 1
    assert assets.rented_out_contracts[0].tenant_player_id == tenant.player_id
    assert assets.rented_out_contracts[0].house_label  # human-readable label


async def test_assets_require_registered_player(seeded):
    services, _ = seeded
    with pytest.raises(PlayerNotFoundError):
        await services.housing.get_player_assets(987654)


async def test_house_info_shows_tenant_and_owner(seeded, register):
    services, houses = seeded
    owner = await register(tg_id=1072, display_name="مالک")
    tenant = await register(tg_id=1073, display_name="کرایه‌چی")
    await _give_money(services, owner.player_id, BUYER_BUDGET)
    await _give_money(services, tenant.player_id, TENANT_BUDGET)

    await services.housing.buy_from_market(owner.player_id, houses[27].id)
    options = await services.housing.get_rent_options(houses[27].id, owner.player_id)
    _, deposit, rent = options.options[1]
    await services.housing.list_house_for_rent(owner.player_id, houses[27].id, rent, deposit)
    await services.housing.rent_house(tenant.player_id, houses[27].id)

    info = await services.housing.get_house_info(
        houses[27].id, viewer_player_id=tenant.player_id
    )
    assert info.owner_name == "مالک"
    assert info.tenant_name == "کرایه‌چی"
    assert info.tenanted_by_me is True
    assert info.contract_id is not None
