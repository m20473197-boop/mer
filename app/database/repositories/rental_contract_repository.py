"""Repository for the ``rental_contracts`` table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.rental_contract import RentalContract


class RentalContractRepository:
    """All database operations for rental contracts."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reads ------------------------------------------------------------

    async def get_by_id(self, contract_id: int) -> RentalContract | None:
        return await self._session.get(RentalContract, contract_id)

    async def get_active_by_house(self, house_id: int) -> RentalContract | None:
        statement = select(RentalContract).where(
            RentalContract.house_id == house_id, RentalContract.is_active.is_(True)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_active_by_tenant(self, tenant_player_id: int) -> RentalContract | None:
        statement = select(RentalContract).where(
            RentalContract.tenant_player_id == tenant_player_id,
            RentalContract.is_active.is_(True),
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_active_by_tenant(self, tenant_player_id: int) -> list[RentalContract]:
        statement = (
            select(RentalContract)
            .where(
                RentalContract.tenant_player_id == tenant_player_id,
                RentalContract.is_active.is_(True),
            )
            .order_by(RentalContract.created_at.desc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_active_by_owner(self, owner_player_id: int) -> list[RentalContract]:
        statement = (
            select(RentalContract)
            .where(
                RentalContract.owner_player_id == owner_player_id,
                RentalContract.is_active.is_(True),
            )
            .order_by(RentalContract.created_at.desc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def count_active(self) -> int:
        result = await self._session.execute(
            select(func.count(RentalContract.id)).where(
                RentalContract.is_active.is_(True)
            )
        )
        return int(result.scalar_one())

    async def list_page(
        self, offset: int, limit: int, *, active_only: bool = True
    ) -> list[RentalContract]:
        """One page of contracts for the admin panel, oldest first."""
        statement = select(RentalContract).order_by(RentalContract.id)
        if active_only:
            statement = statement.where(RentalContract.is_active.is_(True))
        statement = statement.offset(offset).limit(limit)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_by_house(self, house_id: int, limit: int = 20) -> list[RentalContract]:
        statement = (
            select(RentalContract)
            .where(RentalContract.house_id == house_id)
            .order_by(RentalContract.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    # --- Writes -----------------------------------------------------------

    async def create(
        self,
        *,
        house_id: int,
        owner_player_id: int,
        tenant_player_id: int,
        monthly_rent: int,
        deposit: int,
        next_due_at: datetime,
        listing_id: int | None = None,
    ) -> RentalContract:
        contract = RentalContract(
            house_id=house_id,
            owner_player_id=owner_player_id,
            tenant_player_id=tenant_player_id,
            monthly_rent=monthly_rent,
            deposit=deposit,
            listing_id=listing_id,
            started_at=datetime.utcnow(),
            next_due_at=next_due_at,
            is_active=True,
        )
        self._session.add(contract)
        await self._session.flush()
        return contract

    async def end(self, contract_id: int, when: datetime) -> bool:
        contract = await self._session.get(RentalContract, contract_id)
        if contract is None or not contract.is_active:
            return False
        contract.is_active = False
        contract.ended_at = when
        self._session.add(contract)
        await self._session.flush()
        return True

    async def advance_due_date(
        self, contract_id: int, next_due_at: datetime
    ) -> bool:
        contract = await self._session.get(RentalContract, contract_id)
        if contract is None:
            return False
        contract.next_due_at = next_due_at
        self._session.add(contract)
        await self._session.flush()
        return True
