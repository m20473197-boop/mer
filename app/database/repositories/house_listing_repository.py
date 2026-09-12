"""Repository for the ``house_listings`` table (sale + rent offers)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.house_listing import (
    LISTING_RENT,
    LISTING_SALE,
    STATUS_ACTIVE,
    STATUS_CLOSED,
    HouseListing,
)


class HouseListingRepository:
    """All database operations for house listings."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reads ------------------------------------------------------------

    async def get_by_id(self, listing_id: int) -> HouseListing | None:
        return await self._session.get(HouseListing, listing_id)

    async def get_active_by_house_and_type(
        self, house_id: int, listing_type: str
    ) -> HouseListing | None:
        statement = select(HouseListing).where(
            HouseListing.house_id == house_id,
            HouseListing.listing_type == listing_type,
            HouseListing.status == STATUS_ACTIVE,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_active_sale_by_house(self, house_id: int) -> HouseListing | None:
        return await self.get_active_by_house_and_type(house_id, LISTING_SALE)

    async def get_active_rent_by_house(self, house_id: int) -> HouseListing | None:
        return await self.get_active_by_house_and_type(house_id, LISTING_RENT)

    async def list_active_by_type(self, listing_type: str) -> list[HouseListing]:
        statement = (
            select(HouseListing)
            .where(
                HouseListing.listing_type == listing_type,
                HouseListing.status == STATUS_ACTIVE,
            )
            .order_by(HouseListing.created_at.desc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_active_sales(self) -> list[HouseListing]:
        return await self.list_active_by_type(LISTING_SALE)

    async def list_active_rents(self) -> list[HouseListing]:
        return await self.list_active_by_type(LISTING_RENT)

    async def list_active_by_owner(self, player_id: int) -> list[HouseListing]:
        statement = (
            select(HouseListing)
            .where(
                HouseListing.owner_player_id == player_id,
                HouseListing.status == STATUS_ACTIVE,
            )
            .order_by(HouseListing.created_at.desc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def has_any_active_for_house(self, house_id: int) -> bool:
        statement = (
            select(HouseListing.id)
            .where(HouseListing.house_id == house_id, HouseListing.status == STATUS_ACTIVE)
            .limit(1)
        )
        return (await self._session.execute(statement)).scalar() is not None

    # --- Admin reads --------------------------------------------------------

    async def count_active(self, listing_type: str | None = None) -> int:
        statement = select(func.count(HouseListing.id)).where(
            HouseListing.status == STATUS_ACTIVE
        )
        if listing_type is not None:
            statement = statement.where(HouseListing.listing_type == listing_type)
        return int((await self._session.execute(statement)).scalar_one())

    async def list_active_page(
        self, listing_type: str | None, offset: int, limit: int
    ) -> list[HouseListing]:
        """One page of active listings (``None`` = both sale and rent)."""
        statement = (
            select(HouseListing)
            .where(HouseListing.status == STATUS_ACTIVE)
            .order_by(HouseListing.id)
            .offset(offset)
            .limit(limit)
        )
        if listing_type is not None:
            statement = statement.where(HouseListing.listing_type == listing_type)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    # --- Writes -----------------------------------------------------------

    async def create(
        self,
        *,
        house_id: int,
        owner_player_id: int | None,
        listing_type: str,
        price: int,
        deposit: int = 0,
    ) -> HouseListing:
        listing = HouseListing(
            house_id=house_id,
            owner_player_id=owner_player_id,
            listing_type=listing_type,
            price=price,
            deposit=deposit,
            status=STATUS_ACTIVE,
        )
        self._session.add(listing)
        await self._session.flush()
        return listing

    async def close(self, listing_id: int, when: datetime) -> bool:
        """Mark a listing closed (sold, rented out, or cancelled)."""
        listing = await self._session.get(HouseListing, listing_id)
        if listing is None:
            return False
        listing.status = STATUS_CLOSED
        listing.closed_at = when
        self._session.add(listing)
        await self._session.flush()
        return True

    async def purge_closed_older_than(self, cutoff: datetime) -> int:
        """Delete closed listings shut before ``cutoff``; returns rows removed."""
        statement = delete(HouseListing).where(
            HouseListing.status == STATUS_CLOSED,
            HouseListing.closed_at.is_not(None),
            HouseListing.closed_at < cutoff,
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return int(result.rowcount or 0)

    async def close_active_for_house(self, house_id: int, when: datetime) -> int:
        """Close every active listing on a house; returns how many closed."""
        statement = select(HouseListing).where(
            HouseListing.house_id == house_id,
            HouseListing.status == STATUS_ACTIVE,
        )
        result = await self._session.execute(statement)
        count = 0
        for listing in result.scalars().all():
            listing.status = STATUS_CLOSED
            listing.closed_at = when
            self._session.add(listing)
            count += 1
        if count:
            await self._session.flush()
        return count
