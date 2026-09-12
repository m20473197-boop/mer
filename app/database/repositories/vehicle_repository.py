"""Repositories for the fixed vehicle catalog and player ownership."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.vehicle_model import VehicleModel
from app.database.models.vehicle_ownership import (
    VEHICLE_OWNERSHIP_OWNED,
    VehicleOwnership,
)
from app.game.vehicle.catalog import (
    VEHICLE_MODEL_AVAILABLE,
    VehicleCatalogDefinition,
)


class VehicleModelRepository:
    """Database access for predefined dealership models."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, model_id: int) -> VehicleModel | None:
        return await self._session.get(VehicleModel, model_id)

    async def get_by_code(self, code: str) -> VehicleModel | None:
        statement = select(VehicleModel).where(VehicleModel.code == code)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_all(self) -> list[VehicleModel]:
        statement = select(VehicleModel).order_by(VehicleModel.id)
        return list((await self._session.execute(statement)).scalars().all())

    async def list_available(self) -> list[VehicleModel]:
        statement = (
            select(VehicleModel)
            .where(VehicleModel.availability_status == VEHICLE_MODEL_AVAILABLE)
            .order_by(VehicleModel.id)
        )
        return list((await self._session.execute(statement)).scalars().all())

    async def create_from_definition(
        self, definition: VehicleCatalogDefinition
    ) -> VehicleModel:
        model = VehicleModel(
            id=definition.model_id,
            code=definition.code,
            name=definition.name,
            purchase_price=definition.purchase_price,
            availability_status=definition.availability_status,
            shoti_eligible=definition.is_shoti_eligible,
        )
        self._session.add(model)
        await self._session.flush()
        return model


class VehicleOwnershipRepository:
    """Database access for player-owned vehicle rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, ownership_id: int) -> VehicleOwnership | None:
        return await self._session.get(VehicleOwnership, ownership_id)

    async def get_owned_by_player_and_model(
        self, owner_player_id: int, vehicle_model_id: int
    ) -> VehicleOwnership | None:
        statement = select(VehicleOwnership).where(
            VehicleOwnership.owner_player_id == owner_player_id,
            VehicleOwnership.vehicle_model_id == vehicle_model_id,
            VehicleOwnership.status == VEHICLE_OWNERSHIP_OWNED,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def count_owned_by_player(self, owner_player_id: int) -> int:
        statement = select(func.count(VehicleOwnership.id)).where(
            VehicleOwnership.owner_player_id == owner_player_id,
            VehicleOwnership.status == VEHICLE_OWNERSHIP_OWNED,
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def list_owned_with_models(
        self, owner_player_id: int
    ) -> list[tuple[VehicleOwnership, VehicleModel]]:
        statement = (
            select(VehicleOwnership, VehicleModel)
            .join(VehicleModel, VehicleModel.id == VehicleOwnership.vehicle_model_id)
            .where(
                VehicleOwnership.owner_player_id == owner_player_id,
                VehicleOwnership.status == VEHICLE_OWNERSHIP_OWNED,
            )
            .order_by(VehicleOwnership.purchased_at.desc(), VehicleOwnership.id.desc())
        )
        return list((await self._session.execute(statement)).all())

    async def get_owned_with_model(
        self, owner_player_id: int, ownership_id: int
    ) -> tuple[VehicleOwnership, VehicleModel] | None:
        statement = (
            select(VehicleOwnership, VehicleModel)
            .join(VehicleModel, VehicleModel.id == VehicleOwnership.vehicle_model_id)
            .where(
                VehicleOwnership.id == ownership_id,
                VehicleOwnership.owner_player_id == owner_player_id,
                VehicleOwnership.status == VEHICLE_OWNERSHIP_OWNED,
            )
        )
        return (await self._session.execute(statement)).one_or_none()

    async def create(
        self,
        *,
        owner_player_id: int,
        vehicle_model_id: int,
        purchase_price: int,
        purchased_at: datetime,
    ) -> VehicleOwnership:
        ownership = VehicleOwnership(
            owner_player_id=owner_player_id,
            vehicle_model_id=vehicle_model_id,
            purchase_price=purchase_price,
            purchased_at=purchased_at,
            status=VEHICLE_OWNERSHIP_OWNED,
        )
        self._session.add(ownership)
        await self._session.flush()
        return ownership
