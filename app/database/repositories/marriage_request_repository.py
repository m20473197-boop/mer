"""Database access for pending marriage requests (``marriage_requests``).

Accept/reject/cancel/expire all go through a single-row atomic claim
(``WHERE status = 'pending'``), so a player tapping accept twice — or a
timeout settler racing an accept — can never produce two outcomes.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.marriage_request import (
    STATUS_ACCEPTED,
    STATUS_CANCELLED,
    STATUS_EXPIRED,
    STATUS_PENDING,
    STATUS_REJECTED,
    MarriageRequest,
)


class MarriageRequestRepository:
    """All database operations for the ``marriage_requests`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reads ---------------------------------------------------------------

    async def get_by_id(self, request_id: int) -> MarriageRequest | None:
        return await self._session.get(MarriageRequest, request_id)

    async def get_pending_for_target(self, target_player_id: int) -> MarriageRequest | None:
        statement = (
            select(MarriageRequest)
            .where(
                MarriageRequest.target_player_id == target_player_id,
                MarriageRequest.status == STATUS_PENDING,
            )
            .order_by(MarriageRequest.id.desc())
            .limit(1)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_pending_from_proposer(
        self, proposer_player_id: int
    ) -> MarriageRequest | None:
        statement = (
            select(MarriageRequest)
            .where(
                MarriageRequest.proposer_player_id == proposer_player_id,
                MarriageRequest.status == STATUS_PENDING,
            )
            .order_by(MarriageRequest.id.desc())
            .limit(1)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def has_pending_involving(self, player_id: int) -> bool:
        statement = (
            select(MarriageRequest.id)
            .where(
                or_(
                    MarriageRequest.proposer_player_id == player_id,
                    MarriageRequest.target_player_id == player_id,
                ),
                MarriageRequest.status == STATUS_PENDING,
            )
            .limit(1)
        )
        return (await self._session.execute(statement)).scalar() is not None

    async def list_expired(self, now: datetime) -> list[MarriageRequest]:
        statement = select(MarriageRequest).where(
            MarriageRequest.status == STATUS_PENDING,
            MarriageRequest.expires_at <= now,
        )
        return list((await self._session.execute(statement)).scalars().all())

    # --- Writes --------------------------------------------------------------

    def add(self, request: MarriageRequest) -> None:
        self._session.add(request)

    async def _claim(self, request_id: int, to_status: str, when: datetime) -> bool:
        statement = (
            update(MarriageRequest)
            .where(
                MarriageRequest.id == request_id,
                MarriageRequest.status == STATUS_PENDING,
            )
            .values(status=to_status, answered_at=when)
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)

    async def claim_accepted(self, request_id: int, when: datetime) -> bool:
        return await self._claim(request_id, STATUS_ACCEPTED, when)

    async def claim_rejected(self, request_id: int, when: datetime) -> bool:
        return await self._claim(request_id, STATUS_REJECTED, when)

    async def claim_cancelled(self, request_id: int, when: datetime) -> bool:
        return await self._claim(request_id, STATUS_CANCELLED, when)

    async def claim_expired(self, request_id: int, when: datetime) -> bool:
        return await self._claim(request_id, STATUS_EXPIRED, when)

    async def set_marriage(self, request_id: int, marriage_id: int) -> None:
        statement = (
            update(MarriageRequest)
            .where(MarriageRequest.id == request_id)
            .values(marriage_id=marriage_id)
        )
        await self._session.execute(statement, execution_options={"synchronize_session": False})


__all__ = ["MarriageRequestRepository"]
