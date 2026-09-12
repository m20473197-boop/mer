"""Repository for the ``lands`` table — ownership and lookup queries."""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.land import Land


class LandRepository:
    """All database operations for land parcels."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reads ------------------------------------------------------------

    async def get_by_id(self, land_id: int) -> Land | None:
        return await self._session.get(Land, land_id)

    async def list_by_owner(self, player_id: int) -> list[Land]:
        statement = (
            select(Land).where(Land.owner_player_id == player_id).order_by(Land.id)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_unowned(self) -> list[Land]:
        """All system-market parcels (no owner yet)."""
        statement = (
            select(Land).where(Land.owner_player_id.is_(None)).order_by(Land.id)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_all(self) -> list[Land]:
        result = await self._session.execute(select(Land).order_by(Land.id))
        return list(result.scalars().all())

    async def list_page(self, offset: int, limit: int) -> list[Land]:
        """One page of parcels for the admin panel, oldest first."""
        statement = select(Land).order_by(Land.id).offset(offset).limit(limit)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def count(self) -> int:
        result = await self._session.execute(select(func.count(Land.id)))
        return int(result.scalar_one())

    # --- Writes -----------------------------------------------------------

    def add(self, land: Land) -> None:
        self._session.add(land)

    async def create(
        self,
        *,
        city: str,
        neighborhood: str,
        area_sqm: int,
        location_quality: str,
        owner_player_id: int | None = None,
    ) -> Land:
        land = Land(
            city=city,
            neighborhood=neighborhood,
            area_sqm=area_sqm,
            location_quality=location_quality,
            owner_player_id=owner_player_id,
        )
        self._session.add(land)
        await self._session.flush()
        return land

    async def set_owner(self, land_id: int, owner_player_id: int | None) -> bool:
        """Transfer ownership (``None`` returns the parcel to the market)."""
        statement = (
            update(Land)
            .where(Land.id == land_id)
            .values(owner_player_id=owner_player_id)
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)

    async def transfer_owner_if(
        self, land_id: int, from_player_id: int, to_player_id: int
    ) -> bool:
        """Transfer only while the expected seller still owns the parcel."""
        statement = (
            update(Land)
            .where(
                Land.id == land_id,
                Land.owner_player_id == from_player_id,
            )
            .values(owner_player_id=to_player_id)
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)

    async def update_attributes(self, land_id: int, **fields: object) -> bool:
        """Update a whitelisted set of parcel attributes (admin panel).

        Only real Land columns may be passed; anything else is rejected so a
        typo can never silently corrupt a property record.
        """
        allowed = {
            "city",
            "neighborhood",
            "area_sqm",
            "location_quality",
            "price_override_per_mille",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unknown land attributes: {sorted(unknown)}")
        if not fields:
            return False
        statement = update(Land).where(Land.id == land_id).values(**fields)
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        cached = await self._session.get(Land, land_id)
        if cached is not None:
            self._session.expire(cached)
        return bool(result.rowcount)

    async def mark_built(self, land_id: int, house_id: int) -> bool:
        """Link the finished house — the parcel can never be built on again."""
        statement = (
            update(Land)
            .where(Land.id == land_id)
            .values(built_house_id=house_id)
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)
