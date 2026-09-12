"""Repository for the ``property_upgrades`` table (value audit trail)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.property_upgrade import PropertyUpgrade


class PropertyUpgradeRepository:
    """All database operations for property upgrade records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reads ------------------------------------------------------------

    async def get_by_id(self, upgrade_id: int) -> PropertyUpgrade | None:
        return await self._session.get(PropertyUpgrade, upgrade_id)

    async def list_by_property(
        self, property_type: str, property_id: int, limit: int = 20
    ) -> list[PropertyUpgrade]:
        statement = (
            select(PropertyUpgrade)
            .where(
                PropertyUpgrade.property_type == property_type,
                PropertyUpgrade.property_id == property_id,
            )
            .order_by(PropertyUpgrade.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_by_player(
        self, player_id: int, limit: int = 20
    ) -> list[PropertyUpgrade]:
        statement = (
            select(PropertyUpgrade)
            .where(PropertyUpgrade.player_id == player_id)
            .order_by(PropertyUpgrade.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    # --- Writes -----------------------------------------------------------

    async def create(
        self,
        *,
        property_type: str,
        property_id: int,
        upgrade_kind: str,
        description: str = "",
        value_before: int | None = None,
        value_after: int | None = None,
        cost: int = 0,
        player_id: int | None = None,
    ) -> PropertyUpgrade:
        upgrade = PropertyUpgrade(
            property_type=property_type,
            property_id=property_id,
            player_id=player_id,
            upgrade_kind=upgrade_kind,
            description=description,
            value_before=value_before,
            value_after=value_after,
            cost=cost,
        )
        self._session.add(upgrade)
        await self._session.flush()
        return upgrade
