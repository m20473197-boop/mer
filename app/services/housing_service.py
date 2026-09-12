"""Housing and Real-Estate service — the transaction boundary of the system.

Use cases:
* System-market browsing and buying (dynamic prices, no stored price).
* Player-to-player selling: list for sale with a chosen price, other players
  buy it — ownership and money move atomically between the two wallets.
* Player-to-player renting: list for rent (monthly rent + Iranian-style
  deposit), other players rent it; rental contracts with monthly payments.
* Player assets (owned houses + total value) and full house information.

There are **no NPC buyers, sellers, landlords or tenants** — every counterparty
is a real player. Money movements reuse the exact atomic wallet primitives the
Wallet system uses (``remove_money_if_enough`` / ``add_money``) inside the same
DB transaction as the ownership change, so the ledger can never drift.

Level/XP integration: buying a house explicitly grants XP through the existing
``LevelService`` (never implicitly) — see ``HOUSING_PURCHASE_XP_*`` constants.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import constants
from app.database.models.house import House
from app.database.models.house_listing import (
    LISTING_RENT,
    LISTING_SALE,
    HouseListing,
)
from app.database.repositories.house_listing_repository import (
    HouseListingRepository,
)
from app.database.repositories.marketplace_listing_repository import (
    MarketplaceListingRepository,
)
from app.database.repositories.house_repository import HouseRepository
from app.database.repositories.house_sale_repository import HouseSaleRepository
from app.database.repositories.house_transaction_repository import (
    HouseTransactionRepository,
)
from app.database.repositories.player_repository import PlayerRepository
from app.database.repositories.rental_contract_repository import (
    RentalContractRepository,
)
from app.game.admin import runtime as admin_runtime
from app.game.housing import pricing
from app.game.marketplace.catalog import ASSET_TYPE_HOUSE
from app.game.housing.dto import (
    EndContractResult,
    HouseData,
    HouseInfoData,
    HouseListingData,
    HouseMarketEntry,
    HouseRentalEntry,
    ListForRentResult,
    ListForSaleResult,
    PlayerAssetsData,
    PurchaseResult,
    RentOptions,
    RentPaymentResult,
    RentalContractData,
    SaleOptions,
)
from app.game.housing.seeding import build_seed_specs
from app.game.shared.errors import DomainError, InsufficientFundsError, PlayerNotFoundError

logger = logging.getLogger(__name__)


# --- Domain errors ------------------------------------------------------------


class HouseNotFoundError(DomainError):
    """The requested house does not exist."""


class NotHouseOwnerError(DomainError):
    """The player does not own this house."""


class HouseNotAvailableError(DomainError):
    """The house is not on the system market (already owned)."""


class NotListedForSaleError(DomainError):
    """The house has no active sale listing."""


class NotListedForRentError(DomainError):
    """The house has no active rent listing."""


class HouseAlreadyListedError(DomainError):
    """The house already has an active listing."""


class HouseRentedOutError(DomainError):
    """The house has an active tenant and cannot be (re)listed."""


class PriceOutOfBoundsError(DomainError):
    """The chosen price is outside the allowed band around the market value."""


class CannotBuyOwnHouseError(DomainError):
    """A player cannot buy the house they already own."""


class CannotRentOwnHouseError(DomainError):
    """A player cannot rent the house they own themselves."""


class AlreadyRentingError(DomainError):
    """The player already rents another house."""


class ContractNotFoundError(DomainError):
    """The rental contract does not exist."""


class NotContractPartyError(DomainError):
    """The player is neither the owner nor the tenant of this contract."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class HousingService:
    """Complete Housing and Real-Estate service."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        level_service=None,
    ) -> None:
        self._session_factory = session_factory
        self._level_service = level_service

    # --- Conversion helpers -------------------------------------------------

    @staticmethod
    def _to_house_dto(house: House) -> HouseData:
        return HouseData(
            id=house.id,
            city=house.city,
            neighborhood=house.neighborhood,
            area_sqm=house.area_sqm,
            bedrooms=house.bedrooms,
            living_rooms=house.living_rooms,
            bathrooms=house.bathrooms,
            kitchen_type=house.kitchen_type,
            construction_year=house.construction_year,
            parking=house.parking,
            elevator=house.elevator,
            storage=house.storage,
            quality=house.quality,
            owner_player_id=house.owner_player_id,
            created_at=house.created_at,
            updated_at=house.updated_at,
            price_override_per_mille=house.price_override_per_mille,
        )

    @staticmethod
    def pricing_input_for_house(house: House) -> pricing.HousePricingInput:
        return pricing.HousePricingInput(
            house_id=house.id,
            city=house.city,
            neighborhood=house.neighborhood,
            area_sqm=house.area_sqm,
            bedrooms=house.bedrooms,
            living_rooms=house.living_rooms,
            bathrooms=house.bathrooms,
            kitchen_type=house.kitchen_type,
            construction_year=house.construction_year,
            parking=house.parking,
            elevator=house.elevator,
            storage=house.storage,
            quality=house.quality,
        )

    def estimate_value(self, house: House) -> int:
        """Dynamic market value of a house (exact integer Toman)."""
        value = pricing.estimate_house_price(
            self.pricing_input_for_house(house),
            market_factor=admin_runtime.effective_market_factor(),
        )
        override = house.price_override_per_mille
        if override:
            value = max(1, value * int(override) // 1000)
        return value

    def estimate_rent(self, house: House) -> int:
        """Dynamic suggested monthly rent (no deposit) for a house."""
        return pricing.estimate_monthly_rent(
            self.pricing_input_for_house(house),
            market_factor=admin_runtime.effective_market_factor(),
        )

    @staticmethod
    def _xp_for_price(price: int) -> int:
        xp = price // admin_runtime.purchase_xp_divisor()
        return max(admin_runtime.purchase_xp_min(), min(admin_runtime.purchase_xp_max(), xp))

    async def _grant_purchase_xp(self, player_id: int, price: int) -> int:
        """Grant XP for a purchase via the existing LevelService (explicit)."""
        if self._level_service is None:
            return 0
        amount = self._xp_for_price(price)
        try:
            await self._level_service.add_xp(
                player_id, amount, reason=constants.HOUSING_PURCHASE_XP_REASON
            )
        except Exception:  # noqa: BLE001 — XP is a bonus, never blocks the purchase
            logger.warning(
                "Could not grant house-purchase XP to player %s", player_id, exc_info=True
            )
            return 0
        return amount

    @staticmethod
    def house_label(house: HouseData | House) -> str:
        """Short human-readable label used in lists and contracts."""
        return f"#{house.id} — {house.city}، {house.neighborhood} ({house.area_sqm} متری)"

    # --- Seeding --------------------------------------------------------------

    async def ensure_initial_houses(self) -> list[HouseData]:
        """Seed the starter system-market houses once (idempotent)."""
        async with self._session_factory() as session:
            repo = HouseRepository(session)
            existing = await repo.count()
            if existing > 0:
                houses = await repo.list_all()
                return [self._to_house_dto(h) for h in houses]

            created: list[HouseData] = []
            for spec in build_seed_specs():
                house = await repo.create(
                    city=spec.city,
                    neighborhood=spec.neighborhood,
                    area_sqm=spec.area_sqm,
                    bedrooms=spec.bedrooms,
                    living_rooms=spec.living_rooms,
                    bathrooms=spec.bathrooms,
                    kitchen_type=spec.kitchen_type,
                    construction_year=spec.construction_year,
                    parking=spec.parking,
                    elevator=spec.elevator,
                    storage=spec.storage,
                    quality=spec.quality,
                    owner_player_id=None,
                )
                created.append(self._to_house_dto(house))
            await session.commit()
            logger.info("Seeded %s starter houses on the system market", len(created))
            return created

    # --- Lookups ----------------------------------------------------------------

    async def get_house(self, house_id: int) -> HouseData:
        async with self._session_factory() as session:
            house = await HouseRepository(session).get_by_id(house_id)
        if house is None:
            raise HouseNotFoundError(f"house_id={house_id} not found")
        return self._to_house_dto(house)

    async def get_house_info(
        self, house_id: int, viewer_player_id: int | None = None
    ) -> HouseInfoData:
        """Everything the «اطلاعات خانه» screen needs."""
        async with self._session_factory() as session:
            house_repo = HouseRepository(session)
            house = await house_repo.get_by_id(house_id)
            if house is None:
                raise HouseNotFoundError(f"house_id={house_id} not found")

            listing_repo = HouseListingRepository(session)
            sale_listing = await listing_repo.get_active_sale_by_house(house_id)
            rent_listing = await listing_repo.get_active_rent_by_house(house_id)
            contract_repo = RentalContractRepository(session)
            contract = await contract_repo.get_active_by_house(house_id)

            owner_name: str | None = None
            if house.owner_player_id is not None:
                owner = await PlayerRepository(session).get_by_id(house.owner_player_id)
                owner_name = owner.display_name if owner else None

            tenant_name: str | None = None
            if contract is not None:
                tenant = await PlayerRepository(session).get_by_id(contract.tenant_player_id)
                tenant_name = tenant.display_name if tenant else None

            info = HouseInfoData(
                house=self._to_house_dto(house),
                market_value=self.estimate_value(house),
                estimated_rent=self.estimate_rent(house),
                owner_name=owner_name,
                active_sale_price=sale_listing.price if sale_listing else None,
                active_rent=(
                    (rent_listing.price, rent_listing.deposit) if rent_listing else None
                ),
                tenant_name=tenant_name,
                tenanted_by_me=(
                    viewer_player_id is not None
                    and contract is not None
                    and contract.tenant_player_id == viewer_player_id
                ),
                contract_id=contract.id if contract is not None else None,
            )
        return info

    async def get_available_houses_for_sale(
        self, viewer_player_id: int | None = None
    ) -> list[HouseMarketEntry]:
        """All purchasable houses: system market + other players' sale listings.

        The viewer's own listings are excluded (you cannot buy your own
        house), so the screen only shows actionable offers.
        """
        async with self._session_factory() as session:
            house_repo = HouseRepository(session)
            listing_repo = HouseListingRepository(session)
            player_repo = PlayerRepository(session)

            entries: list[HouseMarketEntry] = []

            # System market: ownerless houses, priced dynamically right now.
            for house in await house_repo.list_unowned():
                price = self.estimate_value(house)
                entries.append(
                    HouseMarketEntry(
                        house=self._to_house_dto(house),
                        price=price,
                        market_value=price,
                        seller_player_id=None,
                        seller_name=None,
                    )
                )

            # Player listings (excluding the viewer's own).
            for listing in await listing_repo.list_active_sales():
                if viewer_player_id is not None and listing.owner_player_id == viewer_player_id:
                    continue
                house = await house_repo.get_by_id(listing.house_id)
                if house is None:
                    continue
                seller = (
                    await player_repo.get_by_id(listing.owner_player_id)
                    if listing.owner_player_id is not None
                    else None
                )
                value = self.estimate_value(house)
                entries.append(
                    HouseMarketEntry(
                        house=self._to_house_dto(house),
                        price=listing.price,
                        market_value=value,
                        seller_player_id=listing.owner_player_id,
                        seller_name=seller.display_name if seller else None,
                    )
                )

            entries.sort(key=lambda e: e.price)
            return entries

    async def get_available_rentals(
        self, viewer_player_id: int | None = None
    ) -> list[HouseRentalEntry]:
        """All active rent listings (the viewer's own are excluded)."""
        async with self._session_factory() as session:
            listing_repo = HouseListingRepository(session)
            house_repo = HouseRepository(session)
            player_repo = PlayerRepository(session)

            entries: list[HouseRentalEntry] = []
            for listing in await listing_repo.list_active_rents():
                if viewer_player_id is not None and listing.owner_player_id == viewer_player_id:
                    continue
                house = await house_repo.get_by_id(listing.house_id)
                if house is None:
                    continue
                owner = (
                    await player_repo.get_by_id(listing.owner_player_id)
                    if listing.owner_player_id is not None
                    else None
                )
                entries.append(
                    HouseRentalEntry(
                        house=self._to_house_dto(house),
                        monthly_rent=listing.price,
                        deposit=listing.deposit,
                        owner_player_id=listing.owner_player_id or 0,
                        owner_name=owner.display_name if owner else "؟",
                    )
                )
            entries.sort(key=lambda e: e.monthly_rent)
            return entries

    # --- Player assets ------------------------------------------------------------

    async def get_player_assets(self, player_id: int) -> PlayerAssetsData:
        """The player's owned houses as assets, with live values and listings."""
        async with self._session_factory() as session:
            house_repo = HouseRepository(session)
            listing_repo = HouseListingRepository(session)
            contract_repo = RentalContractRepository(session)
            player_repo = PlayerRepository(session)

            if not await player_repo.exists(player_id):
                raise PlayerNotFoundError(f"player_id={player_id} not found")

            houses = await house_repo.list_by_owner(player_id)
            listings = await listing_repo.list_active_by_owner(player_id)
            contracts = await contract_repo.list_active_by_owner(player_id)

            house_dtos = [self._to_house_dto(h) for h in houses]
            total_value = sum(self.estimate_value(h) for h in houses)

            sale_listings = [
                self._to_listing_dto(l) for l in listings if l.listing_type == LISTING_SALE
            ]
            rent_listings = [
                self._to_listing_dto(l) for l in listings if l.listing_type == LISTING_RENT
            ]

            contract_dtos: list[RentalContractData] = []
            for contract in contracts:
                house = await house_repo.get_by_id(contract.house_id)
                tenant = await player_repo.get_by_id(contract.tenant_player_id)
                contract_dtos.append(
                    RentalContractData(
                        id=contract.id,
                        house_id=contract.house_id,
                        owner_player_id=contract.owner_player_id,
                        tenant_player_id=contract.tenant_player_id,
                        monthly_rent=contract.monthly_rent,
                        deposit=contract.deposit,
                        started_at=contract.started_at,
                        next_due_at=contract.next_due_at,
                        is_active=contract.is_active,
                        ended_at=contract.ended_at,
                        created_at=contract.created_at,
                        house_label=(
                            self.house_label(self._to_house_dto(house)) if house else ""
                        ),
                        tenant_name=tenant.display_name if tenant else "؟",
                    )
                )

            return PlayerAssetsData(
                player_id=player_id,
                houses=tuple(house_dtos),
                total_market_value=total_value,
                active_sale_listings=tuple(sale_listings),
                active_rent_listings=tuple(rent_listings),
                rented_out_contracts=tuple(contract_dtos),
            )

    @staticmethod
    def _to_listing_dto(listing: HouseListing) -> HouseListingData:
        return HouseListingData(
            id=listing.id,
            house_id=listing.house_id,
            owner_player_id=listing.owner_player_id,
            listing_type=listing.listing_type,
            price=listing.price,
            deposit=listing.deposit,
            status=listing.status,
            created_at=listing.created_at,
            closed_at=listing.closed_at,
        )

    # --- Price/rent presets (button options) --------------------------------------

    async def get_sale_options(self, house_id: int, seller_player_id: int) -> SaleOptions:
        """Suggested asking prices around the dynamic value (button presets)."""
        async with self._session_factory() as session:
            house = await HouseRepository(session).get_by_id(house_id)
            if house is None:
                raise HouseNotFoundError(f"house_id={house_id} not found")
            if house.owner_player_id != seller_player_id:
                raise NotHouseOwnerError(f"house {house_id} not owned by {seller_player_id}")
            value = self.estimate_value(house)

        options = tuple(
            (
                per_mille,
                max(
                    pricing.PRICE_ROUNDING_STEP,
                    value * per_mille // 1000
                    // pricing.PRICE_ROUNDING_STEP
                    * pricing.PRICE_ROUNDING_STEP,
                ),
            )
            for per_mille in constants.HOUSING_SALE_PRICE_PRESETS_PER_MILLE
        )
        return SaleOptions(house_id=house_id, market_value=value, price_options=options)

    async def get_rent_options(self, house_id: int, owner_player_id: int) -> RentOptions:
        """Suggested (deposit%, deposit, monthly rent) presets for a house."""
        async with self._session_factory() as session:
            house = await HouseRepository(session).get_by_id(house_id)
            if house is None:
                raise HouseNotFoundError(f"house_id={house_id} not found")
            if house.owner_player_id != owner_player_id:
                raise NotHouseOwnerError(f"house {house_id} not owned by {owner_player_id}")
            value = self.estimate_value(house)

        options = tuple(
            (deposit_percent,) + pricing.suggested_deposit_and_rent(value, deposit_percent=deposit_percent)
            for deposit_percent in constants.HOUSING_DEPOSIT_PRESET_PERCENTS
        )
        return RentOptions(house_id=house_id, market_value=value, options=options)

    # --- Buying -------------------------------------------------------------------

    async def buy_from_market(self, player_id: int, house_id: int) -> PurchaseResult:
        """Buy an ownerless house from the system market at its dynamic price."""
        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            house_repo = HouseRepository(session)

            if not await player_repo.exists(player_id):
                raise PlayerNotFoundError(f"player_id={player_id} not found")

            house = await house_repo.get_by_id(house_id)
            if house is None:
                raise HouseNotFoundError(f"house_id={house_id} not found")
            if house.owner_player_id is not None:
                raise HouseNotAvailableError(f"house {house_id} is not on the market")

            price = self.estimate_value(house)

            # Atomic debit — the check and the subtraction are one statement.
            if not await player_repo.remove_money_if_enough(player_id, price):
                balance = await player_repo.get_money(player_id)
                if balance is None:
                    raise PlayerNotFoundError(f"player_id={player_id} not found")
                raise InsufficientFundsError(
                    f"player_id={player_id} cannot afford {price} (has {balance})"
                )

            await house_repo.set_owner(house_id, player_id)

            sale_repo = HouseSaleRepository(session)
            await sale_repo.create(
                house_id=house_id, buyer_player_id=player_id, price=price, seller_player_id=None
            )
            tx_repo = HouseTransactionRepository(session)
            await tx_repo.create(
                payer_player_id=player_id,
                payee_player_id=None,
                amount=price,
                transaction_type="market_purchase",
                house_id=house_id,
                note=f"خرید خانه #{house_id} از بازار سیستم",
            )
            await session.commit()

            logger.info(
                "Player %s bought house %s from market for %s", player_id, house_id, price
            )

        xp_granted = await self._grant_purchase_xp(player_id, price)

        async with self._session_factory() as session:
            house = await HouseRepository(session).get_by_id(house_id)
            balance = await PlayerRepository(session).get_money(player_id)
        assert house is not None and balance is not None  # guarded above

        return PurchaseResult(
            buyer_player_id=player_id,
            house=self._to_house_dto(house),
            price=price,
            seller_player_id=None,
            balance_after=balance,
            xp_granted=xp_granted,
        )

    async def buy_from_player(self, buyer_player_id: int, house_id: int) -> PurchaseResult:
        """Buy a house that another player listed for sale (atomic P2P trade)."""
        now = _utc_now()

        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            house_repo = HouseRepository(session)
            listing_repo = HouseListingRepository(session)

            if not await player_repo.exists(buyer_player_id):
                raise PlayerNotFoundError(f"player_id={buyer_player_id} not found")

            house = await house_repo.get_by_id(house_id)
            if house is None:
                raise HouseNotFoundError(f"house_id={house_id} not found")
            if house.owner_player_id is None:
                raise NotListedForSaleError(f"house {house_id} has no sale listing")

            listing = await listing_repo.get_active_sale_by_house(house_id)
            if listing is None:
                raise NotListedForSaleError(f"house {house_id} has no sale listing")
            seller_player_id = listing.owner_player_id
            if seller_player_id is None or house.owner_player_id != seller_player_id:
                raise NotListedForSaleError(f"house {house_id} listing is inconsistent")
            if seller_player_id == buyer_player_id:
                raise CannotBuyOwnHouseError(
                    f"player {buyer_player_id} already owns house {house_id}"
                )

            price = listing.price

            if not await player_repo.remove_money_if_enough(buyer_player_id, price):
                balance = await player_repo.get_money(buyer_player_id)
                if balance is None:
                    raise PlayerNotFoundError(f"player_id={buyer_player_id} not found")
                raise InsufficientFundsError(
                    f"player_id={buyer_player_id} cannot afford {price} (has {balance})"
                )
            if not await player_repo.add_money(seller_player_id, price):
                raise PlayerNotFoundError(f"player_id={seller_player_id} not found")

            await house_repo.set_owner(house_id, buyer_player_id)
            await listing_repo.close(listing.id, now)

            sale_repo = HouseSaleRepository(session)
            await sale_repo.create(
                house_id=house_id,
                buyer_player_id=buyer_player_id,
                price=price,
                seller_player_id=seller_player_id,
                listing_id=listing.id,
            )
            tx_repo = HouseTransactionRepository(session)
            await tx_repo.create(
                payer_player_id=buyer_player_id,
                payee_player_id=seller_player_id,
                amount=price,
                transaction_type="player_purchase",
                house_id=house_id,
                note=f"خرید خانه #{house_id} از بازیکن دیگر",
            )
            await session.commit()

            logger.info(
                "Player %s bought house %s from player %s for %s",
                buyer_player_id,
                house_id,
                seller_player_id,
                price,
            )

        xp_granted = await self._grant_purchase_xp(buyer_player_id, price)

        async with self._session_factory() as session:
            house = await HouseRepository(session).get_by_id(house_id)
            balance = await PlayerRepository(session).get_money(buyer_player_id)
        assert house is not None and balance is not None  # guarded above

        return PurchaseResult(
            buyer_player_id=buyer_player_id,
            house=self._to_house_dto(house),
            price=price,
            seller_player_id=seller_player_id,
            balance_after=balance,
            xp_granted=xp_granted,
        )

    # --- Selling (player-to-player) ---------------------------------------------------

    async def list_house_for_sale(
        self, player_id: int, house_id: int, price: int
    ) -> ListForSaleResult:
        """Put an owned house on the market for other players to buy."""
        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            house_repo = HouseRepository(session)
            listing_repo = HouseListingRepository(session)
            contract_repo = RentalContractRepository(session)

            if not await player_repo.exists(player_id):
                raise PlayerNotFoundError(f"player_id={player_id} not found")

            house = await house_repo.get_by_id(house_id)
            if house is None:
                raise HouseNotFoundError(f"house_id={house_id} not found")
            if house.owner_player_id != player_id:
                raise NotHouseOwnerError(f"house {house_id} not owned by {player_id}")
            if await contract_repo.get_active_by_house(house_id) is not None:
                raise HouseRentedOutError(
                    f"house {house_id} is rented out — end the contract first"
                )
            if await listing_repo.has_any_active_for_house(house_id):
                raise HouseAlreadyListedError(f"house {house_id} is already listed")
            if await MarketplaceListingRepository(session).get_active_by_asset(
                ASSET_TYPE_HOUSE, house_id
            ):
                raise HouseAlreadyListedError(f"house {house_id} is already listed")

            market_value = self.estimate_value(house)
            min_price = market_value * constants.HOUSING_SALE_MIN_PER_MILLE // 1000
            max_price = market_value * constants.HOUSING_SALE_MAX_PER_MILLE // 1000
            if price < min_price or price > max_price:
                raise PriceOutOfBoundsError(
                    f"price {price} outside [{min_price}, {max_price}]"
                )

            await listing_repo.create(
                house_id=house_id,
                owner_player_id=player_id,
                listing_type=LISTING_SALE,
                price=price,
            )
            await session.commit()

            logger.info("Player %s listed house %s for sale at %s", player_id, house_id, price)

        return ListForSaleResult(
            house=self._to_house_dto(house), price=price, market_value=market_value
        )

    async def cancel_sale_listing(self, player_id: int, house_id: int) -> None:
        """Take a house off the sale market."""
        async with self._session_factory() as session:
            listing = await HouseListingRepository(session).get_active_sale_by_house(house_id)
            if listing is None:
                raise NotListedForSaleError(f"house {house_id} has no sale listing")
            if listing.owner_player_id != player_id:
                raise NotHouseOwnerError(f"house {house_id} listing not owned by {player_id}")
            await HouseListingRepository(session).close(listing.id, _utc_now())
            await session.commit()
            logger.info("Player %s cancelled the sale listing of house %s", player_id, house_id)

    # --- Renting out (player-to-player) ---------------------------------------------

    async def list_house_for_rent(
        self, player_id: int, house_id: int, monthly_rent: int, deposit: int = 0
    ) -> ListForRentResult:
        """Put an owned house up for rent for other players."""
        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            house_repo = HouseRepository(session)
            listing_repo = HouseListingRepository(session)
            contract_repo = RentalContractRepository(session)

            if not await player_repo.exists(player_id):
                raise PlayerNotFoundError(f"player_id={player_id} not found")

            house = await house_repo.get_by_id(house_id)
            if house is None:
                raise HouseNotFoundError(f"house_id={house_id} not found")
            if house.owner_player_id != player_id:
                raise NotHouseOwnerError(f"house {house_id} not owned by {player_id}")
            if await contract_repo.get_active_by_house(house_id) is not None:
                raise HouseRentedOutError(f"house {house_id} is already rented out")
            if await listing_repo.has_any_active_for_house(house_id):
                raise HouseAlreadyListedError(f"house {house_id} is already listed")
            if await MarketplaceListingRepository(session).get_active_by_asset(
                ASSET_TYPE_HOUSE, house_id
            ):
                raise HouseAlreadyListedError(f"house {house_id} is already listed")

            market_value = self.estimate_value(house)
            rent_min = market_value * constants.HOUSING_RENT_MIN_PER_MILLE // 1000
            rent_max = market_value * constants.HOUSING_RENT_MAX_PER_MILLE // 1000
            deposit_max = market_value * constants.HOUSING_DEPOSIT_MAX_PER_MILLE // 1000
            if monthly_rent < rent_min or monthly_rent > rent_max:
                raise PriceOutOfBoundsError(
                    f"rent {monthly_rent} outside [{rent_min}, {rent_max}]"
                )
            if deposit < 0 or deposit > deposit_max:
                raise PriceOutOfBoundsError(f"deposit {deposit} outside [0, {deposit_max}]")

            await listing_repo.create(
                house_id=house_id,
                owner_player_id=player_id,
                listing_type=LISTING_RENT,
                price=monthly_rent,
                deposit=deposit,
            )
            await session.commit()

            logger.info(
                "Player %s listed house %s for rent at %s/month (deposit %s)",
                player_id,
                house_id,
                monthly_rent,
                deposit,
            )

        return ListForRentResult(
            house=self._to_house_dto(house),
            monthly_rent=monthly_rent,
            deposit=deposit,
            market_value=market_value,
        )

    async def cancel_rent_listing(self, player_id: int, house_id: int) -> None:
        async with self._session_factory() as session:
            listing = await HouseListingRepository(session).get_active_rent_by_house(house_id)
            if listing is None:
                raise NotListedForRentError(f"house {house_id} has no rent listing")
            if listing.owner_player_id != player_id:
                raise NotHouseOwnerError(f"house {house_id} listing not owned by {player_id}")
            await HouseListingRepository(session).close(listing.id, _utc_now())
            await session.commit()
            logger.info("Player %s cancelled the rent listing of house %s", player_id, house_id)

    # --- Renting (tenant side) ---------------------------------------------------------

    async def rent_house(self, tenant_player_id: int, house_id: int) -> RentalContractData:
        """Rent a house from another player: pay the deposit, sign the contract."""
        now = _utc_now()
        next_due = now + timedelta(days=constants.HOUSING_RENT_PERIOD_DAYS)

        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            house_repo = HouseRepository(session)
            listing_repo = HouseListingRepository(session)
            contract_repo = RentalContractRepository(session)

            if not await player_repo.exists(tenant_player_id):
                raise PlayerNotFoundError(f"player_id={tenant_player_id} not found")

            house = await house_repo.get_by_id(house_id)
            if house is None:
                raise HouseNotFoundError(f"house_id={house_id} not found")

            listing = await listing_repo.get_active_rent_by_house(house_id)
            if listing is None:
                raise NotListedForRentError(f"house {house_id} is not up for rent")
            owner_player_id = listing.owner_player_id
            if owner_player_id is None or owner_player_id != house.owner_player_id:
                raise NotListedForRentError(f"house {house_id} listing is inconsistent")
            if owner_player_id == tenant_player_id:
                raise CannotRentOwnHouseError(
                    f"player {tenant_player_id} owns house {house_id}"
                )
            if await contract_repo.get_active_by_tenant(tenant_player_id) is not None:
                raise AlreadyRentingError(
                    f"player {tenant_player_id} already rents a house"
                )

            # Deposit (رهن) moves tenant -> owner right away, atomically.
            if listing.deposit > 0:
                if not await player_repo.remove_money_if_enough(
                    tenant_player_id, listing.deposit
                ):
                    balance = await player_repo.get_money(tenant_player_id)
                    if balance is None:
                        raise PlayerNotFoundError(f"player_id={tenant_player_id} not found")
                    raise InsufficientFundsError(
                        f"player_id={tenant_player_id} cannot afford deposit "
                        f"{listing.deposit} (has {balance})"
                    )
                if not await player_repo.add_money(owner_player_id, listing.deposit):
                    raise PlayerNotFoundError(f"player_id={owner_player_id} not found")

            contract = await contract_repo.create(
                house_id=house_id,
                owner_player_id=owner_player_id,
                tenant_player_id=tenant_player_id,
                monthly_rent=listing.price,
                deposit=listing.deposit,
                next_due_at=next_due,
                listing_id=listing.id,
            )
            await listing_repo.close(listing.id, now)

            if listing.deposit > 0:
                tx_repo = HouseTransactionRepository(session)
                await tx_repo.create(
                    payer_player_id=tenant_player_id,
                    payee_player_id=owner_player_id,
                    amount=listing.deposit,
                    transaction_type="rent_deposit",
                    house_id=house_id,
                    contract_id=contract.id,
                    note=f"رهن قرارداد خانه #{house_id}",
                )
            await session.commit()

            logger.info(
                "Player %s rented house %s from player %s (rent %s, deposit %s)",
                tenant_player_id,
                house_id,
                owner_player_id,
                listing.price,
                listing.deposit,
            )

        owner_name, label = await self._names_for_contract(house_id, owner_player_id)
        return RentalContractData(
            id=contract.id,
            house_id=house_id,
            owner_player_id=owner_player_id,
            tenant_player_id=tenant_player_id,
            monthly_rent=contract.monthly_rent,
            deposit=contract.deposit,
            started_at=contract.started_at,
            next_due_at=contract.next_due_at,
            is_active=contract.is_active,
            ended_at=contract.ended_at,
            created_at=contract.created_at,
            house_label=label,
            owner_name=owner_name,
        )

    async def _names_for_contract(
        self, house_id: int, owner_player_id: int
    ) -> tuple[str, str]:
        async with self._session_factory() as session:
            house = await HouseRepository(session).get_by_id(house_id)
            owner = await PlayerRepository(session).get_by_id(owner_player_id)
            label = self.house_label(self._to_house_dto(house)) if house else ""
            return (owner.display_name if owner else "؟"), label

    async def pay_rent(self, tenant_player_id: int, contract_id: int) -> RentPaymentResult:
        """Pay one period of rent: money moves tenant -> owner atomically."""
        period = timedelta(days=constants.HOUSING_RENT_PERIOD_DAYS)
        now = _utc_now()

        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            contract_repo = RentalContractRepository(session)

            if not await player_repo.exists(tenant_player_id):
                raise PlayerNotFoundError(f"player_id={tenant_player_id} not found")

            contract = await contract_repo.get_by_id(contract_id)
            if contract is None:
                raise ContractNotFoundError(f"contract {contract_id} not found")
            if not contract.is_active:
                raise ContractNotFoundError(f"contract {contract_id} is not active")
            if contract.tenant_player_id != tenant_player_id:
                raise NotContractPartyError(
                    f"player {tenant_player_id} is not the tenant of {contract_id}"
                )

            amount = contract.monthly_rent
            if not await player_repo.remove_money_if_enough(tenant_player_id, amount):
                balance = await player_repo.get_money(tenant_player_id)
                if balance is None:
                    raise PlayerNotFoundError(f"player_id={tenant_player_id} not found")
                raise InsufficientFundsError(
                    f"player_id={tenant_player_id} cannot afford rent {amount}"
                )
            if not await player_repo.add_money(contract.owner_player_id, amount):
                raise PlayerNotFoundError(f"player_id={contract.owner_player_id} not found")

            # Paying early extends from the current due date; overdue payments
            # restart from now.
            base = max(_as_utc(contract.next_due_at), now)
            next_due = base + period
            await contract_repo.advance_due_date(contract_id, next_due)

            tx_repo = HouseTransactionRepository(session)
            await tx_repo.create(
                payer_player_id=tenant_player_id,
                payee_player_id=contract.owner_player_id,
                amount=amount,
                transaction_type="rent_payment",
                house_id=contract.house_id,
                contract_id=contract_id,
                note=f"اجاره ماهانه خانه #{contract.house_id}",
            )
            await session.commit()

            tenant_balance = await self._balance(tenant_player_id)
            owner_balance = await self._balance(contract.owner_player_id)
            logger.info(
                "Tenant %s paid %s rent for contract %s", tenant_player_id, amount, contract_id
            )

        return RentPaymentResult(
            contract_id=contract_id,
            house_id=contract.house_id,
            amount=amount,
            next_due_at=next_due,
            tenant_balance_after=tenant_balance,
            owner_balance_after=owner_balance,
        )

    async def _balance(self, player_id: int) -> int:
        async with self._session_factory() as session:
            balance = await PlayerRepository(session).get_money(player_id)
        if balance is None:  # pragma: no cover — existence guarded upstream
            raise PlayerNotFoundError(f"player_id={player_id} not found")
        return balance

    async def end_rental_contract(
        self, player_id: int, contract_id: int
    ) -> EndContractResult:
        """End a rental contract — either the owner or the tenant may end it."""
        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            contract_repo = RentalContractRepository(session)

            if not await player_repo.exists(player_id):
                raise PlayerNotFoundError(f"player_id={player_id} not found")

            contract = await contract_repo.get_by_id(contract_id)
            if contract is None or not contract.is_active:
                raise ContractNotFoundError(f"contract {contract_id} not found")
            if player_id not in (contract.owner_player_id, contract.tenant_player_id):
                raise NotContractPartyError(
                    f"player {player_id} is not a party of contract {contract_id}"
                )

            await contract_repo.end(contract_id, _utc_now())
            await session.commit()
            logger.info("Contract %s ended by player %s", contract_id, player_id)

        return EndContractResult(
            contract_id=contract_id,
            house_id=contract.house_id,
            ended_by_player_id=player_id,
            tenant_player_id=contract.tenant_player_id,
            owner_player_id=contract.owner_player_id,
        )

    # --- Contract views -----------------------------------------------------------------

    async def get_my_rental_contracts(self, tenant_player_id: int) -> list[RentalContractData]:
        """Contracts where the player is the tenant."""
        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            if not await player_repo.exists(tenant_player_id):
                raise PlayerNotFoundError(f"player_id={tenant_player_id} not found")
            contract_repo = RentalContractRepository(session)
            house_repo = HouseRepository(session)

            result: list[RentalContractData] = []
            for contract in await contract_repo.list_active_by_tenant(tenant_player_id):
                house = await house_repo.get_by_id(contract.house_id)
                owner = await player_repo.get_by_id(contract.owner_player_id)
                result.append(
                    RentalContractData(
                        id=contract.id,
                        house_id=contract.house_id,
                        owner_player_id=contract.owner_player_id,
                        tenant_player_id=contract.tenant_player_id,
                        monthly_rent=contract.monthly_rent,
                        deposit=contract.deposit,
                        started_at=contract.started_at,
                        next_due_at=contract.next_due_at,
                        is_active=contract.is_active,
                        ended_at=contract.ended_at,
                        created_at=contract.created_at,
                        house_label=(
                            self.house_label(self._to_house_dto(house)) if house else ""
                        ),
                        owner_name=owner.display_name if owner else "؟",
                    )
                )
            return result
