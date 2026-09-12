"""Repository layer for all fictional خلاف records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.bank_hack_attempt import BankHackAttempt
from app.database.models.crime_activity import CrimeActivity
from app.database.models.fake_document import DOCUMENT_ACTIVE, DOCUMENT_EXPIRED, FakeDocument
from app.database.models.information_selling_operation import InformationSellingOperation
from app.database.models.money_laundering_operation import (
    LAUNDERING_COMPLETED,
    LAUNDERING_FAILED,
    LAUNDERING_PENDING,
    LAUNDERING_PROCESSING,
    MoneyLaunderingOperation,
)
from app.database.models.player import Player
from app.database.models.shoti_mission import (
    SHOTI_COMPLETED,
    SHOTI_FAILED,
    SHOTI_PENDING,
    SHOTI_PROCESSING,
    ShotiMission,
)


class CrimeRepository:
    """All persistence operations used by ``CrimeService``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_player_display_name(self, player_id: int) -> str | None:
        statement = select(Player.display_name).where(Player.id == player_id)
        return (await self._session.execute(statement)).scalar_one_or_none()

    # --- Generic activity history -----------------------------------------

    async def create_activity(
        self,
        *,
        activity_type: str,
        actor_player_id: int,
        target_player_id: int | None,
        status: str,
        success: bool | None,
        reward_amount: int,
        fee_amount: int,
        operation_key: str,
        details: str,
        created_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> CrimeActivity:
        activity = CrimeActivity(
            activity_type=activity_type,
            actor_player_id=actor_player_id,
            target_player_id=target_player_id,
            status=status,
            success=success,
            reward_amount=reward_amount,
            fee_amount=fee_amount,
            operation_key=operation_key,
            details=details,
            created_at=created_at,
            completed_at=completed_at,
        )
        self._session.add(activity)
        await self._session.flush()
        return activity

    async def get_activity(self, activity_id: int) -> CrimeActivity | None:
        return await self._session.get(CrimeActivity, activity_id)

    async def get_activity_by_operation_key(self, operation_key: str) -> CrimeActivity | None:
        statement = select(CrimeActivity).where(CrimeActivity.operation_key == operation_key)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_latest_activity(
        self,
        actor_player_id: int,
        activity_type: str,
        since: datetime,
    ) -> CrimeActivity | None:
        statement = (
            select(CrimeActivity)
            .where(
                CrimeActivity.actor_player_id == actor_player_id,
                CrimeActivity.activity_type == activity_type,
                CrimeActivity.created_at >= since,
                CrimeActivity.status.not_in(("cancelled",)),
            )
            .order_by(CrimeActivity.created_at.desc(), CrimeActivity.id.desc())
            .limit(1)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_activities(
        self, actor_player_id: int, *, offset: int, limit: int
    ) -> list[CrimeActivity]:
        statement = (
            select(CrimeActivity)
            .where(CrimeActivity.actor_player_id == actor_player_id)
            .order_by(CrimeActivity.created_at.desc(), CrimeActivity.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list((await self._session.execute(statement)).scalars().all())

    async def count_activities(self, actor_player_id: int) -> int:
        result = await self._session.execute(
            select(func.count(CrimeActivity.id)).where(
                CrimeActivity.actor_player_id == actor_player_id
            )
        )
        return int(result.scalar_one())

    async def update_activity(
        self,
        activity_id: int,
        *,
        status: str,
        success: bool | None,
        reward_amount: int | None = None,
        fee_amount: int | None = None,
        details: str | None = None,
        completed_at: datetime | None = None,
    ) -> bool:
        values: dict[str, object] = {"status": status, "success": success}
        if reward_amount is not None:
            values["reward_amount"] = reward_amount
        if fee_amount is not None:
            values["fee_amount"] = fee_amount
        if details is not None:
            values["details"] = details
        if completed_at is not None:
            values["completed_at"] = completed_at
        result = await self._session.execute(
            update(CrimeActivity)
            .where(CrimeActivity.id == activity_id)
            .values(**values),
            execution_options={"synchronize_session": False},
        )
        return bool(result.rowcount)

    # --- Information selling ---------------------------------------------

    async def create_information_operation(
        self,
        *,
        activity_id: int,
        actor_player_id: int,
        target_player_id: int,
        target_name: str,
        information_text: str,
        success: bool,
        reward_amount: int,
        created_at: datetime | None = None,
    ) -> InformationSellingOperation:
        operation = InformationSellingOperation(
            activity_id=activity_id,
            actor_player_id=actor_player_id,
            target_player_id=target_player_id,
            target_name=target_name,
            information_text=information_text,
            success=success,
            reward_amount=reward_amount,
            created_at=created_at,
        )
        self._session.add(operation)
        await self._session.flush()
        return operation

    async def get_information_operation(self, activity_id: int) -> InformationSellingOperation | None:
        statement = select(InformationSellingOperation).where(
            InformationSellingOperation.activity_id == activity_id
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    # --- Money laundering -------------------------------------------------

    async def create_laundering_operation(
        self,
        *,
        activity_id: int,
        player_id: int,
        amount: int,
        fee_amount: int,
        final_amount: int,
        process_at: datetime,
    ) -> MoneyLaunderingOperation:
        operation = MoneyLaunderingOperation(
            activity_id=activity_id,
            player_id=player_id,
            amount=amount,
            fee_amount=fee_amount,
            final_amount=final_amount,
            process_at=process_at,
            status=LAUNDERING_PENDING,
        )
        self._session.add(operation)
        await self._session.flush()
        return operation

    async def get_laundering_operation(self, operation_id: int) -> MoneyLaunderingOperation | None:
        return await self._session.get(MoneyLaunderingOperation, operation_id)

    async def get_laundering_by_activity(self, activity_id: int) -> MoneyLaunderingOperation | None:
        statement = select(MoneyLaunderingOperation).where(
            MoneyLaunderingOperation.activity_id == activity_id
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_due_laundering(self, now: datetime) -> list[MoneyLaunderingOperation]:
        statement = (
            select(MoneyLaunderingOperation)
            .where(
                MoneyLaunderingOperation.status == LAUNDERING_PENDING,
                MoneyLaunderingOperation.process_at <= now,
            )
            .order_by(MoneyLaunderingOperation.process_at, MoneyLaunderingOperation.id)
        )
        return list((await self._session.execute(statement)).scalars().all())

    async def claim_laundering(self, operation_id: int) -> bool:
        result = await self._session.execute(
            update(MoneyLaunderingOperation)
            .where(
                MoneyLaunderingOperation.id == operation_id,
                MoneyLaunderingOperation.status == LAUNDERING_PENDING,
            )
            .values(status=LAUNDERING_PROCESSING),
            execution_options={"synchronize_session": False},
        )
        return bool(result.rowcount)

    async def complete_laundering(
        self, operation_id: int, completed_at: datetime
    ) -> bool:
        result = await self._session.execute(
            update(MoneyLaunderingOperation)
            .where(
                MoneyLaunderingOperation.id == operation_id,
                MoneyLaunderingOperation.status == LAUNDERING_PROCESSING,
                MoneyLaunderingOperation.reward_paid.is_(False),
            )
            .values(
                status=LAUNDERING_COMPLETED,
                reward_paid=True,
                completed_at=completed_at,
            ),
            execution_options={"synchronize_session": False},
        )
        return bool(result.rowcount)

    async def fail_laundering(self, operation_id: int, completed_at: datetime) -> bool:
        result = await self._session.execute(
            update(MoneyLaunderingOperation)
            .where(
                MoneyLaunderingOperation.id == operation_id,
                MoneyLaunderingOperation.status == LAUNDERING_PROCESSING,
            )
            .values(status=LAUNDERING_FAILED, completed_at=completed_at),
            execution_options={"synchronize_session": False},
        )
        return bool(result.rowcount)

    async def list_laundering_for_player(self, player_id: int) -> list[MoneyLaunderingOperation]:
        statement = (
            select(MoneyLaunderingOperation)
            .where(MoneyLaunderingOperation.player_id == player_id)
            .order_by(MoneyLaunderingOperation.created_at.desc(), MoneyLaunderingOperation.id.desc())
        )
        return list((await self._session.execute(statement)).scalars().all())

    # --- Fake documents ---------------------------------------------------

    async def expire_documents(self, now: datetime) -> int:
        result = await self._session.execute(
            update(FakeDocument)
            .where(
                FakeDocument.status == DOCUMENT_ACTIVE,
                FakeDocument.expires_at.is_not(None),
                FakeDocument.expires_at <= now,
            )
            .values(status=DOCUMENT_EXPIRED),
            execution_options={"synchronize_session": False},
        )
        return int(result.rowcount or 0)

    async def get_active_document(self, owner_player_id: int, document_type: str) -> FakeDocument | None:
        statement = select(FakeDocument).where(
            FakeDocument.owner_player_id == owner_player_id,
            FakeDocument.document_type == document_type,
            FakeDocument.status == DOCUMENT_ACTIVE,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_document_by_activity_key(self, operation_key: str) -> FakeDocument | None:
        statement = (
            select(FakeDocument)
            .join(CrimeActivity, CrimeActivity.id == FakeDocument.activity_id)
            .where(CrimeActivity.operation_key == operation_key)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def create_document(
        self,
        *,
        activity_id: int,
        owner_player_id: int,
        document_type: str,
        created_at: datetime,
        expires_at: datetime | None,
    ) -> FakeDocument:
        document = FakeDocument(
            activity_id=activity_id,
            owner_player_id=owner_player_id,
            document_type=document_type,
            created_at=created_at,
            expires_at=expires_at,
        )
        self._session.add(document)
        await self._session.flush()
        return document

    async def list_documents(self, owner_player_id: int) -> list[FakeDocument]:
        statement = (
            select(FakeDocument)
            .where(FakeDocument.owner_player_id == owner_player_id)
            .order_by(FakeDocument.created_at.desc(), FakeDocument.id.desc())
        )
        return list((await self._session.execute(statement)).scalars().all())

    # --- Shoti missions ---------------------------------------------------

    async def get_active_shoti_mission(self, player_id: int) -> ShotiMission | None:
        statement = select(ShotiMission).where(
            ShotiMission.player_id == player_id,
            ShotiMission.status.in_((SHOTI_PENDING, SHOTI_PROCESSING)),
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def create_shoti_mission(self, **values) -> ShotiMission:
        mission = ShotiMission(**values)
        self._session.add(mission)
        await self._session.flush()
        return mission

    async def get_shoti_by_activity(self, activity_id: int) -> ShotiMission | None:
        statement = select(ShotiMission).where(ShotiMission.activity_id == activity_id)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_due_shoti(self, now: datetime) -> list[ShotiMission]:
        statement = (
            select(ShotiMission)
            .where(ShotiMission.status == SHOTI_PENDING, ShotiMission.completes_at <= now)
            .order_by(ShotiMission.completes_at, ShotiMission.id)
        )
        return list((await self._session.execute(statement)).scalars().all())

    async def claim_shoti(self, mission_id: int) -> bool:
        result = await self._session.execute(
            update(ShotiMission)
            .where(
                ShotiMission.id == mission_id,
                ShotiMission.status == SHOTI_PENDING,
            )
            .values(status=SHOTI_PROCESSING),
            execution_options={"synchronize_session": False},
        )
        return bool(result.rowcount)

    async def complete_shoti(
        self, mission_id: int, *, success: bool, reward_paid: bool, completed_at: datetime
    ) -> bool:
        result = await self._session.execute(
            update(ShotiMission)
            .where(
                ShotiMission.id == mission_id,
                ShotiMission.status == SHOTI_PROCESSING,
            )
            .values(
                status=SHOTI_COMPLETED if success else SHOTI_FAILED,
                success=success,
                reward_paid=reward_paid,
                completed_at=completed_at,
            ),
            execution_options={"synchronize_session": False},
        )
        return bool(result.rowcount)

    async def list_shoti_for_player(self, player_id: int) -> list[ShotiMission]:
        statement = (
            select(ShotiMission)
            .where(ShotiMission.player_id == player_id)
            .order_by(ShotiMission.started_at.desc(), ShotiMission.id.desc())
        )
        return list((await self._session.execute(statement)).scalars().all())

    # --- Bank hacking -----------------------------------------------------

    async def create_bank_hack(self, **values) -> BankHackAttempt:
        attempt = BankHackAttempt(**values)
        self._session.add(attempt)
        await self._session.flush()
        return attempt

    async def get_bank_hack(self, activity_id: int) -> BankHackAttempt | None:
        statement = select(BankHackAttempt).where(BankHackAttempt.activity_id == activity_id)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def complete_bank_hack(
        self,
        attempt_id: int,
        *,
        success: bool,
        transferred_amount: int,
        reason: str,
        completed_at: datetime,
    ) -> bool:
        result = await self._session.execute(
            update(BankHackAttempt)
            .where(BankHackAttempt.id == attempt_id, BankHackAttempt.status == "pending")
            .values(
                status="completed" if success else "failed",
                success=success,
                transferred_amount=transferred_amount,
                reason=reason,
                completed_at=completed_at,
            ),
            execution_options={"synchronize_session": False},
        )
        return bool(result.rowcount)
