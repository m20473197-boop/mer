"""Job and Income System — dedicated service (time-based salary).

Handles:
- Listing available jobs (hourly salary + employer)
- Checking requirements (level, skill)
- Applying for a job (one active job per player) — saves the work start time
- Settling accounts with the employer (💰 تسویه با صاحبکار):
    * calculates worked time and earned salary,
    * rolls a random employer-behaviour event (normal / bonus / mistake /
      delayed payment),
    * pays through the wallet system and resets the work timer.
- Salary-event history (payments, bonuses, penalties, delayed payments)
- Leaving a job

Expandable for future: education, skills, businesses, etc.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import constants
from app.database.models.job import Job
from app.database.models.job_event import (
    EVENT_BONUS,
    EVENT_DELAYED,
    EVENT_MISTAKE,
    EVENT_NORMAL,
    STATUS_DELAYED,
    STATUS_PAID,
)
from app.database.repositories.job_event_repository import JobEventRepository
from app.database.repositories.job_history_repository import JobHistoryRepository
from app.database.repositories.job_repository import JobRepository
from app.database.repositories.player_job_repository import PlayerJobRepository
from app.database.repositories.player_repository import PlayerRepository
from app.game.admin import runtime as admin_runtime
from app.game.player.dto import (
    JobApplyResult,
    JobData,
    JobEventData,
    JobHistoryData,
    JobLeaveResult,
    PlayerJobData,
    SettlementResult,
)
from app.game.shared.errors import DomainError, PlayerNotFoundError

logger = logging.getLogger(__name__)


class JobNotFoundError(DomainError):
    pass


class JobRequirementError(DomainError):
    pass


class AlreadyHasJobError(DomainError):
    pass


class NoJobError(DomainError):
    pass


class JobNotEnoughTimeError(DomainError):
    """Settlement requested before even a whole minute of work accrued."""

    def __init__(self, message: str = "Not enough work time for settlement"):
        super().__init__(message)


class JobService:
    """Complete Job and Income service (time-based salary)."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        money_service=None,
        rng: random.Random | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._money_service = money_service
        # The employer-behaviour dice. Inject a seeded Random in tests to make
        # event rolls deterministic.
        self._rng = rng if rng is not None else random.Random()

    # --- Helpers to convert ORM -> DTO -----------------------------------

    @staticmethod
    def _to_job_dto(job: Job) -> JobData:
        return JobData(
            id=job.id,
            name=job.name,
            description=job.description,
            salary=job.salary,
            hourly_salary=job.hourly_salary,
            employer=job.employer,
            cooldown=job.cooldown,
            required_level=job.required_level,
            required_skill=job.required_skill,
            is_active=job.is_active,
            created_at=job.created_at,
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _elapsed_minutes(started_at: datetime) -> int:
        """Whole minutes worked since ``started_at`` (never negative)."""
        now = datetime.now(timezone.utc)
        start = JobService._as_utc(started_at)
        return max(0, int((now - start).total_seconds() // 60))

    @staticmethod
    def _gross_salary(hourly_salary: int, minutes: int) -> int:
        """Exact integer salary for ``minutes`` at an hourly rate."""
        return hourly_salary * minutes // 60

    def _roll_employer_event(self) -> tuple[str, int]:
        """Randomly pick the employer behaviour during settlement.

        Returns a ``(event_type, percent)`` pair. ``percent`` is the bonus or
        penalty percentage for ``bonus`` / ``mistake`` events and ``0``
        otherwise.
        """
        roll = self._rng.random()
        delay_p = constants.EMPLOYER_EVENT_DELAY_PROBABILITY
        mistake_p = constants.EMPLOYER_EVENT_MISTAKE_PROBABILITY
        bonus_p = constants.EMPLOYER_EVENT_BONUS_PROBABILITY

        if roll < delay_p:
            return EVENT_DELAYED, 0
        if roll < delay_p + mistake_p:
            return EVENT_MISTAKE, self._rng.randint(
                constants.MISTAKE_PENALTY_MIN_PERCENT,
                constants.MISTAKE_PENALTY_MAX_PERCENT,
            )
        if roll < delay_p + mistake_p + bonus_p:
            return EVENT_BONUS, self._rng.randint(
                constants.BONUS_MIN_PERCENT, constants.BONUS_MAX_PERCENT
            )
        return EVENT_NORMAL, 0

    # --- Public API ------------------------------------------------------

    async def ensure_initial_jobs(self) -> List[JobData]:
        """Seed initial jobs if missing, return active jobs."""
        async with self._session_factory() as session:
            repo = JobRepository(session)
            jobs = await repo.ensure_initial_jobs()
            await session.commit()
            return [self._to_job_dto(j) for j in jobs]

    async def get_available_jobs(self) -> List[JobData]:
        async with self._session_factory() as session:
            repo = JobRepository(session)
            jobs = await repo.list_active()
            return [self._to_job_dto(j) for j in jobs]

    async def get_all_jobs(self) -> List[JobData]:
        async with self._session_factory() as session:
            repo = JobRepository(session)
            jobs = await repo.list_all()
            return [self._to_job_dto(j) for j in jobs]

    async def get_player_job(self, player_id: int) -> PlayerJobData | None:
        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            if not await player_repo.exists(player_id):
                raise PlayerNotFoundError(f"player_id={player_id} not found")

            pj_repo = PlayerJobRepository(session)
            pj = await pj_repo.get_by_player_id(player_id)
            if pj is None:
                return None

            job_repo = JobRepository(session)
            job = await job_repo.get_by_id(pj.job_id)
            if job is None:
                # Job deleted? Clean up orphan
                await pj_repo.delete_by_player_id(player_id)
                await session.commit()
                return None

            worked_minutes = self._elapsed_minutes(pj.started_at)
            accrued_salary = self._gross_salary(job.hourly_salary, worked_minutes)

            return PlayerJobData(
                id=pj.id,
                player_id=pj.player_id,
                job_id=pj.job_id,
                job_name=job.name,
                job_description=job.description,
                salary=job.salary,
                hourly_salary=job.hourly_salary,
                employer=job.employer,
                cooldown=job.cooldown,
                started_at=pj.started_at,
                last_work_time=pj.last_work_time,
                total_earnings=pj.total_earnings,
                created_at=pj.created_at,
                updated_at=pj.updated_at,
                worked_minutes=worked_minutes,
                accrued_salary=accrued_salary,
            )

    async def apply_job(self, player_id: int, job_id: int) -> JobApplyResult:
        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            player = await player_repo.get_by_id(player_id)
            if player is None:
                raise PlayerNotFoundError(f"player_id={player_id} not found")

            job_repo = JobRepository(session)
            job = await job_repo.get_by_id(job_id)
            if job is None:
                raise JobNotFoundError(f"job_id={job_id} not found")
            if not job.is_active:
                raise JobNotFoundError(f"job {job.name} is not active")

            # Check requirements
            if player.level < job.required_level:
                raise JobRequirementError(
                    f"Requires level {job.required_level}, you are {player.level}"
                )
            if job.required_skill is not None:
                raise JobRequirementError(
                    f"Requires skill {job.required_skill} (not yet implemented)"
                )

            pj_repo = PlayerJobRepository(session)
            existing = await pj_repo.get_by_player_id(player_id)
            if existing is not None:
                raise AlreadyHasJobError("Player already has a job")

            # Save the work start time — the time-based salary clock starts now.
            started_at = datetime.now(timezone.utc)
            await pj_repo.create(
                player_id=player_id, job_id=job_id, started_at=started_at
            )
            await session.commit()

            logger.info("Player %s applied for job %s (%s)", player_id, job_id, job.name)

            return JobApplyResult(
                player_id=player_id,
                job_id=job.id,
                job_name=job.name,
                employer=job.employer,
                hourly_salary=job.hourly_salary,
                success=True,
                message="Job selected successfully.",
            )

    async def settle_with_employer(self, player_id: int) -> SettlementResult:
        """Settle accounts with the employer (💰 تسویه با صاحبکار).

        Calculates worked time and earned salary, rolls a random employer
        event, pays through the wallet and resets the work timer. On a
        ``delayed`` event the money is withheld and the timer keeps running so
        the player can settle again later.
        """
        now = datetime.now(timezone.utc)

        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            player = await player_repo.get_by_id(player_id)
            if player is None:
                raise PlayerNotFoundError(f"player_id={player_id} not found")

            pj_repo = PlayerJobRepository(session)
            pj = await pj_repo.get_by_player_id(player_id)
            if pj is None:
                raise NoJobError("You don't have a job yet.")

            job_repo = JobRepository(session)
            job = await job_repo.get_by_id(pj.job_id)
            if job is None:
                raise JobNotFoundError("Job not found (deleted)")

            minutes = self._elapsed_minutes(pj.started_at)
            if minutes < admin_runtime.min_work_minutes():
                raise JobNotEnoughTimeError(
                    "Not enough work time for settlement yet"
                )

            gross = self._gross_salary(job.hourly_salary, minutes)
            event_type, percent = self._roll_employer_event()

            bonus_percent: int | None = None
            bonus_amount = 0
            penalty_percent: int | None = None
            penalty_amount = 0
            final_amount = gross
            status = STATUS_PAID
            paid = True

            if event_type == EVENT_BONUS:
                bonus_percent = percent
                bonus_amount = gross * percent // 100
                final_amount = gross + bonus_amount
            elif event_type == EVENT_MISTAKE:
                penalty_percent = percent
                penalty_amount = gross * percent // 100
                final_amount = max(0, gross - penalty_amount)
            elif event_type == EVENT_DELAYED:
                status = STATUS_DELAYED
                paid = False
                final_amount = 0

            # Save the event (payments, bonuses, penalties and delays).
            event_repo = JobEventRepository(session)
            event_repo.add(
                player_id=player_id,
                job_id=job.id,
                employer=job.employer,
                event_type=event_type,
                status=status,
                worked_minutes=minutes,
                hourly_salary=job.hourly_salary,
                gross_salary=gross,
                bonus_percent=bonus_percent,
                bonus_amount=bonus_amount,
                penalty_percent=penalty_percent,
                penalty_amount=penalty_amount,
                final_amount=final_amount,
            )

            if paid:
                # Pay through the wallet (same atomic credit the Wallet system
                # uses), then reset the work timer and accrue total earnings.
                await player_repo.add_money(player_id, final_amount)
                await pj_repo.settle(player_id, now, earnings_to_add=final_amount)
            # On delay: no payment, no timer reset — work keeps accruing.

            await session.commit()

            logger.info(
                "Player %s settled job %s: %s %s minutes -> %s (paid=%s)",
                player_id,
                job.id,
                event_type,
                minutes,
                final_amount,
                paid,
            )

        # Re-read post-settlement state in a fresh session.
        async with self._session_factory() as read_session:
            read_player_repo = PlayerRepository(read_session)
            balance_after = await read_player_repo.get_money(player_id)
            read_pj_repo = PlayerJobRepository(read_session)
            read_pj = await read_pj_repo.get_by_player_id(player_id)
            total_earnings = read_pj.total_earnings if read_pj else 0
        if balance_after is None:  # pragma: no cover — guarded above
            raise PlayerNotFoundError(f"player_id={player_id} not found")

        return SettlementResult(
            player_id=player_id,
            job_id=job.id,
            job_name=job.name,
            employer=job.employer,
            event_type=event_type,
            status=status,
            worked_minutes=minutes,
            hourly_salary=job.hourly_salary,
            gross_salary=gross,
            bonus_percent=bonus_percent,
            bonus_amount=bonus_amount,
            penalty_percent=penalty_percent,
            penalty_amount=penalty_amount,
            final_amount=final_amount,
            paid=paid,
            balance_after=balance_after,
            total_earnings=total_earnings,
            message=(
                "Settlement completed."
                if paid
                else "Employer delayed the payment — settle again later."
            ),
        )

    async def leave_job(self, player_id: int) -> JobLeaveResult:
        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            if not await player_repo.exists(player_id):
                raise PlayerNotFoundError(f"player_id={player_id} not found")

            pj_repo = PlayerJobRepository(session)
            pj = await pj_repo.get_by_player_id(player_id)
            if pj is None:
                raise NoJobError("You don't have a job yet.")

            job_repo = JobRepository(session)
            job = await job_repo.get_by_id(pj.job_id)
            job_name = job.name if job else "Unknown"
            total = pj.total_earnings

            await pj_repo.delete_by_player_id(player_id)
            await session.commit()

            logger.info("Player %s left job %s", player_id, pj.job_id)

            return JobLeaveResult(
                player_id=player_id,
                job_id=pj.job_id,
                job_name=job_name,
                success=True,
                total_earnings=total,
                message="Left job successfully.",
            )

    async def get_salary_events(
        self, player_id: int, limit: int = 20, offset: int = 0
    ) -> List[JobEventData]:
        """Saved settlement events for a player (payments, bonuses, ...)."""
        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            if not await player_repo.exists(player_id):
                raise PlayerNotFoundError(f"player_id={player_id} not found")

            repo = JobEventRepository(session)
            events = await repo.list_by_player(player_id, limit, offset)
            return [
                JobEventData(
                    id=e.id,
                    player_id=e.player_id,
                    job_id=e.job_id,
                    employer=e.employer,
                    event_type=e.event_type,
                    status=e.status,
                    worked_minutes=e.worked_minutes,
                    hourly_salary=e.hourly_salary,
                    gross_salary=e.gross_salary,
                    bonus_percent=e.bonus_percent,
                    bonus_amount=e.bonus_amount,
                    penalty_percent=e.penalty_percent,
                    penalty_amount=e.penalty_amount,
                    final_amount=e.final_amount,
                    created_at=e.created_at,
                )
                for e in events
            ]

    async def get_job_history(
        self, player_id: int, limit: int = 20, offset: int = 0
    ) -> List[JobHistoryData]:
        """Legacy per-action income history (kept for backward compatibility)."""
        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            if not await player_repo.exists(player_id):
                raise PlayerNotFoundError(f"player_id={player_id} not found")

            hist_repo = JobHistoryRepository(session)
            job_repo = JobRepository(session)

            histories = await hist_repo.list_by_player(player_id, limit, offset)
            result: List[JobHistoryData] = []
            for h in histories:
                job = await job_repo.get_by_id(h.job_id)
                job_name = job.name if job else f"Job#{h.job_id}"
                result.append(
                    JobHistoryData(
                        id=h.id,
                        player_id=h.player_id,
                        job_id=h.job_id,
                        job_name=job_name,
                        income=h.income,
                        created_at=h.created_at,
                    )
                )
            return result
