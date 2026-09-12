"""Land, Construction and Renovation service — the transaction boundary.

Use cases:
* Land market: dynamic-priced parcels, buy → ownership + transaction history.
* Construction: build a full blueprint on an owned vacant parcel; money is
  paid upfront, the project takes real time, and completion creates a brand
  new House (age 0) that plugs straight into the Housing system.
* Renovation: quote and start renovations on owned houses; completion applies
  the attribute changes, and the dynamic pricing engine raises the value.
* Property upgrades: every construction/renovation completion writes a
  value_before → value_after audit row.

Money movements reuse the atomic wallet primitives (``remove_money_if_enough``
/ ``add_money``). Completion is lazy: whenever any related screen is opened,
due projects are settled first (concurrent-safe via an atomic status claim),
so a future scheduler can also call ``settle_due`` periodically.

Level/XP integration: completing a construction grants XP through the
existing ``LevelService`` — never implicitly.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import constants
from app.database.models.house import House
from app.database.models.land import Land
from app.database.repositories.construction_project_repository import (
    ConstructionProjectRepository,
)
from app.database.repositories.house_repository import HouseRepository
from app.database.repositories.land_repository import LandRepository
from app.database.repositories.land_transaction_repository import (
    LandTransactionRepository,
)
from app.database.repositories.player_repository import PlayerRepository
from app.database.repositories.property_upgrade_repository import (
    PropertyUpgradeRepository,
)
from app.database.repositories.renovation_project_repository import (
    RenovationProjectRepository,
)
from app.database.repositories.rental_contract_repository import (
    RentalContractRepository,
)
from app.game.admin import runtime as admin_runtime
from app.game.housing import pricing
from app.game.housing.dto import HouseData
from app.game.realestate import construction as construction_domain
from app.game.realestate import renovation as renovation_domain
from app.game.realestate.dto import (
    STATUS_IN_PROGRESS,
    ConstructionCancelResult,
    ConstructionProjectData,
    ConstructionStartResult,
    LandData,
    LandInfoData,
    LandMarketEntry,
    LandPurchaseResult,
    LandWithStatus,
    PlayerLandsData,
    ProjectsStatusData,
    PropertyUpgradeData,
    RenovationProjectData,
    RenovationStartResult,
)
from app.game.realestate.land_pricing import (
    LandPricingInput,
    estimate_land_price,
    estimate_land_price_per_sqm,
    quality_label_for,
)
from app.game.housing.construction_year import current_iranian_year
from app.game.housing.seeding import CITY_NEIGHBORHOODS, list_cities
from app.game.shared.errors import DomainError, InsufficientFundsError, PlayerNotFoundError
from app.services.housing_service import (
    HouseNotFoundError,
    HousingService,
    NotHouseOwnerError,
)

logger = logging.getLogger(__name__)


# --- Domain errors --------------------------------------------------------------


class LandNotFoundError(DomainError):
    """The requested parcel does not exist."""


class LandNotAvailableError(DomainError):
    """The parcel is already owned by someone."""


class LandBusyError(DomainError):
    """The parcel already has a built house or an active construction."""


class SpecInvalidError(DomainError):
    """The construction blueprint is impossible."""


class ProjectNotFoundError(DomainError):
    """The construction/renovation project does not exist."""


class NotProjectOwnerError(DomainError):
    """The player does not own this project."""


class AlreadyRenovatingError(DomainError):
    """The house already has an active renovation."""


class RenovationBlockedError(DomainError):
    """The house cannot be renovated right now (e.g. tenant in place)."""


class NothingToRenovateError(DomainError):
    """The chosen renovation is not applicable to this house."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class RealEstateService:
    """Complete Land, Construction and Renovation service."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        level_service=None,
        housing_service: HousingService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._level_service = level_service
        # Shared HousingService for asset reads (wired by the registry).
        self._housing = housing_service or HousingService(session_factory)

    # --- Conversion helpers ---------------------------------------------------

    @staticmethod
    def _to_land_dto(land: Land) -> LandData:
        return LandData(
            id=land.id,
            city=land.city,
            neighborhood=land.neighborhood,
            area_sqm=land.area_sqm,
            location_quality=land.location_quality,
            owner_player_id=land.owner_player_id,
            built_house_id=land.built_house_id,
            created_at=land.created_at,
            updated_at=land.updated_at,
            price_override_per_mille=land.price_override_per_mille,
        )

    @staticmethod
    def _land_pricing_input(land: Land) -> LandPricingInput:
        return LandPricingInput(
            land_id=land.id,
            city=land.city,
            neighborhood=land.neighborhood,
            area_sqm=land.area_sqm,
        )

    def estimate_land_value(self, land: Land) -> int:
        """Live dynamic market value of a parcel (exact integer Toman)."""
        value = estimate_land_price(self._land_pricing_input(land))
        override = land.price_override_per_mille
        if override:
            value = max(1, value * int(override) // 1000)
        return value

    @staticmethod
    def house_value(house: House | HouseData) -> int:
        """Live dynamic market value of a house (via the housing engine)."""
        value = pricing.estimate_house_price(
            HousingService.pricing_input_for_house(house),
            market_factor=admin_runtime.effective_market_factor(),
        )
        override = getattr(house, "price_override_per_mille", None)
        if override:
            value = max(1, value * int(override) // 1000)
        return value

    @staticmethod
    def house_label(house: House | HouseData) -> str:
        return HousingService.house_label(house)

    @staticmethod
    def _project_progress(
        started_at: datetime, duration_seconds: int, status: str, now: datetime
    ) -> tuple[float, int | None]:
        """(progress_percent, seconds_remaining) for a project."""
        if status != STATUS_IN_PROGRESS:
            return 100.0, 0
        started = _as_utc(started_at)
        elapsed = (now - started).total_seconds()
        percent = max(0.0, min(100.0, elapsed / max(1, duration_seconds) * 100.0))
        completes = started + timedelta(seconds=duration_seconds)
        remaining = max(0, int((completes - now).total_seconds()))
        return percent, remaining

    def _to_project_dto(
        self, project, land: Land | None = None
    ) -> ConstructionProjectData:
        now = _utc_now()
        percent, remaining = self._project_progress(
            project.started_at, project.duration_seconds, project.status, now
        )
        return ConstructionProjectData(
            id=project.id,
            land_id=project.land_id,
            house_id=project.house_id,
            owner_player_id=project.owner_player_id,
            status=project.status,
            building_type_label=construction_domain.BUILDING_TYPE_LABELS.get(
                project.building_type, project.building_type
            ),
            floors=project.floors,
            area_sqm=project.area_sqm,
            bedrooms=project.bedrooms,
            bathrooms=project.bathrooms,
            living_rooms=project.living_rooms,
            kitchen_type=project.kitchen_type,
            quality=construction_domain.QUALITY_TOKENS.get(project.quality, project.quality),
            parking=project.parking,
            elevator=project.elevator,
            storage=project.storage,
            cost_total=project.cost_total,
            started_at=project.started_at,
            completes_at=project.completes_at,
            completed_at=project.completed_at,
            progress_percent=percent,
            seconds_remaining=remaining,
            land_label=(f"{land.city}، {land.neighborhood}" if land is not None else ""),
        )

    # --- Seeding ------------------------------------------------------------------

    async def ensure_initial_lands(self) -> list[LandData]:
        """Seed the starter land market once (idempotent)."""
        async with self._session_factory() as session:
            repo = LandRepository(session)
            if await repo.count() > 0:
                lands = await repo.list_unowned()
                return [self._to_land_dto(l) for l in lands]

            cities = list_cities()
            areas = (100, 150, 200, 250, 300, 400, 500, 600, 750, 1000)
            created: list[LandData] = []
            for index in range(constants.REALESTATE_SEED_LAND_COUNT):
                city = cities[index % len(cities)]
                neighborhoods = list(CITY_NEIGHBORHOODS.get(city, {}).keys())
                neighborhood = neighborhoods[index % len(neighborhoods)]
                area = areas[index % len(areas)]
                quality = quality_label_for(city, neighborhood) or "خوب"
                land = await repo.create(
                    city=city,
                    neighborhood=neighborhood,
                    area_sqm=area,
                    location_quality=quality,
                    owner_player_id=None,
                )
                created.append(self._to_land_dto(land))
            await session.commit()
            logger.info("Seeded %s starter lands on the system market", len(created))
            return created

    # --- Land market ---------------------------------------------------------------

    async def get_available_lands(self) -> list[LandMarketEntry]:
        """All ownerless parcels with their live dynamic prices (cheapest first)."""
        async with self._session_factory() as session:
            lands = await LandRepository(session).list_unowned()

        entries: list[LandMarketEntry] = []
        for land in lands:
            price = self.estimate_land_value(land)
            per_sqm = estimate_land_price_per_sqm(self._land_pricing_input(land))
            entries.append(
                LandMarketEntry(land=self._to_land_dto(land), price=price, price_per_sqm=per_sqm)
            )
        entries.sort(key=lambda e: e.price)
        return entries

    async def get_land_info(
        self, land_id: int, viewer_player_id: int | None = None
    ) -> LandInfoData:
        """Everything the «اطلاعات ملک» screen needs for one parcel."""
        del viewer_player_id  # kept for signature symmetry with housing info
        async with self._session_factory() as session:
            land_repo = LandRepository(session)
            land = await land_repo.get_by_id(land_id)
            if land is None:
                raise LandNotFoundError(f"land_id={land_id} not found")

            owner_name: str | None = None
            if land.owner_player_id is not None:
                owner = await PlayerRepository(session).get_by_id(land.owner_player_id)
                owner_name = owner.display_name if owner else None

            project_repo = ConstructionProjectRepository(session)
            active = await project_repo.get_active_by_land(land_id)

            built_house: House | None = None
            if land.built_house_id is not None:
                built_house = await HouseRepository(session).get_by_id(land.built_house_id)

            info = LandInfoData(
                land=self._to_land_dto(land),
                market_value=self.estimate_land_value(land),
                price_per_sqm=estimate_land_price_per_sqm(self._land_pricing_input(land)),
                owner_name=owner_name,
                built_house=(
                    HousingService._to_house_dto(built_house) if built_house else None
                ),
                active_construction=(
                    self._to_project_dto(active, land) if active is not None else None
                ),
            )
        return info

    async def buy_land(self, player_id: int, land_id: int) -> LandPurchaseResult:
        """Buy an ownerless parcel: atomic debit + ownership + audit row."""
        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            land_repo = LandRepository(session)

            if not await player_repo.exists(player_id):
                raise PlayerNotFoundError(f"player_id={player_id} not found")

            land = await land_repo.get_by_id(land_id)
            if land is None:
                raise LandNotFoundError(f"land_id={land_id} not found")
            if land.owner_player_id is not None:
                raise LandNotAvailableError(f"land {land_id} is already owned")

            price = self.estimate_land_value(land)

            if not await player_repo.remove_money_if_enough(player_id, price):
                balance = await player_repo.get_money(player_id)
                if balance is None:
                    raise PlayerNotFoundError(f"player_id={player_id} not found")
                raise InsufficientFundsError(
                    f"player_id={player_id} cannot afford {price} (has {balance})"
                )

            await land_repo.set_owner(land_id, player_id)
            await LandTransactionRepository(session).create(
                payer_player_id=player_id,
                payee_player_id=None,
                amount=price,
                transaction_type="market_purchase",
                land_id=land_id,
                note=f"خرید زمین #{land_id} از بازار سیستم",
            )
            await session.commit()

            logger.info("Player %s bought land %s for %s", player_id, land_id, price)

        async with self._session_factory() as session:
            land = await LandRepository(session).get_by_id(land_id)
            balance = await PlayerRepository(session).get_money(player_id)
        assert land is not None and balance is not None  # guarded above

        return LandPurchaseResult(
            buyer_player_id=player_id,
            land=self._to_land_dto(land),
            price=price,
            balance_after=balance,
        )

    async def get_my_lands(self, player_id: int) -> PlayerLandsData:
        """The player's parcels («زمین‌های من») with live values and status."""
        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            if not await player_repo.exists(player_id):
                raise PlayerNotFoundError(f"player_id={player_id} not found")

            land_repo = LandRepository(session)
            project_repo = ConstructionProjectRepository(session)

            lands = await land_repo.list_by_owner(player_id)
            entries: list[LandWithStatus] = []
            total = 0
            for land in lands:
                active = await project_repo.get_active_by_land(land.id)
                value = self.estimate_land_value(land)
                total += value
                entries.append(
                    LandWithStatus(
                        land=self._to_land_dto(land),
                        market_value=value,
                        active_construction=(
                            self._to_project_dto(active, land)
                            if active is not None
                            else None
                        ),
                    )
                )
        return PlayerLandsData(
            player_id=player_id,
            lands=tuple(entries),
            total_market_value=total,
        )

    # --- Construction -----------------------------------------------------------------

    async def get_land_for_building(
        self, land_id: int, player_id: int
    ) -> tuple[LandData, list[int], int]:
        """Validate a parcel for building; return (land, floors_options, max_floors).

        Raises the domain errors the bot layer translates into friendly text.
        """
        async with self._session_factory() as session:
            land = await LandRepository(session).get_by_id(land_id)
            if land is None:
                raise LandNotFoundError(f"land_id={land_id} not found")
            if land.owner_player_id != player_id:
                raise NotHouseOwnerError(f"land {land_id} not owned by {player_id}")
            if land.built_house_id is not None:
                raise LandBusyError(f"land {land_id} already has a house")
            if await ConstructionProjectRepository(session).get_active_by_land(land_id):
                raise LandBusyError(f"land {land_id} is under construction")
            land_dto = self._to_land_dto(land)
        return land_dto, list(
            range(
                construction_domain.APARTMENT_MIN_FLOORS,
                construction_domain.APARTMENT_MAX_FLOORS + 1,
            )
        ), construction_domain.APARTMENT_MAX_FLOORS

    async def start_construction(
        self, player_id: int, land_id: int, spec: construction_domain.BuildingSpec
    ) -> ConstructionStartResult:
        """Start building on an owned vacant parcel (paid upfront, takes time)."""
        now = _utc_now()

        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            land_repo = LandRepository(session)
            project_repo = ConstructionProjectRepository(session)

            if not await player_repo.exists(player_id):
                raise PlayerNotFoundError(f"player_id={player_id} not found")

            land = await land_repo.get_by_id(land_id)
            if land is None:
                raise LandNotFoundError(f"land_id={land_id} not found")
            if land.owner_player_id != player_id:
                raise NotHouseOwnerError(f"land {land_id} not owned by {player_id}")
            if land.built_house_id is not None:
                raise LandBusyError(f"land {land_id} already has a house")
            if await project_repo.get_active_by_land(land_id) is not None:
                raise LandBusyError(f"land {land_id} is under construction")
            if spec.land_id != land_id:
                raise SpecInvalidError("blueprint is for a different parcel")

            try:
                construction_domain.validate_spec(spec, land.area_sqm)
            except ValueError as exc:
                raise SpecInvalidError(str(exc)) from exc

            cost = construction_domain.construction_cost(spec)
            duration = construction_domain.construction_duration_seconds(spec)

            if not await player_repo.remove_money_if_enough(player_id, cost):
                balance = await player_repo.get_money(player_id)
                if balance is None:
                    raise PlayerNotFoundError(f"player_id={player_id} not found")
                raise InsufficientFundsError(
                    f"player_id={player_id} cannot afford construction {cost} "
                    f"(has {balance})"
                )

            bathrooms, living_rooms = construction_domain.derived_rooms(
                spec.area_sqm, spec.bedrooms
            )
            project = await project_repo.create(
                land_id=land_id,
                owner_player_id=player_id,
                building_type=spec.building_type,
                floors=spec.floors,
                area_sqm=spec.area_sqm,
                bedrooms=spec.bedrooms,
                bathrooms=bathrooms,
                living_rooms=living_rooms,
                quality=spec.quality_token,
                kitchen_type=spec.kitchen_type,
                parking=spec.parking,
                elevator=spec.elevator,
                storage=spec.storage,
                cost_total=cost,
                started_at=now,
                duration_seconds=duration,
                completes_at=now + timedelta(seconds=duration),
            )
            await session.commit()

            logger.info(
                "Player %s started construction %s on land %s (cost %s, %ss)",
                player_id, project.id, land_id, cost, duration,
            )

        async with self._session_factory() as session:
            land = await LandRepository(session).get_by_id(land_id)
            balance = await PlayerRepository(session).get_money(player_id)
        assert land is not None and balance is not None

        project_dto = await self.get_construction_project(project.id)
        return ConstructionStartResult(
            project=project_dto,
            land=self._to_land_dto(land),
            cost=cost,
            balance_after=balance,
        )

    async def get_construction_project(self, project_id: int) -> ConstructionProjectData:
        async with self._session_factory() as session:
            project = await ConstructionProjectRepository(session).get_by_id(project_id)
            if project is None:
                raise ProjectNotFoundError(f"project {project_id} not found")
            land = await LandRepository(session).get_by_id(project.land_id)
        return self._to_project_dto(project, land)

    async def cancel_construction(
        self, player_id: int, project_id: int
    ) -> ConstructionCancelResult:
        """Cancel an in-progress construction; refunds part of the cost."""
        refund_percent = constants.CONSTRUCTION_CANCEL_REFUND_PERCENT

        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            project_repo = ConstructionProjectRepository(session)

            if not await player_repo.exists(player_id):
                raise PlayerNotFoundError(f"player_id={player_id} not found")

            project = await project_repo.get_by_id(project_id)
            if project is None or project.status != STATUS_IN_PROGRESS:
                raise ProjectNotFoundError(f"project {project_id} is not active")
            if project.owner_player_id != player_id:
                raise NotProjectOwnerError(
                    f"project {project_id} not owned by {player_id}"
                )

            refund = project.cost_total * refund_percent // 100
            cancelled = await project_repo.mark_cancelled(project_id, _utc_now())
            if not cancelled:  # pragma: no cover — same-session race guard
                raise ProjectNotFoundError(f"project {project_id} is not active")

            await player_repo.add_money(player_id, refund)
            await session.commit()

            logger.info(
                "Project %s cancelled by player %s (refund %s)", project_id, player_id, refund
            )

        balance = await self._balance(player_id)
        return ConstructionCancelResult(
            project_id=project_id, refund=refund, balance_after=balance
        )

    # --- Renovation -----------------------------------------------------------------

    async def get_renovation_options(self, player_id: int, house_id: int):
        """Quote every renovation for an owned, free, not-busy house."""
        async with self._session_factory() as session:
            house = await HouseRepository(session).get_by_id(house_id)
            if house is None:
                raise HouseNotFoundError(f"house_id={house_id} not found")
            if house.owner_player_id != player_id:
                raise NotHouseOwnerError(f"house {house_id} not owned by {player_id}")
            if await RentalContractRepository(session).get_active_by_house(house_id):
                raise RenovationBlockedError(
                    f"house {house_id} is rented out — the tenant lives there"
                )
            if await RenovationProjectRepository(session).get_active_by_house(house_id):
                raise AlreadyRenovatingError(f"house {house_id} is already renovating")
            house_dto = HousingService._to_house_dto(house)
            label = self.house_label(house_dto)

        options = renovation_domain.available_renovations(house_dto)
        value = self.house_value(house_dto)
        return house_dto, label, value, options

    async def start_renovation(
        self, player_id: int, house_id: int, renovation_type: str
    ) -> RenovationStartResult:
        """Start a renovation on an owned house (paid upfront, takes time)."""
        now = _utc_now()

        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            house_repo = HouseRepository(session)

            if not await player_repo.exists(player_id):
                raise PlayerNotFoundError(f"player_id={player_id} not found")

            house = await house_repo.get_by_id(house_id)
            if house is None:
                raise HouseNotFoundError(f"house_id={house_id} not found")
            if house.owner_player_id != player_id:
                raise NotHouseOwnerError(f"house {house_id} not owned by {player_id}")
            if await RentalContractRepository(session).get_active_by_house(house_id):
                raise RenovationBlockedError(
                    f"house {house_id} is rented out — the tenant lives there"
                )
            if await RenovationProjectRepository(session).get_active_by_house(house_id):
                raise AlreadyRenovatingError(f"house {house_id} is already renovating")

        house_dto = HousingService._to_house_dto(house)
        try:
            quote = renovation_domain.renovation_quote(house_dto, renovation_type)
        except ValueError as exc:
            raise NothingToRenovateError(str(exc)) from exc
        value_before = self.house_value(house_dto)

        async with self._session_factory() as session:
            # A fresh repository bound to THIS session — the earlier one belongs
            # to the already-closed validation session.
            player_repo = PlayerRepository(session)
            if not await player_repo.remove_money_if_enough(player_id, quote.cost):
                balance = await player_repo.get_money(player_id)
                if balance is None:
                    raise PlayerNotFoundError(f"player_id={player_id} not found")
                raise InsufficientFundsError(
                    f"player_id={player_id} cannot afford renovation {quote.cost}"
                )

            project = await RenovationProjectRepository(session).create(
                house_id=house_id,
                owner_player_id=player_id,
                renovation_type=renovation_type,
                title=quote.title,
                description=quote.description,
                cost=quote.cost,
                started_at=now,
                duration_seconds=quote.duration_seconds,
                completes_at=now + timedelta(seconds=quote.duration_seconds),
            )
            await session.commit()

            logger.info(
                "Player %s started renovation %s on house %s (cost %s)",
                player_id, renovation_type, house_id, quote.cost,
            )

        balance = await self._balance(player_id)
        project_dto = await self.get_renovation_project(project.id)
        return RenovationStartResult(
            project=project_dto,
            house=house_dto,
            cost=quote.cost,
            balance_after=balance,
            value_before=value_before,
        )

    async def get_renovation_project(self, project_id: int) -> RenovationProjectData:
        async with self._session_factory() as session:
            project = await RenovationProjectRepository(session).get_by_id(project_id)
            if project is None:
                raise ProjectNotFoundError(f"project {project_id} not found")
            house = await HouseRepository(session).get_by_id(project.house_id)
        return self._to_renovation_dto(project, house)

    def _to_renovation_dto(self, project, house: House | None) -> RenovationProjectData:
        now = _utc_now()
        percent, remaining = self._project_progress(
            project.started_at, project.duration_seconds, project.status, now
        )
        return RenovationProjectData(
            id=project.id,
            house_id=project.house_id,
            owner_player_id=project.owner_player_id,
            renovation_type=project.renovation_type,
            title=project.title,
            description=project.description,
            cost=project.cost,
            status=project.status,
            started_at=project.started_at,
            completes_at=project.completes_at,
            completed_at=project.completed_at,
            progress_percent=percent,
            seconds_remaining=remaining,
            house_label=self.house_label(house) if house else "",
        )

    async def get_my_renovations(self, player_id: int) -> list[RenovationProjectData]:
        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            if not await player_repo.exists(player_id):
                raise PlayerNotFoundError(f"player_id={player_id} not found")
            projects = await RenovationProjectRepository(session).list_by_owner(player_id)
            house_repo = HouseRepository(session)
            dtos = []
            for project in projects:
                house = await house_repo.get_by_id(project.house_id)
                dtos.append(self._to_renovation_dto(project, house))
        return dtos

    async def get_renovatable_houses(self, player_id: int) -> list[HouseData]:
        """Owned houses that can be renovated right now.

        Excludes houses with a tenant in place (renovating around a tenant is
        blocked) and houses already under renovation.
        """
        assets = await self._housing.get_player_assets(player_id)
        rented = {c.house_id for c in assets.rented_out_contracts}

        async with self._session_factory() as session:
            renovation_repo = RenovationProjectRepository(session)
            result: list[HouseData] = []
            for house in assets.houses:
                if house.id in rented:
                    continue
                if await renovation_repo.get_active_by_house(house.id) is not None:
                    continue
                result.append(house)
        return result

    # --- Status ------------------------------------------------------------------------

    async def get_projects_status(self, player_id: int) -> ProjectsStatusData:
        """Active and recent projects for the «وضعیت ساخت» screen."""
        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            if not await player_repo.exists(player_id):
                raise PlayerNotFoundError(f"player_id={player_id} not found")
            project_repo = ConstructionProjectRepository(session)
            renovation_repo = RenovationProjectRepository(session)
            land_repo = LandRepository(session)
            house_repo = HouseRepository(session)

            constructions: list[ConstructionProjectData] = []
            for project in await project_repo.list_by_owner(player_id):
                land = await land_repo.get_by_id(project.land_id)
                constructions.append(self._to_project_dto(project, land))

            renovations: list[RenovationProjectData] = []
            for project in await renovation_repo.list_by_owner(player_id):
                house = await house_repo.get_by_id(project.house_id)
                renovations.append(self._to_renovation_dto(project, house))

        # Active first, newest first within each group.
        constructions.sort(key=lambda p: (p.status != STATUS_IN_PROGRESS, -p.id))
        renovations.sort(key=lambda p: (p.status != STATUS_IN_PROGRESS, -p.id))
        return ProjectsStatusData(
            constructions=tuple(constructions), renovations=tuple(renovations)
        )

    # --- Lazy completion -----------------------------------------------------------------

    async def settle_due(self) -> int:
        """Complete every due construction and renovation.

        Safe to call as often as wanted — each completion is claimed
        atomically, so concurrent callers never double-apply. Returns how
        many projects completed. A future scheduler/cron can call this
        periodically instead of relying on lazy settlement.
        """
        completed = await self._settle_due_constructions()
        completed += await self._settle_due_renovations()
        return completed

    async def _settle_due_constructions(self) -> int:
        now = _utc_now()
        xp_grants: list[tuple[int, int]] = []  # (player_id, cost)

        async with self._session_factory() as session:
            project_repo = ConstructionProjectRepository(session)
            land_repo = LandRepository(session)
            house_repo = HouseRepository(session)
            upgrade_repo = PropertyUpgradeRepository(session)

            settled = 0
            for project in await project_repo.list_due(now):
                claimed = await project_repo.claim_completion(project.id, now)
                if not claimed:
                    continue  # another settler won the race

                land = await land_repo.get_by_id(project.land_id)
                if land is None:  # pragma: no cover — land is CASCADE-protected
                    continue

                house = await house_repo.create(
                    city=land.city,
                    neighborhood=land.neighborhood,
                    area_sqm=project.area_sqm,
                    bedrooms=project.bedrooms,
                    living_rooms=project.living_rooms,
                    bathrooms=project.bathrooms,
                    kitchen_type=project.kitchen_type,
                    construction_year=current_iranian_year(),
                    parking=project.parking,
                    elevator=project.elevator,
                    storage=project.storage,
                    quality=construction_domain.QUALITY_TOKENS.get(
                        project.quality, "خوب"
                    ),
                    owner_player_id=project.owner_player_id,
                )
                await land_repo.mark_built(land.id, house.id)
                await project_repo.set_house(project.id, house.id)

                value_after = self.house_value(house)
                await upgrade_repo.create(
                    property_type="house",
                    property_id=house.id,
                    player_id=project.owner_player_id,
                    upgrade_kind="construction",
                    description=(
                        f"ساخت {construction_domain.BUILDING_TYPE_LABELS.get(project.building_type, '')}"
                        f" {project.area_sqm} متری، {project.floors} طبقه روی زمین #{land.id}"
                    ),
                    value_before=None,
                    value_after=value_after,
                    cost=project.cost_total,
                )
                xp_grants.append((project.owner_player_id, project.cost_total))
                settled += 1
                logger.info(
                    "Construction %s completed: house %s created on land %s (value %s)",
                    project.id, house.id, land.id, value_after,
                )

            if settled:
                await session.commit()

        for owner_id, cost in xp_grants:
            await self._grant_construction_xp(owner_id, cost)
        return settled

    async def _settle_due_renovations(self) -> int:
        now = _utc_now()

        async with self._session_factory() as session:
            project_repo = RenovationProjectRepository(session)
            house_repo = HouseRepository(session)
            upgrade_repo = PropertyUpgradeRepository(session)

            settled = 0
            for project in await project_repo.list_due(now):
                claimed = await project_repo.claim_completion(project.id, now)
                if not claimed:
                    continue

                house = await house_repo.get_by_id(project.house_id)
                if house is None:  # pragma: no cover — house is CASCADE-protected
                    continue

                value_before = self.house_value(house)
                try:
                    changes = renovation_domain.apply_renovation(
                        house, project.renovation_type
                    )
                except ValueError:  # pragma: no cover — quote snapshotted at start
                    logger.warning(
                        "Renovation %s no longer applicable; completing as no-op",
                        project.id,
                    )
                    changes = {}
                if changes:
                    await house_repo.update_attributes(house.id, **changes)
                    # Re-read the changed house to value it after the work.
                    house = await house_repo.get_by_id(project.house_id)
                value_after = self.house_value(house)

                await upgrade_repo.create(
                    property_type="house",
                    property_id=project.house_id,
                    player_id=project.owner_player_id,
                    upgrade_kind=project.renovation_type,
                    description=(
                        f"{project.title}"
                        + (f" — {project.description}" if project.description else "")
                    ),
                    value_before=value_before,
                    value_after=value_after,
                    cost=project.cost,
                )
                settled += 1
                logger.info(
                    "Renovation %s completed on house %s: value %s -> %s",
                    project.id, project.house_id, value_before, value_after,
                )

            if settled:
                await session.commit()
        return settled

    async def get_property_upgrades(
        self, property_type: str, property_id: int, limit: int = 10
    ) -> list[PropertyUpgradeData]:
        """The value history of one property (from the audit trail)."""
        async with self._session_factory() as session:
            rows = await PropertyUpgradeRepository(session).list_by_property(
                property_type, property_id, limit
            )
            return [
                PropertyUpgradeData(
                    id=row.id,
                    property_type=row.property_type,
                    property_id=row.property_id,
                    player_id=row.player_id,
                    upgrade_kind=row.upgrade_kind,
                    description=row.description,
                    value_before=row.value_before,
                    value_after=row.value_after,
                    cost=row.cost,
                    created_at=row.created_at,
                )
                for row in rows
            ]

    # --- Helpers ------------------------------------------------------------------------

    async def _balance(self, player_id: int) -> int:
        async with self._session_factory() as session:
            balance = await PlayerRepository(session).get_money(player_id)
        if balance is None:  # pragma: no cover — existence guarded upstream
            raise PlayerNotFoundError(f"player_id={player_id} not found")
        return balance

    async def _grant_construction_xp(self, player_id: int, cost: int) -> int:
        """Grant XP for finishing a construction via the LevelService."""
        if self._level_service is None:
            return 0
        amount = max(
            admin_runtime.purchase_xp_min(),
            min(
                admin_runtime.purchase_xp_max(),
                cost // admin_runtime.construction_xp_divisor(),
            ),
        )
        try:
            await self._level_service.add_xp(
                player_id, amount, reason=constants.CONSTRUCTION_XP_REASON
            )
        except Exception:  # noqa: BLE001 — XP is a bonus, never blocks completion
            logger.warning(
                "Could not grant construction XP to player %s", player_id, exc_info=True
            )
            return 0
        return amount
