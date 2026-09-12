"""Database access for children (``children``)."""

from __future__ import annotations

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.child import Child


class ChildRepository:
    """All database operations for the ``children`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, child_id: int) -> Child | None:
        return await self._session.get(Child, child_id)

    async def list_by_player(self, player_id: int, limit: int = 50) -> list[Child]:
        statement = (
            select(Child)
            .where(
                or_(
                    Child.father_player_id == player_id,
                    Child.mother_player_id == player_id,
                )
            )
            .order_by(Child.id)
            .limit(limit)
        )
        return list((await self._session.execute(statement)).scalars().all())

    async def list_by_marriage(self, marriage_id: int, limit: int = 50) -> list[Child]:
        statement = (
            select(Child)
            .where(Child.marriage_id == marriage_id)
            .order_by(Child.id)
            .limit(limit)
        )
        return list((await self._session.execute(statement)).scalars().all())

    async def count_by_marriage(self, marriage_id: int) -> int:
        statement = select(func.count(Child.id)).where(Child.marriage_id == marriage_id)
        return int((await self._session.execute(statement)).scalar_one() or 0)

    async def count_by_player(self, player_id: int) -> int:
        statement = select(func.count(Child.id)).where(
            or_(Child.father_player_id == player_id, Child.mother_player_id == player_id)
        )
        return int((await self._session.execute(statement)).scalar_one() or 0)

    def add(self, child: Child) -> None:
        self._session.add(child)

    async def set_growth_stage(self, child_id: int, stage: str) -> None:
        statement = (
            update(Child).where(Child.id == child_id).values(growth_stage=stage)
        )
        await self._session.execute(statement, execution_options={"synchronize_session": False})

    async def add_expenses(self, child_id: int, amount: int) -> None:
        """Future hook for the family-expenses system (never called yet)."""
        statement = (
            update(Child)
            .where(Child.id == child_id)
            .values(expenses_total=Child.expenses_total + amount)
        )
        await self._session.execute(statement, execution_options={"synchronize_session": False})


__all__ = ["ChildRepository"]
