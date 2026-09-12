"""Service layer for the player-to-player ``🧱 دیوار ایران`` marketplace.

Only existing, owned houses, unbuilt land parcels, and fixed-catalog cars
can be listed. The marketplace stores references to those rows, never copies
their attributes.
Every purchase uses the existing MoneyService inside one transaction with the
conditional asset/listing updates, so payment, ownership and sale state either
all commit or all roll back.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select

from app.database.models.house import House
from app.database.models.house_transaction import TX_PLAYER_PURCHASE
from app.database.models.land import Land
from app.database.models.marketplace_listing import MarketplaceListing
from app.database.models.vehicle_ownership import (
    VEHICLE_OWNERSHIP_OWNED,
    VehicleOwnership,
)
from app.database.repositories.construction_project_repository import (
    ConstructionProjectRepository,
)
from app.database.repositories.house_listing_repository import HouseListingRepository
from app.database.repositories.house_repository import HouseRepository
from app.database.repositories.house_sale_repository import HouseSaleRepository
from app.database.repositories.house_transaction_repository import (
    HouseTransactionRepository,
)
from app.database.repositories.land_repository import LandRepository
from app.database.repositories.land_transaction_repository import (
    LandTransactionRepository,
)
from app.database.repositories.marketplace_listing_repository import (
    MarketplaceListingRepository,
)
from app.database.repositories.player_repository import PlayerRepository
from app.database.repositories.rental_contract_repository import RentalContractRepository
from app.database.repositories.vehicle_repository import (
    VehicleModelRepository,
    VehicleOwnershipRepository,
)
from app.database.repositories.renovation_project_repository import (
    RenovationProjectRepository,
)
from app.game.housing.dto import HouseData
from app.game.marketplace.catalog import (
    ASSET_TYPE_CAR,
    ASSET_TYPE_HOUSE,
    ASSET_TYPE_LAND,
    LISTING_STATUS_ACTIVE,
    is_supported_asset_type,
)
from app.game.marketplace.dto import (
    MarketplaceCancelResult,
    MarketplaceCreateResult,
    MarketplaceListingData,
    MarketplaceOwnedAssetData,
    MarketplacePurchaseResult,
    MarketplaceSearchCriteria,
    MarketplaceSearchResult,
)
from app.game.realestate.dto import LandData
from app.game.shared.errors import DomainError, PlayerNotFoundError
from app.game.vehicle.dto import VehicleOwnershipData
from app.services.housing_service import HousingService
from app.services.money_service import MoneyService
from app.services.realestate_service import RealEstateService
from app.services.vehicle_service import VehicleService

logger = logging.getLogger(__name__)


class MarketplaceListingNotFoundError(DomainError):
    """The requested marketplace listing does not exist."""


class MarketplaceListingNotActiveError(DomainError):
    """The listing was sold/cancelled or is no longer purchasable."""


class MarketplaceListingNotOwnerError(DomainError):
    """The caller is not the seller who owns the listing."""


class MarketplaceAssetNotFoundError(DomainError):
    """The referenced house or land row no longer exists."""


class MarketplaceAssetNotOwnedError(DomainError):
    """The seller does not currently own the referenced asset."""


class MarketplaceAssetNotTransferableError(DomainError):
    """The asset is real but currently blocked from transfer."""


class MarketplaceListingAlreadyExistsError(DomainError):
    """The same asset already has an active Divar/legacy sale listing."""


class MarketplaceInvalidPriceError(DomainError):
    """The asking price is not a positive exact integer."""


class MarketplaceCannotBuyOwnListingError(DomainError):
    """A seller cannot purchase their own advertisement."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class DivarService:
    """Business rules and transaction boundary for Divar Iran."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        money_service: MoneyService,
        housing_service: HousingService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._money = money_service
        self._housing = housing_service or HousingService(session_factory)

    # --- Asset eligibility -------------------------------------------------

    async def get_owned_assets(self, player_id: int) -> list[MarketplaceOwnedAssetData]:
        """Return only real, currently eligible player-owned assets."""
        async with self._session_factory() as session:
            players = PlayerRepository(session)
            if not await players.exists(player_id):
                raise PlayerNotFoundError(f"player_id={player_id} not found")

            marketplace = MarketplaceListingRepository(session)
            house_listings = HouseListingRepository(session)
            rentals = RentalContractRepository(session)
            renovations = RenovationProjectRepository(session)
            constructions = ConstructionProjectRepository(session)
            houses = HouseRepository(session)
            lands = LandRepository(session)
            assets: list[MarketplaceOwnedAssetData] = []

            for house in await houses.list_by_owner(player_id):
                if await marketplace.get_active_by_asset(ASSET_TYPE_HOUSE, house.id):
                    continue
                if await house_listings.has_any_active_for_house(house.id):
                    continue
                if await rentals.get_active_by_house(house.id):
                    continue
                if await renovations.get_active_by_house(house.id):
                    continue
                # A constructed house is structurally attached to a parcel.
                # Listing it alone would split ownership of one property.
                attached = await session.execute(
                    select(Land.id).where(Land.built_house_id == house.id).limit(1)
                )
                if attached.scalar_one_or_none() is not None:
                    continue
                assets.append(
                    MarketplaceOwnedAssetData(
                        asset_type=ASSET_TYPE_HOUSE,
                        asset_id=house.id,
                        label=f"🏠 خانه #{house.id} — {house.city}، {house.neighborhood}",
                        location=f"{house.city}، {house.neighborhood}",
                        area_sqm=house.area_sqm,
                    )
                )

            for land in await lands.list_by_owner(player_id):
                if land.built_house_id is not None:
                    continue
                if await marketplace.get_active_by_asset(ASSET_TYPE_LAND, land.id):
                    continue
                if await constructions.get_active_by_land(land.id):
                    continue
                assets.append(
                    MarketplaceOwnedAssetData(
                        asset_type=ASSET_TYPE_LAND,
                        asset_id=land.id,
                        label=f"🌍 زمین #{land.id} — {land.city}، {land.neighborhood}",
                        location=f"{land.city}، {land.neighborhood}",
                        area_sqm=land.area_sqm,
                    )
                )

            for ownership, model in await VehicleOwnershipRepository(session).list_owned_with_models(
                player_id
            ):
                if not VehicleService._is_fixed_model(model):
                    continue
                if await marketplace.get_active_by_asset(ASSET_TYPE_CAR, ownership.id):
                    continue
                assets.append(
                    MarketplaceOwnedAssetData(
                        asset_type=ASSET_TYPE_CAR,
                        asset_id=ownership.id,
                        label=f"🚗 {model.name} — مالکیت #{ownership.id}",
                        location="",
                        area_sqm=None,
                    )
                )
            return assets

    async def create_listing(
        self, seller_player_id: int, asset_type: str, asset_id: int, price: int
    ) -> MarketplaceCreateResult:
        """Create a listing only after re-checking the real asset ownership."""
        self._validate_asset_reference(asset_type, asset_id)
        self._validate_price(price)

        async with self._session_factory() as session:
            players = PlayerRepository(session)
            if not await players.exists(seller_player_id):
                raise PlayerNotFoundError(f"player_id={seller_player_id} not found")
            await self._load_transferable_asset(
                session,
                seller_player_id=seller_player_id,
                asset_type=asset_type,
                asset_id=asset_id,
            )
            marketplace = MarketplaceListingRepository(session)
            if await marketplace.get_active_by_asset(asset_type, asset_id):
                raise MarketplaceListingAlreadyExistsError(
                    f"active marketplace listing exists for {asset_type}:{asset_id}"
                )
            if asset_type == ASSET_TYPE_HOUSE and await HouseListingRepository(
                session
            ).has_any_active_for_house(asset_id):
                raise MarketplaceListingAlreadyExistsError(
                    f"active legacy house listing exists for house {asset_id}"
                )
            try:
                listing = await marketplace.create(
                    seller_player_id=seller_player_id,
                    asset_type=asset_type,
                    asset_id=asset_id,
                    price=price,
                )
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise MarketplaceListingAlreadyExistsError(
                    f"active marketplace listing exists for {asset_type}:{asset_id}"
                ) from exc

            return MarketplaceCreateResult(
                listing=await self._hydrate_listing(session, listing, require_active_owner=False)
            )

    async def cancel_listing(
        self, seller_player_id: int, listing_id: int
    ) -> MarketplaceCancelResult:
        async with self._session_factory() as session:
            listing = await MarketplaceListingRepository(session).get_by_id(listing_id)
            if listing is None:
                raise MarketplaceListingNotFoundError(str(listing_id))
            if listing.status != LISTING_STATUS_ACTIVE:
                raise MarketplaceListingNotActiveError(str(listing_id))
            if listing.seller_player_id != seller_player_id:
                raise MarketplaceListingNotOwnerError(str(listing_id))
            await self._load_transferable_asset(
                session,
                seller_player_id=seller_player_id,
                asset_type=listing.asset_type,
                asset_id=listing.asset_id,
            )
            if not await MarketplaceListingRepository(session).cancel_if_active(
                listing_id, seller_player_id, _utc_now()
            ):
                raise MarketplaceListingNotActiveError(str(listing_id))
            await session.commit()
            return MarketplaceCancelResult(
                listing_id=listing.id,
                asset_type=listing.asset_type,
                asset_id=listing.asset_id,
            )

    async def list_my_listings(self, seller_player_id: int) -> list[MarketplaceListingData]:
        async with self._session_factory() as session:
            if not await PlayerRepository(session).exists(seller_player_id):
                raise PlayerNotFoundError(f"player_id={seller_player_id} not found")
            listings = await MarketplaceListingRepository(session).list_active_by_seller(
                seller_player_id
            )
            result: list[MarketplaceListingData] = []
            for listing in listings:
                try:
                    result.append(
                        await self._hydrate_listing(
                            session, listing, require_active_owner=True
                        )
                    )
                except MarketplaceAssetNotOwnedError:
                    # Keep stale records historical and out of actionable views.
                    continue
            return result

    # --- Search and details ------------------------------------------------

    async def search(
        self,
        criteria: MarketplaceSearchCriteria | None = None,
        *,
        page: int = 0,
        page_size: int = 5,
    ) -> MarketplaceSearchResult:
        criteria = criteria or MarketplaceSearchCriteria()
        if criteria.asset_type is not None and not is_supported_asset_type(
            criteria.asset_type
        ):
            raise MarketplaceAssetNotFoundError(criteria.asset_type)
        safe_page = max(0, int(page))
        safe_size = max(1, min(int(page_size), 20))
        async with self._session_factory() as session:
            listings, total = await MarketplaceListingRepository(session).search_active(
                criteria,
                offset=safe_page * safe_size,
                limit=safe_size,
            )
            hydrated: list[MarketplaceListingData] = []
            for listing in listings:
                try:
                    hydrated.append(
                        await self._hydrate_listing(
                            session, listing, require_active_owner=True
                        )
                    )
                except (MarketplaceAssetNotFoundError, MarketplaceAssetNotOwnedError):
                    # The SQL ownership join normally prevents this. The
                    # defensive check handles a deletion/transfer race.
                    continue
            return MarketplaceSearchResult(
                listings=tuple(hydrated),
                page=safe_page,
                page_size=safe_size,
                total=total,
            )

    async def get_listing(
        self, listing_id: int, *, viewer_player_id: int | None = None
    ) -> MarketplaceListingData:
        del viewer_player_id  # safe seller display is independent of the viewer
        async with self._session_factory() as session:
            listing = await MarketplaceListingRepository(session).get_by_id(listing_id)
            if listing is None:
                raise MarketplaceListingNotFoundError(str(listing_id))
            return await self._hydrate_listing(
                session,
                listing,
                require_active_owner=listing.status == LISTING_STATUS_ACTIVE,
            )

    # --- Atomic purchase ---------------------------------------------------

    async def purchase(
        self, buyer_player_id: int, listing_id: int
    ) -> MarketplacePurchaseResult:
        """Buy one listing atomically; at most one concurrent buyer succeeds."""
        now = _utc_now()
        async with self._session_factory() as session:
            players = PlayerRepository(session)
            if not await players.exists(buyer_player_id):
                raise PlayerNotFoundError(f"player_id={buyer_player_id} not found")

            marketplace = MarketplaceListingRepository(session)
            listing = await marketplace.get_by_id(listing_id)
            if listing is None:
                raise MarketplaceListingNotFoundError(str(listing_id))
            if listing.status != LISTING_STATUS_ACTIVE:
                raise MarketplaceListingNotActiveError(str(listing_id))
            if listing.seller_player_id == buyer_player_id:
                raise MarketplaceCannotBuyOwnListingError(str(listing_id))

            transferable = await self._load_transferable_asset(
                session,
                seller_player_id=listing.seller_player_id,
                asset_type=listing.asset_type,
                asset_id=listing.asset_id,
            )
            if listing.asset_type == ASSET_TYPE_CAR:
                # The dealership's existing partial unique index allows only
                # one owned row per buyer/model. Reject this before charging
                # the buyer instead of relying on an IntegrityError later.
                assert isinstance(transferable, VehicleOwnership)
                already_owned = await VehicleOwnershipRepository(
                    session
                ).get_owned_by_player_and_model(
                    buyer_player_id, transferable.vehicle_model_id
                )
                if already_owned is not None:
                    raise MarketplaceAssetNotTransferableError(
                        "buyer already owns this vehicle model"
                    )

            # These calls only stage SQL in this session. The outer service
            # owns commit/rollback, so an ownership or listing race rolls the
            # debit and seller credit back with it.
            debit = await self._money.remove_money_in_transaction(
                session, buyer_player_id, listing.price
            )
            await self._money.add_money_in_transaction(
                session, listing.seller_player_id, listing.price
            )

            if listing.asset_type == ASSET_TYPE_HOUSE:
                transferred = await HouseRepository(session).transfer_owner_if(
                    listing.asset_id, listing.seller_player_id, buyer_player_id
                )
            elif listing.asset_type == ASSET_TYPE_LAND:
                transferred = await LandRepository(session).transfer_owner_if(
                    listing.asset_id, listing.seller_player_id, buyer_player_id
                )
            else:
                transferred = await VehicleOwnershipRepository(session).transfer_owner_if(
                    listing.asset_id, listing.seller_player_id, buyer_player_id
                )
            if not transferred:
                raise MarketplaceAssetNotOwnedError(str(listing.asset_id))

            if not await marketplace.mark_sold_if_active(
                listing.id, buyer_player_id, now
            ):
                raise MarketplaceListingNotActiveError(str(listing_id))

            if listing.asset_type == ASSET_TYPE_HOUSE:
                await HouseSaleRepository(session).create(
                    house_id=listing.asset_id,
                    buyer_player_id=buyer_player_id,
                    seller_player_id=listing.seller_player_id,
                    price=listing.price,
                    listing_id=None,
                )
                await HouseTransactionRepository(session).create(
                    payer_player_id=buyer_player_id,
                    payee_player_id=listing.seller_player_id,
                    amount=listing.price,
                    transaction_type=TX_PLAYER_PURCHASE,
                    house_id=listing.asset_id,
                    note=f"خرید خانه #{listing.asset_id} از دیوار ایران",
                )
            elif listing.asset_type == ASSET_TYPE_LAND:
                await LandTransactionRepository(session).create(
                    payer_player_id=buyer_player_id,
                    payee_player_id=listing.seller_player_id,
                    amount=listing.price,
                    transaction_type="player_sale",
                    land_id=listing.asset_id,
                    note=f"خرید زمین #{listing.asset_id} از دیوار ایران",
                )
            else:
                logger.info(
                    "Divar car ownership transfer staged: ownership=%s buyer=%s",
                    listing.asset_id,
                    buyer_player_id,
                )

            await session.commit()
            # The repository deliberately uses a conditional bulk UPDATE for
            # the race-safe status transition; refresh the identity-mapped
            # object before returning the historical sold state.
            await session.refresh(listing)
            sold_listing = listing
            hydrated = await self._hydrate_listing(
                session, sold_listing, require_active_owner=False
            )
            logger.info(
                "Divar listing %s sold: buyer=%s seller=%s price=%s",
                listing.id,
                buyer_player_id,
                listing.seller_player_id,
                listing.price,
            )
            return MarketplacePurchaseResult(
                listing=hydrated,
                buyer_player_id=buyer_player_id,
                seller_player_id=listing.seller_player_id,
                price=listing.price,
                buyer_balance_after=debit.balance_after,
            )

    # --- Internal validation / hydration ----------------------------------

    @staticmethod
    def _validate_asset_reference(asset_type: str, asset_id: int) -> None:
        if not is_supported_asset_type(asset_type):
            raise MarketplaceAssetNotFoundError(asset_type)
        if isinstance(asset_id, bool) or not isinstance(asset_id, int) or asset_id <= 0:
            raise MarketplaceAssetNotFoundError(str(asset_id))

    @staticmethod
    def _validate_price(price: int) -> None:
        if isinstance(price, bool) or not isinstance(price, int) or price <= 0:
            raise MarketplaceInvalidPriceError(str(price))

    async def _load_transferable_asset(
        self,
        session: AsyncSession,
        *,
        seller_player_id: int,
        asset_type: str,
        asset_id: int,
    ) -> House | Land | VehicleOwnership:
        self._validate_asset_reference(asset_type, asset_id)
        if asset_type == ASSET_TYPE_HOUSE:
            house = await HouseRepository(session).get_by_id(asset_id)
            if house is None:
                raise MarketplaceAssetNotFoundError(str(asset_id))
            if house.owner_player_id != seller_player_id:
                raise MarketplaceAssetNotOwnedError(str(asset_id))
            if await RentalContractRepository(session).get_active_by_house(asset_id):
                raise MarketplaceAssetNotTransferableError("rented house")
            if await RenovationProjectRepository(session).get_active_by_house(asset_id):
                raise MarketplaceAssetNotTransferableError("renovating house")
            if await HouseListingRepository(session).has_any_active_for_house(asset_id):
                raise MarketplaceListingAlreadyExistsError(str(asset_id))
            attached = await session.execute(
                select(Land.id).where(Land.built_house_id == asset_id).limit(1)
            )
            if attached.scalar_one_or_none() is not None:
                raise MarketplaceAssetNotTransferableError("constructed house")
            return house

        if asset_type == ASSET_TYPE_CAR:
            ownership = await VehicleOwnershipRepository(session).get_by_id(asset_id)
            if ownership is None:
                raise MarketplaceAssetNotFoundError(str(asset_id))
            if ownership.owner_player_id != seller_player_id:
                raise MarketplaceAssetNotOwnedError(str(asset_id))
            if ownership.status != VEHICLE_OWNERSHIP_OWNED:
                raise MarketplaceAssetNotTransferableError("inactive vehicle")
            model = await VehicleModelRepository(session).get_by_id(
                ownership.vehicle_model_id
            )
            if model is None or not VehicleService._is_fixed_model(model):
                raise MarketplaceAssetNotFoundError(str(asset_id))
            return ownership

        land = await LandRepository(session).get_by_id(asset_id)
        if land is None:
            raise MarketplaceAssetNotFoundError(str(asset_id))
        if land.owner_player_id != seller_player_id:
            raise MarketplaceAssetNotOwnedError(str(asset_id))
        if land.built_house_id is not None:
            raise MarketplaceAssetNotTransferableError("built land")
        if await ConstructionProjectRepository(session).get_active_by_land(asset_id):
            raise MarketplaceAssetNotTransferableError("constructing land")
        return land

    async def _hydrate_listing(
        self,
        session: AsyncSession,
        listing: MarketplaceListing,
        *,
        require_active_owner: bool,
    ) -> MarketplaceListingData:
        seller = await PlayerRepository(session).get_by_id(listing.seller_player_id)
        if seller is None:
            raise MarketplaceAssetNotFoundError(str(listing.seller_player_id))
        house: HouseData | None = None
        land: LandData | None = None
        vehicle: VehicleOwnershipData | None = None
        if listing.asset_type == ASSET_TYPE_HOUSE:
            asset = await HouseRepository(session).get_by_id(listing.asset_id)
            if asset is None:
                raise MarketplaceAssetNotFoundError(str(listing.asset_id))
            await session.refresh(asset)
            if require_active_owner and asset.owner_player_id != listing.seller_player_id:
                raise MarketplaceAssetNotOwnedError(str(listing.asset_id))
            house = HousingService._to_house_dto(asset)
        elif listing.asset_type == ASSET_TYPE_LAND:
            asset = await LandRepository(session).get_by_id(listing.asset_id)
            if asset is None:
                raise MarketplaceAssetNotFoundError(str(listing.asset_id))
            await session.refresh(asset)
            if require_active_owner and asset.owner_player_id != listing.seller_player_id:
                raise MarketplaceAssetNotOwnedError(str(listing.asset_id))
            land = RealEstateService._to_land_dto(asset)
        elif listing.asset_type == ASSET_TYPE_CAR:
            ownership = await VehicleOwnershipRepository(session).get_by_id(
                listing.asset_id
            )
            if ownership is None:
                raise MarketplaceAssetNotFoundError(str(listing.asset_id))
            await session.refresh(ownership)
            if (
                require_active_owner
                and (
                    ownership.owner_player_id != listing.seller_player_id
                    or ownership.status != VEHICLE_OWNERSHIP_OWNED
                )
            ):
                raise MarketplaceAssetNotOwnedError(str(listing.asset_id))
            model = await VehicleModelRepository(session).get_by_id(
                ownership.vehicle_model_id
            )
            if model is None or not VehicleService._is_fixed_model(model):
                raise MarketplaceAssetNotFoundError(str(listing.asset_id))
            vehicle = VehicleService._to_ownership_dto(ownership, model)
        else:
            raise MarketplaceAssetNotFoundError(listing.asset_type)
        return MarketplaceListingData(
            id=listing.id,
            seller_player_id=listing.seller_player_id,
            seller_name=seller.display_name,
            asset_type=listing.asset_type,
            asset_id=listing.asset_id,
            price=listing.price,
            status=listing.status,
            created_at=_as_utc(listing.created_at) or _utc_now(),
            sold_at=_as_utc(listing.sold_at),
            buyer_player_id=listing.buyer_player_id,
            house=house,
            land=land,
            vehicle=vehicle,
        )
