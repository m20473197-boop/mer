"""Database access for ``marketplace_listings``.

All active-listing filtering and pagination stays in SQL. The service layer
only hydrates the small result page with the existing house/land DTOs.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, func, or_, select, update, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.house import House
from app.database.models.land import Land
from app.database.models.marketplace_listing import MarketplaceListing
from app.game.marketplace.catalog import (
    ASSET_TYPE_HOUSE,
    ASSET_TYPE_LAND,
    LISTING_STATUS_ACTIVE,
    LISTING_STATUS_CANCELLED,
    LISTING_STATUS_SOLD,
)
from app.game.marketplace.dto import MarketplaceSearchCriteria


class MarketplaceListingRepository:
    """Queries and conditional state changes for Divar listings."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, listing_id: int) -> MarketplaceListing | None:
        return await self._session.get(MarketplaceListing, listing_id)

    async def get_active_by_asset(
        self, asset_type: str, asset_id: int
    ) -> MarketplaceListing | None:
        statement = select(MarketplaceListing).where(
            MarketplaceListing.asset_type == asset_type,
            MarketplaceListing.asset_id == asset_id,
            MarketplaceListing.status == LISTING_STATUS_ACTIVE,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_active_by_seller(self, seller_player_id: int) -> list[MarketplaceListing]:
        statement = (
            select(MarketplaceListing)
            .where(
                MarketplaceListing.seller_player_id == seller_player_id,
                MarketplaceListing.status == LISTING_STATUS_ACTIVE,
            )
            .order_by(MarketplaceListing.created_at.desc(), MarketplaceListing.id.desc())
        )
        return list((await self._session.execute(statement)).scalars().all())

    async def create(
        self,
        *,
        seller_player_id: int,
        asset_type: str,
        asset_id: int,
        price: int,
    ) -> MarketplaceListing:
        listing = MarketplaceListing(
            seller_player_id=seller_player_id,
            asset_type=asset_type,
            asset_id=asset_id,
            price=price,
            status=LISTING_STATUS_ACTIVE,
        )
        self._session.add(listing)
        await self._session.flush()
        return listing

    async def cancel_if_active(
        self, listing_id: int, seller_player_id: int, when: datetime
    ) -> bool:
        statement = (
            update(MarketplaceListing)
            .where(
                MarketplaceListing.id == listing_id,
                MarketplaceListing.seller_player_id == seller_player_id,
                MarketplaceListing.status == LISTING_STATUS_ACTIVE,
            )
            .values(status=LISTING_STATUS_CANCELLED, cancelled_at=when)
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)

    async def mark_sold_if_active(
        self,
        listing_id: int,
        buyer_player_id: int,
        when: datetime,
    ) -> bool:
        """Close one listing only while it is still active."""
        statement = (
            update(MarketplaceListing)
            .where(
                MarketplaceListing.id == listing_id,
                MarketplaceListing.status == LISTING_STATUS_ACTIVE,
            )
            .values(
                status=LISTING_STATUS_SOLD,
                buyer_player_id=buyer_player_id,
                sold_at=when,
            )
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)

    async def search_active(
        self,
        criteria: MarketplaceSearchCriteria,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[MarketplaceListing], int]:
        """Return one filtered page and its total count, entirely in SQL."""
        statements = self._asset_id_statements(criteria)
        if not statements:
            return [], 0
        matching_ids = union_all(*statements).subquery("matching_marketplace_ids")
        count_statement = select(func.count()).select_from(matching_ids)
        total = int((await self._session.execute(count_statement)).scalar_one())
        statement = (
            select(MarketplaceListing)
            .join(matching_ids, MarketplaceListing.id == matching_ids.c.id)
            .order_by(
                MarketplaceListing.created_at.desc(), MarketplaceListing.id.desc()
            )
            .offset(max(0, offset))
            .limit(max(1, limit))
        )
        listings = list((await self._session.execute(statement)).scalars().all())
        return listings, total

    def _asset_id_statements(self, criteria: MarketplaceSearchCriteria):
        statements = []
        if criteria.asset_type in (None, ASSET_TYPE_HOUSE):
            statements.append(self._house_ids(criteria))
        if criteria.asset_type in (None, ASSET_TYPE_LAND):
            statements.append(self._land_ids(criteria))
        return statements

    @staticmethod
    def _contains(value: str) -> str:
        """Escape user text before placing it in a SQL LIKE expression."""
        escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"

    @classmethod
    def _common_conditions(cls, criteria: MarketplaceSearchCriteria, model):
        conditions = [
            MarketplaceListing.status == LISTING_STATUS_ACTIVE,
            MarketplaceListing.asset_type
            == (ASSET_TYPE_HOUSE if model is House else ASSET_TYPE_LAND),
            MarketplaceListing.asset_id == model.id,
            MarketplaceListing.seller_player_id == model.owner_player_id,
        ]
        if criteria.city:
            conditions.append(model.city == criteria.city)
        if criteria.neighborhood:
            conditions.append(
                model.neighborhood.ilike(
                    cls._contains(criteria.neighborhood), escape="\\"
                )
            )
        if criteria.min_price is not None:
            conditions.append(MarketplaceListing.price >= criteria.min_price)
        if criteria.max_price is not None:
            conditions.append(MarketplaceListing.price <= criteria.max_price)
        if criteria.min_area_sqm is not None:
            conditions.append(model.area_sqm >= criteria.min_area_sqm)
        if criteria.max_area_sqm is not None:
            conditions.append(model.area_sqm <= criteria.max_area_sqm)
        if criteria.text_terms:
            fields = [model.city, model.neighborhood]
            if model is House:
                fields.extend([House.kitchen_type, House.quality])
            else:
                fields.append(Land.location_quality)
            for term in criteria.text_terms:
                conditions.append(
                    or_(
                        *(
                            field.ilike(cls._contains(term), escape="\\")
                            for field in fields
                        )
                    )
                )
        return conditions

    def _house_ids(self, criteria: MarketplaceSearchCriteria):
        if criteria.asset_type == ASSET_TYPE_LAND:
            return select(MarketplaceListing.id).where(False)
        if criteria.bedrooms is not None and criteria.bedrooms <= 0:
            return select(MarketplaceListing.id).where(False)
        conditions = self._common_conditions(criteria, House)
        if criteria.bedrooms is not None:
            conditions.append(House.bedrooms == criteria.bedrooms)
        if criteria.construction_year is not None:
            conditions.append(House.construction_year == criteria.construction_year)
        if criteria.quality:
            conditions.append(House.quality == criteria.quality)
        return (
            select(MarketplaceListing.id)
            .select_from(MarketplaceListing)
            .join(
                House,
                and_(
                    MarketplaceListing.asset_type == ASSET_TYPE_HOUSE,
                    MarketplaceListing.asset_id == House.id,
                ),
            )
            .where(*conditions)
        )

    def _land_ids(self, criteria: MarketplaceSearchCriteria):
        if criteria.asset_type == ASSET_TYPE_HOUSE:
            return select(MarketplaceListing.id).where(False)
        if criteria.bedrooms is not None or criteria.construction_year is not None:
            return select(MarketplaceListing.id).where(False)
        conditions = self._common_conditions(criteria, Land)
        # Quality is represented by Land.location_quality; house quality is a
        # different field and therefore never leaks into land results.
        if criteria.quality:
            conditions.append(Land.location_quality == criteria.quality)
        return (
            select(MarketplaceListing.id)
            .select_from(MarketplaceListing)
            .join(
                Land,
                and_(
                    MarketplaceListing.asset_type == ASSET_TYPE_LAND,
                    MarketplaceListing.asset_id == Land.id,
                ),
            )
            .where(*conditions)
        )
