"""Service layer for 🚗 نمایشگاه ماشین حاج ممد.

The catalog is fixed and predefined, while its persisted model rows keep
prices/availability configurable for future administration. Players can only
buy existing catalog models; no service method creates custom models.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import constants
from app.database.models.vehicle_model import VehicleModel
from app.database.models.vehicle_ownership import VehicleOwnership
from app.database.repositories.player_repository import PlayerRepository
from app.database.repositories.vehicle_repository import (
    VehicleModelRepository,
    VehicleOwnershipRepository,
)
from app.game.shared.errors import DomainError, PlayerNotFoundError
from app.game.vehicle.catalog import (
    SHOTI_COMPATIBILITY_TAG,
    VEHICLE_CATALOG,
    VEHICLE_MODEL_AVAILABLE,
    get_catalog_definition,
    is_supported_model_id,
)
from app.game.vehicle.dto import (
    VehicleModelData,
    VehicleOwnershipData,
    VehiclePurchaseResult,
)
from app.services.money_service import MoneyService

logger = logging.getLogger(__name__)


class VehicleModelNotFoundError(DomainError):
    """The requested model is not part of the fixed catalog/database."""


class VehicleUnavailableError(DomainError):
    """The model exists but is not currently available in the showroom."""


class VehicleInvalidPriceError(DomainError):
    """A persisted model price is not a valid positive integer."""


class VehicleAlreadyOwnedError(DomainError):
    """The player already owns an active vehicle of this model."""


class VehicleOwnershipLimitReachedError(DomainError):
    """The configurable per-player vehicle limit has been reached."""


class VehicleNotOwnedError(DomainError):
    """The requested ownership row belongs to another player or is inactive."""


class VehiclePurchaseError(DomainError):
    """The purchase could not be persisted atomically."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class VehicleService:
    """Business rules and transaction boundary for the vehicle dealership."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        money_service: MoneyService,
        ownership_limit: int | None = constants.VEHICLE_OWNERSHIP_LIMIT,
    ) -> None:
        if ownership_limit is not None and ownership_limit < 0:
            raise ValueError("ownership_limit must be non-negative or None")
        self._session_factory = session_factory
        self._money = money_service
        self._ownership_limit = ownership_limit
        self._catalog_lock = asyncio.Lock()
        self._purchase_locks: dict[int, asyncio.Lock] = {}

    @property
    def ownership_limit(self) -> int | None:
        """Configured cap; ``None`` means no arbitrary gameplay cap."""
        return self._ownership_limit

    # --- Catalog ------------------------------------------------------------

    async def ensure_catalog(self) -> list[VehicleModelData]:
        """Create missing fixed catalog rows without resetting configured data.

        The in-process lock prevents two first Telegram requests from trying
        to seed the same SQLite table at once. The bounded retry also handles
        another bot process performing the same additive startup migration.
        """
        async with self._catalog_lock:
            for attempt in range(2):
                try:
                    async with self._session_factory() as session:
                        repository = VehicleModelRepository(session)
                        existing = {
                            model.id for model in await repository.list_all()
                        }
                        for definition in VEHICLE_CATALOG:
                            if definition.model_id not in existing:
                                await repository.create_from_definition(definition)
                        await session.commit()
                        models = [
                            model
                            for model in await repository.list_all()
                            if self._is_fixed_model(model)
                        ]
                        return [
                            self._to_model_dto(model) for model in models
                        ]
                except IntegrityError:
                    if attempt == 1:
                        raise
                    # Another process/request won the catalog insert race. Its
                    # commit is visible on the retry's fresh session.
                    continue
            return []  # pragma: no cover - the retry loop always returns/raises

    async def get_catalog(self, *, include_unavailable: bool = True) -> list[VehicleModelData]:
        """Return persisted catalog rows in stable model-id order."""
        await self.ensure_catalog()
        async with self._session_factory() as session:
            repository = VehicleModelRepository(session)
            models = (
                await repository.list_all()
                if include_unavailable
                else await repository.list_available()
            )
            return [
                self._to_model_dto(model)
                for model in models
                if self._is_fixed_model(model)
            ]

    async def get_available_vehicles(self) -> list[VehicleModelData]:
        """Descriptive alias for the available showroom catalog."""
        return await self.get_catalog(include_unavailable=False)

    async def get_model(self, model_id: int) -> VehicleModelData:
        """Return one server-known model after validating the model id."""
        self._validate_model_id(model_id)
        await self.ensure_catalog()
        async with self._session_factory() as session:
            model = await VehicleModelRepository(session).get_by_id(model_id)
            if model is None or not self._is_fixed_model(model):
                raise VehicleModelNotFoundError(str(model_id))
            return self._to_model_dto(model)

    # --- Owned vehicles -----------------------------------------------------

    async def get_owned_vehicles(self, player_id: int) -> list[VehicleOwnershipData]:
        async with self._session_factory() as session:
            await self._require_player(session, player_id)
            rows = await VehicleOwnershipRepository(session).list_owned_with_models(
                player_id
            )
            return [
                self._to_ownership_dto(ownership, model)
                for ownership, model in rows
                if self._is_fixed_model(model)
            ]

    async def get_owned_cars(self, player_id: int) -> list[VehicleOwnershipData]:
        """Alias used by the Persian «ماشین‌های من» screen."""
        return await self.get_owned_vehicles(player_id)

    async def get_owned_vehicle(
        self, player_id: int, ownership_id: int
    ) -> VehicleOwnershipData:
        if isinstance(ownership_id, bool) or not isinstance(ownership_id, int) or ownership_id <= 0:
            raise VehicleNotOwnedError(str(ownership_id))
        async with self._session_factory() as session:
            await self._require_player(session, player_id)
            row = await VehicleOwnershipRepository(session).get_owned_with_model(
                player_id, ownership_id
            )
            if row is None:
                raise VehicleNotOwnedError(str(ownership_id))
            ownership, model = row
            if not self._is_fixed_model(model):
                raise VehicleNotOwnedError(str(ownership_id))
            return self._to_ownership_dto(ownership, model)

    # --- Purchase -----------------------------------------------------------

    async def buy_vehicle(
        self, player_id: int, model_id: int
    ) -> VehiclePurchaseResult:
        """Alias for callers that name the use case as a vehicle purchase."""
        return await self.purchase(player_id, model_id)

    async def purchase(
        self, player_id: int, model_id: int
    ) -> VehiclePurchaseResult:
        """Buy one predefined model atomically with the existing wallet."""
        self._validate_model_id(model_id)
        # Seeding is additive and happens before the money transaction. It
        # cannot debit a wallet or create an ownership row.
        await self.ensure_catalog()
        purchase_lock = self._purchase_locks.setdefault(player_id, asyncio.Lock())
        async with purchase_lock:
            return await self._purchase_in_transaction(player_id, model_id)

    async def _purchase_in_transaction(
        self, player_id: int, model_id: int
    ) -> VehiclePurchaseResult:
        async with self._session_factory() as session:
            await self._require_player(session, player_id)
            model_repository = VehicleModelRepository(session)
            ownership_repository = VehicleOwnershipRepository(session)
            model = await model_repository.get_by_id(model_id)
            if model is None or not self._is_fixed_model(model):
                raise VehicleModelNotFoundError(str(model_id))
            if model.availability_status != VEHICLE_MODEL_AVAILABLE:
                raise VehicleUnavailableError(model.name)
            self._validate_price(model.purchase_price)
            # Cache scalar values before the transaction can be rolled back;
            # SQLAlchemy expires ORM attributes on rollback.
            persisted_model_id = model.id
            model_name = model.name
            purchase_price = model.purchase_price

            existing = await ownership_repository.get_owned_by_player_and_model(
                player_id, persisted_model_id
            )
            if existing is not None:
                raise VehicleAlreadyOwnedError(model_name)
            if (
                self._ownership_limit is not None
                and await ownership_repository.count_owned_by_player(player_id)
                >= self._ownership_limit
            ):
                raise VehicleOwnershipLimitReachedError(str(self._ownership_limit))

            logger.info(
                "Vehicle purchase attempt: player=%s model=%s price=%s",
                player_id,
                persisted_model_id,
                purchase_price,
            )
            wallet_result = await self._money.remove_money_in_transaction(
                session, player_id, purchase_price
            )
            try:
                ownership = await ownership_repository.create(
                    owner_player_id=player_id,
                    vehicle_model_id=persisted_model_id,
                    purchase_price=purchase_price,
                    purchased_at=_utc_now(),
                )
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                # Usually the partial unique index won a concurrent repeated
                # callback. Confirm that case without exposing SQL details.
                if await ownership_repository.get_owned_by_player_and_model(
                    player_id, persisted_model_id
                ) is not None:
                    raise VehicleAlreadyOwnedError(model_name) from exc
                logger.error(
                    "Vehicle purchase database conflict: player=%s model=%s",
                    player_id,
                    persisted_model_id,
                )
                raise VehiclePurchaseError(model_name) from exc

            result = VehiclePurchaseResult(
                ownership=self._to_ownership_dto(ownership, model),
                wallet_balance_after=wallet_result.balance_after,
            )
            logger.info(
                "Vehicle purchase successful: player=%s model=%s ownership=%s",
                player_id,
                model.id,
                ownership.id,
            )
            return result

    # --- Internal helpers --------------------------------------------------

    @staticmethod
    def _is_fixed_model(model: VehicleModel) -> bool:
        definition = get_catalog_definition(model.id)
        return definition is not None and model.code == definition.code

    @staticmethod
    def _validate_model_id(model_id: int) -> None:
        if (
            isinstance(model_id, bool)
            or not isinstance(model_id, int)
            or model_id <= 0
            or not is_supported_model_id(model_id)
        ):
            raise VehicleModelNotFoundError(str(model_id))

    @staticmethod
    def _validate_price(price: int) -> None:
        if isinstance(price, bool) or not isinstance(price, int) or price <= 0:
            raise VehicleInvalidPriceError(str(price))

    async def _require_player(self, session: AsyncSession, player_id: int) -> None:
        if not isinstance(player_id, int) or isinstance(player_id, bool):
            raise PlayerNotFoundError(str(player_id))
        if not await PlayerRepository(session).exists(player_id):
            raise PlayerNotFoundError(f"player_id={player_id} not found")

    @staticmethod
    def _to_model_dto(model: VehicleModel) -> VehicleModelData:
        compatibility = (SHOTI_COMPATIBILITY_TAG,) if model.shoti_eligible else ()
        return VehicleModelData(
            model_id=model.id,
            code=model.code,
            name=model.name,
            purchase_price=model.purchase_price,
            availability_status=model.availability_status,
            future_compatibility=compatibility,
        )

    @classmethod
    def _to_ownership_dto(
        cls, ownership: VehicleOwnership, model: VehicleModel
    ) -> VehicleOwnershipData:
        return VehicleOwnershipData(
            ownership_id=ownership.id,
            owner_player_id=ownership.owner_player_id,
            model=cls._to_model_dto(model),
            purchase_price=ownership.purchase_price,
            purchased_at=(
                ownership.purchased_at
                if ownership.purchased_at.tzinfo is not None
                else ownership.purchased_at.replace(tzinfo=timezone.utc)
            ),
            status=ownership.status,
        )
