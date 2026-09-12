"""Business service for the fictional 🕳️ خلاف system.

Nothing in this module represents real-world wrongdoing. Every activity is a
contained game mechanic using only the L.I.R player, wallet, bank, and vehicle
systems. The service owns transaction boundaries; Telegram handlers never
read or mutate crime records directly.
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from secrets import token_hex

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models.bank_hack_attempt import BANK_HACK_PENDING
from app.database.models.crime_activity import (
    CRIME_STATUS_COMPLETED,
    CRIME_STATUS_FAILED,
    CRIME_STATUS_PENDING,
    CRIME_STATUS_PROCESSING,
)
from app.database.models.money_laundering_operation import (
    LAUNDERING_COMPLETED,
    LAUNDERING_PROCESSING,
)
from app.database.models.shoti_mission import SHOTI_PENDING, SHOTI_PROCESSING
from app.database.repositories.crime_repository import CrimeRepository
from app.database.repositories.player_repository import PlayerRepository
from app.game.crime.catalog import (
    CRIME_ACTIVITY_BANK_HACK,
    CRIME_ACTIVITY_FAKE_DOCUMENT,
    CRIME_ACTIVITY_INFORMATION_SELLING,
    CRIME_ACTIVITY_MONEY_LAUNDERING,
    CRIME_ACTIVITY_SHOTI,
    DEFAULT_CRIME_CONFIG,
    CrimeConfig,
    get_fake_document_definition,
)
from app.game.crime.dto import (
    BankHackResult,
    CrimeActivityData,
    FakeDocumentData,
    InformationSellingResult,
    MoneyLaunderingData,
    ShotiMissionData,
)
from app.game.crime.errors import (
    CrimeActiveMissionError,
    CrimeCooldownError,
    CrimeDuplicateDocumentError,
    CrimeError,
    CrimeInsufficientFundsError,
    CrimeInvalidAmountError,
    CrimeInvalidDocumentTypeError,
    CrimeInvalidTargetError,
    CrimeNoEligibleVehicleError,
    CrimeOperationConflictError,
    CrimeTargetBankAccountError,
    CrimeVehicleNotOwnedError,
)
from app.game.shared.errors import InsufficientFundsError, PlayerNotFoundError
from app.services.bank_service import (
    BankError,
    BankInsufficientBalanceError,
    BankService,
)
from app.services.money_service import MoneyService
from app.services.vehicle_service import VehicleNotOwnedError, VehicleService

logger = logging.getLogger(__name__)

_CRIME_LOCKS: dict[int, asyncio.Lock] = {}


def _shared_crime_lock(session_factory: async_sessionmaker[AsyncSession]) -> asyncio.Lock:
    key = id(session_factory)
    lock = _CRIME_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _CRIME_LOCKS[key] = lock
    return lock


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _clamp_percent(value: int) -> int:
    return max(0, min(100, int(value)))


class CrimeService:
    """Use cases, persistence coordination, and settlement for خلاف."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        money_service: MoneyService | None = None,
        bank_service: BankService | None = None,
        vehicle_service: VehicleService | None = None,
        config: CrimeConfig | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._money = money_service or MoneyService(session_factory)
        self._bank = bank_service or BankService(session_factory, money_service=self._money)
        self._vehicles = vehicle_service
        self._config = config or DEFAULT_CRIME_CONFIG
        self._rng = rng or random.Random()
        self._lock = _shared_crime_lock(session_factory)
        self._scheduler_task: asyncio.Task[None] | None = None
        self._scheduler_stop: asyncio.Event | None = None

    @property
    def config(self) -> CrimeConfig:
        return self._config

    # ------------------------------------------------------------------
    # Information-selling
    # ------------------------------------------------------------------

    async def sell_information(
        self,
        actor_player_id: int,
        target_player_id: int,
        *,
        operation_key: str | None = None,
        now: datetime | None = None,
    ) -> InformationSellingResult:
        current = _as_utc(now) or _utc_now()
        key = self._operation_key(operation_key)
        async with self._lock:
            async with self._session_factory() as session:
                repository = CrimeRepository(session)
                existing = await repository.get_activity_by_operation_key(key)
                if existing is not None:
                    if (
                        existing.activity_type != CRIME_ACTIVITY_INFORMATION_SELLING
                        or existing.actor_player_id != actor_player_id
                        or existing.target_player_id != target_player_id
                    ):
                        raise CrimeOperationConflictError("operation key belongs to another activity")
                    return await self._existing_information(repository, existing)
                actor, target = await self._require_target(session, actor_player_id, target_player_id)
                self._check_cooldown(
                    await repository.get_latest_activity(
                        actor_player_id,
                        CRIME_ACTIVITY_INFORMATION_SELLING,
                        current - timedelta(seconds=max(0, self._config.information_cooldown_seconds)),
                    ),
                    current,
                    self._config.information_cooldown_seconds,
                )
                success = self._roll_percent(self._config.information_success_percent)
                information = self._generate_information(target, success)
                reward = self._positive_config_amount(self._config.information_reward)
                reward = reward if success else 0
                activity = await repository.create_activity(
                    activity_type=CRIME_ACTIVITY_INFORMATION_SELLING,
                    actor_player_id=actor.id,
                    target_player_id=target.id,
                    status=CRIME_STATUS_COMPLETED,
                    success=success,
                    reward_amount=reward,
                    fee_amount=0,
                    operation_key=key,
                    details=information,
                    created_at=current,
                    completed_at=current,
                )
                operation = await repository.create_information_operation(
                    activity_id=activity.id,
                    actor_player_id=actor.id,
                    target_player_id=target.id,
                    target_name=target.display_name,
                    information_text=information,
                    success=success,
                    reward_amount=reward,
                    created_at=current,
                )
                if success:
                    try:
                        await self._money.add_money_in_transaction(session, actor.id, reward)
                    except InsufficientFundsError as exc:  # defensive: credit cannot normally fail
                        raise CrimeError("information reward could not be credited") from exc
                await session.commit()
                return self._information_result(activity, operation)

    # ------------------------------------------------------------------
    # Money laundering
    # ------------------------------------------------------------------

    async def start_laundering(
        self,
        player_id: int,
        amount: int,
        *,
        operation_key: str | None = None,
        now: datetime | None = None,
    ) -> MoneyLaunderingData:
        current = _as_utc(now) or _utc_now()
        amount = self._validate_laundering_amount(amount)
        key = self._operation_key(operation_key)
        fee = amount * _clamp_percent(self._config.laundering_fee_percent) // 100
        final_amount = amount - fee
        if final_amount <= 0:
            raise CrimeInvalidAmountError("laundering fee leaves no positive payout")
        async with self._lock:
            async with self._session_factory() as session:
                repository = CrimeRepository(session)
                existing = await repository.get_activity_by_operation_key(key)
                if existing is not None:
                    if (
                        existing.activity_type != CRIME_ACTIVITY_MONEY_LAUNDERING
                        or existing.actor_player_id != player_id
                    ):
                        raise CrimeOperationConflictError("operation key belongs to another activity")
                    return await self._existing_laundering(repository, existing)
                await self._require_player(session, player_id)
                self._check_cooldown(
                    await repository.get_latest_activity(
                        player_id,
                        CRIME_ACTIVITY_MONEY_LAUNDERING,
                        current - timedelta(seconds=max(0, self._config.laundering_cooldown_seconds)),
                    ),
                    current,
                    self._config.laundering_cooldown_seconds,
                )
                try:
                    wallet_result = await self._money.remove_money_in_transaction(
                        session, player_id, amount
                    )
                except InsufficientFundsError as exc:
                    raise CrimeInsufficientFundsError(str(exc)) from exc
                process_at = current + timedelta(
                    seconds=max(0, int(self._config.laundering_processing_seconds))
                )
                activity = await repository.create_activity(
                    activity_type=CRIME_ACTIVITY_MONEY_LAUNDERING,
                    actor_player_id=player_id,
                    target_player_id=None,
                    status=CRIME_STATUS_PENDING,
                    success=None,
                    reward_amount=final_amount,
                    fee_amount=fee,
                    operation_key=key,
                    details="پول در صف پردازش قرار گرفت",
                    created_at=current,
                )
                operation = await repository.create_laundering_operation(
                    activity_id=activity.id,
                    player_id=player_id,
                    amount=amount,
                    fee_amount=fee,
                    final_amount=final_amount,
                    process_at=process_at,
                )
                await session.commit()
                return self._laundering_data(activity, operation, wallet_result.balance_after)

    async def process_due_operations(self, *, now: datetime | None = None) -> int:
        """Atomically settle due laundering operations and شوتی missions."""

        current = _as_utc(now) or _utc_now()
        settled = 0
        async with self._lock:
            async with self._session_factory() as session:
                repository = CrimeRepository(session)
                laundering_rows = await repository.list_due_laundering(current)
                for operation in laundering_rows:
                    if not await repository.claim_laundering(operation.id):
                        continue
                    operation.status = LAUNDERING_PROCESSING
                    activity = await repository.get_activity(operation.activity_id)
                    if activity is not None:
                        await repository.update_activity(
                            activity.id,
                            status=CRIME_STATUS_PROCESSING,
                            success=None,
                            details="پردازش پول در حال تکمیل است",
                        )
                    wallet_result = await self._money.add_money_in_transaction(
                        session, operation.player_id, operation.final_amount
                    )
                    if not await repository.complete_laundering(operation.id, current):
                        raise CrimeOperationConflictError("laundering payout was already processed")
                    await repository.update_activity(
                        operation.activity_id,
                        status=CRIME_STATUS_COMPLETED,
                        success=True,
                        reward_amount=operation.final_amount,
                        details="پول‌شویی با موفقیت تکمیل شد",
                        completed_at=current,
                    )
                    operation.status = LAUNDERING_COMPLETED
                    operation.reward_paid = True
                    operation.completed_at = current
                    settled += 1

                mission_rows = await repository.list_due_shoti(current)
                for mission in mission_rows:
                    if not await repository.claim_shoti(mission.id):
                        continue
                    mission.status = SHOTI_PROCESSING
                    await repository.update_activity(
                        mission.activity_id,
                        status=CRIME_STATUS_PROCESSING,
                        success=None,
                        details="مأموریت شوتی در حال تسویه است",
                    )
                    wallet_balance_after: int | None = None
                    if mission.success:
                        wallet_result = await self._money.add_money_in_transaction(
                            session, mission.player_id, mission.reward
                        )
                        wallet_balance_after = wallet_result.balance_after
                    if not await repository.complete_shoti(
                        mission.id,
                        success=bool(mission.success),
                        reward_paid=bool(mission.success),
                        completed_at=current,
                    ):
                        raise CrimeOperationConflictError("shoti mission was already processed")
                    await repository.update_activity(
                        mission.activity_id,
                        status=CRIME_STATUS_COMPLETED if mission.success else CRIME_STATUS_FAILED,
                        success=bool(mission.success),
                        reward_amount=mission.reward if mission.success else 0,
                        details=(
                            "مأموریت شوتی موفق بود"
                            if mission.success
                            else "مأموریت شوتی ناموفق بود"
                        ),
                        completed_at=current,
                    )
                    mission.status = "completed" if mission.success else "failed"
                    mission.reward_paid = bool(mission.success)
                    mission.completed_at = current
                    settled += 1
                await session.commit()
        return settled

    async def get_laundering_history(self, player_id: int) -> tuple[MoneyLaunderingData, ...]:
        await self.process_due_operations()
        async with self._session_factory() as session:
            await self._require_player(session, player_id)
            repository = CrimeRepository(session)
            rows = await repository.list_laundering_for_player(player_id)
            result: list[MoneyLaunderingData] = []
            for operation in rows:
                activity = await repository.get_activity(operation.activity_id)
                if activity is not None:
                    result.append(self._laundering_data(activity, operation, None))
            return tuple(result)

    # ------------------------------------------------------------------
    # Fake documents
    # ------------------------------------------------------------------

    async def issue_fake_document(
        self,
        player_id: int,
        document_type: str,
        *,
        operation_key: str | None = None,
        now: datetime | None = None,
    ) -> FakeDocumentData:
        current = _as_utc(now) or _utc_now()
        definition = get_fake_document_definition(self._config.fake_documents, document_type)
        if definition is None:
            raise CrimeInvalidDocumentTypeError(document_type)
        key = self._operation_key(operation_key)
        async with self._lock:
            async with self._session_factory() as session:
                repository = CrimeRepository(session)
                existing_activity = await repository.get_activity_by_operation_key(key)
                if existing_activity is not None:
                    if (
                        existing_activity.activity_type != CRIME_ACTIVITY_FAKE_DOCUMENT
                        or existing_activity.actor_player_id != player_id
                    ):
                        raise CrimeOperationConflictError("operation key belongs to another activity")
                    document = await repository.get_document_by_activity_key(key)
                    if document is not None:
                        return self._document_data(document, definition.name, existing_activity)
                await self._require_player(session, player_id)
                await repository.expire_documents(current)
                existing = await repository.get_active_document(player_id, document_type)
                if existing is not None:
                    raise CrimeDuplicateDocumentError(document_type)
                expires_at = (
                    current + timedelta(seconds=definition.validity_seconds)
                    if definition.validity_seconds is not None
                    else None
                )
                activity = await repository.create_activity(
                    activity_type=CRIME_ACTIVITY_FAKE_DOCUMENT,
                    actor_player_id=player_id,
                    target_player_id=None,
                    status=CRIME_STATUS_COMPLETED,
                    success=True,
                    reward_amount=0,
                    fee_amount=0,
                    operation_key=key,
                    details=definition.name,
                    created_at=current,
                    completed_at=current,
                )
                document = await repository.create_document(
                    activity_id=activity.id,
                    owner_player_id=player_id,
                    document_type=document_type,
                    created_at=current,
                    expires_at=expires_at,
                )
                await repository.update_activity(
                    activity.id,
                    status=CRIME_STATUS_COMPLETED,
                    success=True,
                    completed_at=current,
                )
                await session.commit()
                return self._document_data(document, definition.name, activity)

    async def list_documents(self, player_id: int) -> tuple[FakeDocumentData, ...]:
        current = _utc_now()
        async with self._lock:
            async with self._session_factory() as session:
                await self._require_player(session, player_id)
                repository = CrimeRepository(session)
                await repository.expire_documents(current)
                rows = await repository.list_documents(player_id)
                await session.commit()
                names = {definition.code: definition.name for definition in self._config.fake_documents}
                return tuple(self._document_data(row, names.get(row.document_type, row.document_type), None) for row in rows)

    async def owns_document(self, player_id: int, document_type: str) -> bool:
        current = _utc_now()
        async with self._session_factory() as session:
            repository = CrimeRepository(session)
            await repository.expire_documents(current)
            return await repository.get_active_document(player_id, document_type) is not None

    # ------------------------------------------------------------------
    # شوتی
    # ------------------------------------------------------------------

    async def get_eligible_vehicles(self, player_id: int):
        if self._vehicles is None:
            raise CrimeNoEligibleVehicleError("vehicle service is not configured")
        owned = await self._vehicles.get_owned_vehicles(player_id)
        eligible_codes = set(self._config.shoti_vehicle_modifiers)
        return tuple(vehicle for vehicle in owned if vehicle.model.code in eligible_codes and vehicle.model.is_shoti_eligible)

    async def start_shoti_mission(
        self,
        player_id: int,
        vehicle_ownership_id: int,
        *,
        operation_key: str | None = None,
        now: datetime | None = None,
    ) -> ShotiMissionData:
        if self._vehicles is None:
            raise CrimeNoEligibleVehicleError("vehicle service is not configured")
        current = _as_utc(now) or _utc_now()
        key = self._operation_key(operation_key)
        try:
            vehicle = await self._vehicles.get_owned_vehicle(player_id, vehicle_ownership_id)
        except VehicleNotOwnedError as exc:
            raise CrimeVehicleNotOwnedError(str(vehicle_ownership_id)) from exc
        if vehicle.model.code not in self._config.shoti_vehicle_modifiers or not vehicle.model.is_shoti_eligible:
            raise CrimeVehicleNotOwnedError(str(vehicle_ownership_id))
        template = self._rng.choice(self._config.shoti_templates)
        modifier = self._config.shoti_vehicle_modifiers[vehicle.model.code]
        chance = _clamp_percent(
            self._config.shoti_success_base_percent
            + modifier
            - template.difficulty // 2
            - template.risk // 2
        )
        success = self._roll_percent(chance)
        async with self._lock:
            async with self._session_factory() as session:
                repository = CrimeRepository(session)
                existing = await repository.get_activity_by_operation_key(key)
                if existing is not None:
                    if (
                        existing.activity_type != CRIME_ACTIVITY_SHOTI
                        or existing.actor_player_id != player_id
                    ):
                        raise CrimeOperationConflictError("operation key belongs to another activity")
                    mission = await repository.get_shoti_by_activity(existing.id)
                    if mission is not None:
                        return await self._mission_data_from_session(repository, existing, mission)
                await self._require_player(session, player_id)
                active = await repository.get_active_shoti_mission(player_id)
                if active is not None:
                    raise CrimeActiveMissionError(str(active.id))
                self._check_cooldown(
                    await repository.get_latest_activity(
                        player_id,
                        CRIME_ACTIVITY_SHOTI,
                        current - timedelta(seconds=max(0, self._config.shoti_cooldown_seconds)),
                    ),
                    current,
                    self._config.shoti_cooldown_seconds,
                )
                completes_at = current + timedelta(seconds=max(0, template.duration_seconds))
                activity = await repository.create_activity(
                    activity_type=CRIME_ACTIVITY_SHOTI,
                    actor_player_id=player_id,
                    target_player_id=None,
                    status=CRIME_STATUS_PENDING,
                    success=None,
                    reward_amount=template.reward,
                    fee_amount=0,
                    operation_key=key,
                    details=f"{template.origin} ← {template.destination}؛ {vehicle.model.name}",
                    created_at=current,
                )
                mission = await repository.create_shoti_mission(
                    activity_id=activity.id,
                    player_id=player_id,
                    vehicle_ownership_id=vehicle.ownership_id,
                    vehicle_model_id=vehicle.model.model_id,
                    vehicle_name=vehicle.model.name,
                    origin=template.origin,
                    destination=template.destination,
                    shipment=template.shipment,
                    reward=template.reward,
                    difficulty=template.difficulty,
                    risk=template.risk,
                    duration_seconds=max(0, template.duration_seconds),
                    started_at=current,
                    completes_at=completes_at,
                    status=SHOTI_PENDING,
                    success=success,
                )
                await session.commit()
                result = self._mission_data(activity, mission, None)
        if template.duration_seconds <= 0:
            await self.process_due_operations(now=current)
            missions = await self.get_shoti_missions(player_id, settle=False)
            for item in missions:
                if item.mission_id == result.mission_id:
                    return item
        return result

    async def get_shoti_missions(
        self, player_id: int, *, settle: bool = True
    ) -> tuple[ShotiMissionData, ...]:
        if settle:
            await self.process_due_operations()
        async with self._session_factory() as session:
            await self._require_player(session, player_id)
            repository = CrimeRepository(session)
            rows = await repository.list_shoti_for_player(player_id)
            result: list[ShotiMissionData] = []
            for mission in rows:
                activity = await repository.get_activity(mission.activity_id)
                if activity is not None:
                    result.append(self._mission_data(activity, mission, None))
            return tuple(result)

    # ------------------------------------------------------------------
    # Bank hacking
    # ------------------------------------------------------------------

    async def hack_bank_account(
        self,
        attacker_player_id: int,
        target_player_id: int,
        *,
        operation_key: str | None = None,
        now: datetime | None = None,
    ) -> BankHackResult:
        current = _as_utc(now) or _utc_now()
        key = self._operation_key(operation_key)
        async with self._lock:
            # Validate the L.I.R account before creating the attempt. This is
            # a read through BankService, never a handler/repository shortcut.
            try:
                target_account = await self._bank.get_existing_account(target_player_id)
            except PlayerNotFoundError as exc:
                raise CrimeInvalidTargetError(str(target_player_id)) from exc
            if target_account is None:
                raise CrimeTargetBankAccountError(str(target_player_id))
            # Interest is part of the existing bank rules; settle it before
            # checking whether the configured hack amount is available.
            await self._bank.process_interest_for_player(target_player_id)
            target_account = await self._bank.get_existing_account(target_player_id)
            if target_account is None:
                raise CrimeTargetBankAccountError(str(target_player_id))

            configured_amount = self._positive_config_amount(self._config.bank_hack_amount)
            activity_id: int
            attempt_id: int
            target_name: str
            async with self._session_factory() as session:
                repository = CrimeRepository(session)
                existing = await repository.get_activity_by_operation_key(key)
                if existing is not None:
                    if (
                        existing.activity_type != CRIME_ACTIVITY_BANK_HACK
                        or existing.actor_player_id != attacker_player_id
                        or existing.target_player_id != target_player_id
                    ):
                        raise CrimeOperationConflictError("operation key belongs to another activity")
                    attempt = await repository.get_bank_hack(existing.id)
                    target = await PlayerRepository(session).get_by_id(target_player_id)
                    if attempt is None or target is None:
                        raise CrimeOperationConflictError("hack record is incomplete")
                    if attempt.status != BANK_HACK_PENDING:
                        return self._hack_result(existing, attempt, target.display_name)
                    activity_id = existing.id
                    attempt_id = attempt.id
                    target_name = target.display_name
                    configured_amount = int(attempt.configured_amount)
                    success_decision = (
                        bool(attempt.success)
                        if attempt.success is not None
                        else self._roll_percent(self._config.bank_hack_success_percent)
                    )
                    # A crash can leave an old pending row without a stored
                    # decision. Persist the decision before touching the bank.
                    if attempt.success is None:
                        attempt.success = success_decision
                        await session.commit()
                else:
                    attacker, target = await self._require_target(
                        session, attacker_player_id, target_player_id
                    )
                    self._check_cooldown(
                        await repository.get_latest_activity(
                            attacker_player_id,
                            CRIME_ACTIVITY_BANK_HACK,
                            current
                            - timedelta(
                                seconds=max(0, self._config.bank_hack_cooldown_seconds)
                            ),
                        ),
                        current,
                        self._config.bank_hack_cooldown_seconds,
                    )
                    target_name = target.display_name
                    success_decision = self._roll_percent(
                        self._config.bank_hack_success_percent
                    )
                    activity = await repository.create_activity(
                        activity_type=CRIME_ACTIVITY_BANK_HACK,
                        actor_player_id=attacker.id,
                        target_player_id=target.id,
                        status=CRIME_STATUS_PENDING,
                        success=None,
                        reward_amount=0,
                        fee_amount=0,
                        operation_key=key,
                        details="تلاش برای نفوذ به حساب بانکی",
                        created_at=current,
                    )
                    attempt = await repository.create_bank_hack(
                        activity_id=activity.id,
                        attacker_player_id=attacker.id,
                        target_player_id=target.id,
                        target_bank_account_id=target_account.account_id,
                        configured_amount=configured_amount,
                        transferred_amount=0,
                        success=success_decision,
                        status=BANK_HACK_PENDING,
                        reason="",
                        created_at=current,
                    )
                    activity_id = activity.id
                    attempt_id = attempt.id
                    await session.commit()

            # Refresh the strict target account after a retry. BankService is
            # still the authority for the final conditional debit.
            target_account = await self._bank.get_existing_account(target_player_id)
            success = bool(success_decision)
            transferred = 0
            reason = "نفوذ شکست خورد"
            if success and target_account is not None:
                try:
                    bank_result = await self._bank.transfer_to_player(
                        target_player_id,
                        attacker_player_id,
                        configured_amount,
                        operation_id=f"crime-bank-{key}",
                    )
                    transferred = bank_result.amount
                    reason = "نفوذ موفق بود"
                except (BankError, BankInsufficientBalanceError):
                    success = False
                    reason = "موجودی حساب هدف برای برداشت کافی نبود"
            elif success:
                success = False
                reason = "حساب بانکی هدف دیگر فعال نیست"

            async with self._session_factory() as session:
                repository = CrimeRepository(session)
                activity = await repository.get_activity(activity_id)
                attempt = await repository.get_bank_hack(activity_id)
                if activity is None or attempt is None:
                    raise CrimeOperationConflictError("hack activity disappeared")
                if attempt.status != BANK_HACK_PENDING:
                    return self._hack_result(activity, attempt, target_name)
                await repository.complete_bank_hack(
                    attempt_id,
                    success=success,
                    transferred_amount=transferred,
                    reason=reason,
                    completed_at=current,
                )
                await repository.update_activity(
                    activity.id,
                    status=CRIME_STATUS_COMPLETED if success else CRIME_STATUS_FAILED,
                    success=success,
                    reward_amount=transferred,
                    details=reason,
                    completed_at=current,
                )
                await session.commit()
                await session.refresh(activity)
                await session.refresh(attempt)
                return self._hack_result(activity, attempt, target_name)

    # ------------------------------------------------------------------
    # History and scheduling
    # ------------------------------------------------------------------

    async def get_history(
        self, player_id: int, *, page: int = 0, page_size: int = 8
    ) -> tuple[tuple[CrimeActivityData, ...], int, int, int]:
        page = max(0, int(page))
        page_size = max(1, min(50, int(page_size)))
        await self.process_due_operations()
        async with self._session_factory() as session:
            await self._require_player(session, player_id)
            repository = CrimeRepository(session)
            total = await repository.count_activities(player_id)
            rows = await repository.list_activities(
                player_id, offset=page * page_size, limit=page_size
            )
            return tuple(self._activity_data(row) for row in rows), total, page, page_size

    async def start_scheduler(self, interval_seconds: int | None = None) -> None:
        if self._scheduler_task is not None and not self._scheduler_task.done():
            return
        self._scheduler_stop = asyncio.Event()
        interval = max(1, int(interval_seconds or self._config.scheduler_interval_seconds))
        self._scheduler_task = asyncio.create_task(self._scheduler_loop(interval))

    async def stop_scheduler(self) -> None:
        task = self._scheduler_task
        if task is None:
            return
        if self._scheduler_stop is not None:
            self._scheduler_stop.set()
        try:
            await task
        finally:
            self._scheduler_task = None
            self._scheduler_stop = None

    async def _scheduler_loop(self, interval_seconds: int) -> None:
        stop = self._scheduler_stop
        if stop is None:
            return
        while not stop.is_set():
            try:
                await self.process_due_operations()
            except Exception:  # pragma: no cover - defensive worker boundary
                logger.exception("Crime scheduled settlement failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                continue

    # ------------------------------------------------------------------
    # Internal conversion/validation helpers
    # ------------------------------------------------------------------

    async def _existing_information(
        self, repository: CrimeRepository, activity
    ) -> InformationSellingResult:
        operation = await repository.get_information_operation(activity.id)
        if operation is None:
            raise CrimeOperationConflictError("information record is incomplete")
        return self._information_result(activity, operation)

    async def _existing_laundering(
        self, repository: CrimeRepository, activity
    ) -> MoneyLaunderingData:
        operation = await repository.get_laundering_by_activity(activity.id)
        if operation is None:
            raise CrimeOperationConflictError("laundering record is incomplete")
        return self._laundering_data(activity, operation, None)

    async def _existing_hack(self, repository: CrimeRepository, activity) -> BankHackResult:
        attempt = await repository.get_bank_hack(activity.id)
        if attempt is None:
            raise CrimeOperationConflictError("hack record is incomplete")
        target_name = await repository.get_player_display_name(attempt.target_player_id)
        return self._hack_result(activity, attempt, target_name or "بازیکن هدف")

    async def _require_player(self, session: AsyncSession, player_id: int):
        player = await PlayerRepository(session).get_by_id(player_id)
        if player is None:
            raise PlayerNotFoundError(str(player_id))
        return player

    async def _require_target(self, session: AsyncSession, actor_id: int, target_id: int):
        actor = await self._require_player(session, actor_id)
        target = await PlayerRepository(session).get_by_id(target_id)
        if target is None:
            raise CrimeInvalidTargetError(str(target_id))
        if actor.id == target.id:
            raise CrimeInvalidTargetError("self target")
        return actor, target

    def _check_cooldown(self, latest, now: datetime, cooldown_seconds: int) -> None:
        if latest is None or cooldown_seconds <= 0:
            return
        created_at = _as_utc(latest.created_at) or now
        remaining = int(cooldown_seconds - (now - created_at).total_seconds())
        if remaining > 0:
            raise CrimeCooldownError(remaining)

    def _operation_key(self, operation_key: str | None) -> str:
        if operation_key:
            return str(operation_key)[:64]
        return f"crime-{token_hex(24)}"

    def _roll_percent(self, percent: int) -> bool:
        return self._rng.randrange(100) < _clamp_percent(percent)

    @staticmethod
    def _positive_config_amount(amount: int) -> int:
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            raise CrimeInvalidAmountError("invalid crime reward configuration")
        return amount

    def _validate_laundering_amount(self, amount: int) -> int:
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            raise CrimeInvalidAmountError("amount must be a positive integer")
        if amount < self._config.laundering_min_amount or amount > self._config.laundering_max_amount:
            raise CrimeInvalidAmountError("amount is outside laundering limits")
        return amount

    @staticmethod
    def _generate_information(target, success: bool) -> str:
        if not success:
            return f"گزارش ناقص درباره «{target.display_name}» پیدا شد؛ اطلاعات قابل فروش نبود."
        family = "متأهل است" if target.spouse_player_id is not None else "مجرد است"
        return (
            f"گزارش ساختگی درباره «{target.display_name}»: "
            f"سطح {target.level}، {family}، و {target.xp} امتیاز تجربه دارد."
        )

    @staticmethod
    def _activity_data(activity) -> CrimeActivityData:
        return CrimeActivityData(
            activity_id=activity.id,
            activity_type=activity.activity_type,
            actor_player_id=activity.actor_player_id,
            target_player_id=activity.target_player_id,
            status=activity.status,
            success=activity.success,
            reward_amount=int(activity.reward_amount),
            fee_amount=int(activity.fee_amount),
            operation_key=activity.operation_key,
            details=activity.details,
            created_at=_as_utc(activity.created_at) or _utc_now(),
            completed_at=_as_utc(activity.completed_at),
        )

    def _information_result(self, activity, operation) -> InformationSellingResult:
        return InformationSellingResult(
            activity=self._activity_data(activity),
            target_player_id=operation.target_player_id,
            target_name=operation.target_name,
            success=operation.success,
            reward_amount=int(operation.reward_amount),
            information=operation.information_text,
        )

    def _laundering_data(self, activity, operation, wallet_balance_after: int | None) -> MoneyLaunderingData:
        return MoneyLaunderingData(
            activity=self._activity_data(activity),
            operation_id=operation.id,
            player_id=operation.player_id,
            amount=int(operation.amount),
            fee_amount=int(operation.fee_amount),
            final_amount=int(operation.final_amount),
            status=operation.status,
            process_at=_as_utc(operation.process_at) or _utc_now(),
            completed_at=_as_utc(operation.completed_at),
            wallet_balance_after=wallet_balance_after,
        )

    @staticmethod
    def _document_data(document, name: str, activity) -> FakeDocumentData:
        return FakeDocumentData(
            document_id=document.id,
            owner_player_id=document.owner_player_id,
            document_type=document.document_type,
            document_name=name,
            status=document.status,
            created_at=_as_utc(document.created_at) or _utc_now(),
            expires_at=_as_utc(document.expires_at),
            activity=CrimeService._activity_data(activity) if activity is not None else None,
        )

    @staticmethod
    def _mission_data(activity, mission, wallet_balance_after: int | None) -> ShotiMissionData:
        return ShotiMissionData(
            mission_id=mission.id,
            activity=CrimeService._activity_data(activity),
            player_id=mission.player_id,
            vehicle_ownership_id=mission.vehicle_ownership_id,
            vehicle_model_id=mission.vehicle_model_id,
            vehicle_name=mission.vehicle_name,
            origin=mission.origin,
            destination=mission.destination,
            shipment=mission.shipment,
            reward=int(mission.reward),
            difficulty=int(mission.difficulty),
            risk=int(mission.risk),
            duration_seconds=int(mission.duration_seconds),
            started_at=_as_utc(mission.started_at) or _utc_now(),
            completes_at=_as_utc(mission.completes_at) or _utc_now(),
            status=mission.status,
            success=mission.success,
            reward_paid=mission.reward_paid,
            completed_at=_as_utc(mission.completed_at),
            wallet_balance_after=wallet_balance_after,
        )

    async def _mission_data_from_session(self, repository, activity, mission):
        return self._mission_data(activity, mission, None)

    def _hack_result(self, activity, attempt, target_name: str) -> BankHackResult:
        return BankHackResult(
            activity=self._activity_data(activity),
            attempt_id=attempt.id,
            attacker_player_id=attempt.attacker_player_id,
            target_player_id=attempt.target_player_id,
            target_name=target_name,
            success=bool(attempt.success),
            configured_amount=int(attempt.configured_amount),
            transferred_amount=int(attempt.transferred_amount),
            reason=attempt.reason,
        )
