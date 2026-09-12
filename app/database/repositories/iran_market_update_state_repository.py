"""Repository for the singleton Iranian-market scheduler state."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, insert, or_, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.iran_market_update_state import IranMarketUpdateState


class IranMarketUpdateStateRepository:
    """Persistent three-day cursor and atomic update lease."""

    STATE_ID = 1

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> IranMarketUpdateState | None:
        return await self._session.get(IranMarketUpdateState, self.STATE_ID)

    async def ensure(self) -> IranMarketUpdateState:
        """Insert the singleton row idempotently, including concurrent boots."""
        statement = _insert_if_absent(
            self._session,
            IranMarketUpdateState,
            {"id": self.STATE_ID},
            conflict_column="id",
        )
        await self._session.execute(statement)
        state = await self.get()
        if state is None:  # pragma: no cover - defensive guard for bad dialects
            raise RuntimeError("Iran market scheduler state could not be initialized")
        return state

    async def try_claim(
        self,
        *,
        now: datetime,
        token: str,
        due_before: datetime,
        initial_retry_before: datetime,
        failure_retry_before: datetime,
        lease_expired_before: datetime,
        force: bool = False,
    ) -> bool:
        """Claim a due cycle with one conditional SQL update."""
        initial_due = and_(
            IranMarketUpdateState.last_successful_update.is_(None),
            or_(
                IranMarketUpdateState.last_attempted_update.is_(None),
                IranMarketUpdateState.last_attempted_update <= initial_retry_before,
            ),
        )
        regular_due = and_(
            IranMarketUpdateState.last_successful_update <= due_before,
            or_(
                IranMarketUpdateState.last_attempted_update.is_(None),
                IranMarketUpdateState.last_attempted_update <= failure_retry_before,
            ),
        )
        due_condition = or_(initial_due, regular_due) if not force else True
        statement = (
            update(IranMarketUpdateState)
            .where(
                IranMarketUpdateState.id == self.STATE_ID,
                due_condition,
                or_(
                    IranMarketUpdateState.lock_acquired_at.is_(None),
                    IranMarketUpdateState.lock_acquired_at <= lease_expired_before,
                ),
            )
            .values(
                lock_token=token,
                lock_acquired_at=now,
                last_attempted_update=now,
                last_error=None,
            )
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)

    async def release(self, *, token: str, error: str) -> bool:
        statement = (
            update(IranMarketUpdateState)
            .where(
                IranMarketUpdateState.id == self.STATE_ID,
                IranMarketUpdateState.lock_token == token,
            )
            .values(lock_token=None, lock_acquired_at=None, last_error=error[:256])
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)

    async def finalize(
        self, *, token: str, successful_at: datetime
    ) -> bool:
        statement = (
            update(IranMarketUpdateState)
            .where(
                IranMarketUpdateState.id == self.STATE_ID,
                IranMarketUpdateState.lock_token == token,
            )
            .values(
                last_successful_update=successful_at,
                lock_token=None,
                lock_acquired_at=None,
                last_error=None,
            )
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)

    async def clear_stale_lock(self, *, now: datetime, lease_expired_before: datetime) -> int:
        statement = (
            update(IranMarketUpdateState)
            .where(
                IranMarketUpdateState.id == self.STATE_ID,
                IranMarketUpdateState.lock_acquired_at <= lease_expired_before,
            )
            .values(lock_token=None, lock_acquired_at=None)
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return int(result.rowcount or 0)


def _insert_if_absent(session: AsyncSession, model, values: dict, *, conflict_column: str):
    """Build a small cross-dialect insert that does not race on boot."""
    dialect_name = session.get_bind().dialect.name
    if dialect_name == "sqlite":
        return sqlite_insert(model).values(**values).prefix_with("OR IGNORE")
    if dialect_name == "postgresql":
        return postgres_insert(model).values(**values).on_conflict_do_nothing(
            index_elements=[conflict_column]
        )
    # SQLite and PostgreSQL are the supported deployment paths. For another
    # dialect, use the standard insert and let its normal constraint error make
    # the unsupported path visible instead of silently dropping data.
    return insert(model).values(**values)
