"""Repository for owned businesses."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.business import Business


class BusinessRepository:
    """All database access for the ``businesses`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reads -----------------------------------------------------------

    async def get_by_id(self, business_id: int) -> Business | None:
        return await self._session.get(Business, business_id)

    async def get_by_owner_and_type(
        self, owner_player_id: int, business_type: str
    ) -> Business | None:
        statement = select(Business).where(
            Business.owner_player_id == owner_player_id,
            Business.business_type == business_type,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_by_owner(self, owner_player_id: int) -> list[Business]:
        statement = (
            select(Business)
            .where(Business.owner_player_id == owner_player_id)
            .order_by(Business.id)
        )
        return list((await self._session.execute(statement)).scalars().all())

    async def count_by_owner(self, owner_player_id: int) -> int:
        statement = select(func.count(Business.id)).where(
            Business.owner_player_id == owner_player_id
        )
        return int((await self._session.execute(statement)).scalar_one())

    # --- Writes ----------------------------------------------------------

    async def create(
        self,
        *,
        owner_player_id: int,
        business_type: str,
        name: str,
        startup_cost: int,
        min_daily_income: int,
        max_daily_income: int,
        started_at: datetime,
    ) -> Business:
        business = Business(
            owner_player_id=owner_player_id,
            business_type=business_type,
            name=name,
            startup_cost=startup_cost,
            min_daily_income=min_daily_income,
            max_daily_income=max_daily_income,
            started_at=started_at,
        )
        self._session.add(business)
        await self._session.flush()
        return business

    async def add_daily_income(
        self,
        *,
        business_id: int,
        owner_player_id: int,
        income_date: date,
        amount: int,
    ) -> bool:
        """Atomically credit one day's income at most once.

        The date guard is part of the SQL UPDATE, so two concurrent Telegram
        taps cannot both credit the same business for the same day.
        """
        statement = (
            update(Business)
            .where(
                Business.id == business_id,
                Business.owner_player_id == owner_player_id,
                Business.is_active.is_(True),
                or_(
                    Business.last_income_date.is_(None),
                    Business.last_income_date < income_date,
                ),
            )
            .values(
                balance=Business.balance + amount,
                latest_daily_income=amount,
                last_income_date=income_date,
            )
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)
