"""Marriage and Family service — the transaction boundary for family life.

Business rules live here; handlers only translate Telegram objects into calls,
and every query goes through a repository. The service reuses the *existing*
game systems rather than inventing parallel ones:

* **Wallet** — Mahriyeh and cheating fines move through the same atomic
  ``remove_money_if_enough`` / ``add_money`` pair the housing market uses,
  inside the same transaction as the family state change, so the ledger and
  the marriage can never drift apart.
* **Level/XP** — marriage, relationship and births grant XP explicitly
  through ``LevelService`` (never implicitly), exactly like house purchases.
* **Users** — players are resolved through ``PlayerRepository``; family
  pointers on ``players`` are written in the same transaction as the marriage
  row, so a profile can never show a spouse the marriage table disagrees with.

Time-based outcomes (a pregnancy) settle **lazily** with an atomic claim,
mirroring construction/renovation completion — no scheduler is required, and
a future cron can call :meth:`FamilyService.settle_due` periodically.

Pure rules (Mahriyeh size, quality bounds, pregnancy odds, consequence tiers)
live in ``app/game/family/domain.py``. Every dice roll goes through
``self._rng``, which is injectable — that is what lets tests force a
discovery, a pregnancy, or a forced divorce deterministically.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import constants
from app.database.models.child import Child
from app.database.models.divorce_record import REASON_CHEATING, REASON_INITIATED, DivorceRecord
from app.database.models.family_history import (
    EVENT_BIRTH,
    EVENT_CHEATING_DISCOVERED,
    EVENT_DIVORCE,
    EVENT_FORCED_DIVORCE,
    EVENT_MARRIAGE,
    EVENT_MARRIAGE_REQUEST,
    EVENT_PREGNANCY,
    EVENT_REQUEST_EXPIRED,
    EVENT_REQUEST_REJECTED,
)
from app.database.models.marriage import Marriage
from app.database.models.marriage_request import MarriageRequest
from app.database.models.relationship_event import (
    EVENT_CHEATING_DISCOVERED as EV_CHEATING_DISCOVERED,
)
from app.database.models.relationship_event import (
    EVENT_CHEATING_FAILED,
    EVENT_CHEATING_SUCCESS,
    EVENT_RELATIONSHIP,
    OUTCOME_NEUTRAL,
    OUTCOME_PREGNANCY,
    RelationshipEvent,
)
from app.database.repositories.child_repository import ChildRepository
from app.database.repositories.divorce_record_repository import DivorceRecordRepository
from app.database.repositories.family_history_repository import FamilyHistoryRepository
from app.database.repositories.marriage_repository import MarriageRepository
from app.database.repositories.marriage_request_repository import MarriageRequestRepository
from app.database.repositories.player_repository import PlayerRepository
from app.database.repositories.relationship_event_repository import (
    RelationshipEventRepository,
)
from app.game.admin import runtime as admin_runtime
from app.game.family import domain
from app.game.family.dto import (
    CheatingResult,
    ChildData,
    DivorceResult,
    FamilyHistoryEntryData,
    FamilyInfoData,
    FamilySettlement,
    MarriageData,
    MarriageRequestData,
    MarriageResult,
    RelationshipResult,
)
from app.game.housing.construction_year import current_iranian_year
from app.game.shared.errors import (
    DomainError,
    InsufficientFundsError,
    PlayerNotFoundError,
)

logger = logging.getLogger(__name__)

# Children are named deterministically by birth order — no RNG, so a settled
# birth reproduces exactly in tests.
CHILD_NAMES: tuple[str, ...] = (
    "سارا",
    "آرش",
    "نگار",
    "سینا",
    "رها",
    "کیان",
    "نی‌آسا",
    "آریا",
)


# --- Errors (handlers translate these into Persian messages) ----------------


class FamilyError(DomainError):
    """Base class for every family-system domain error."""


class AlreadyMarriedError(FamilyError):
    """A married player cannot marry again."""

    def __init__(self, message: str = "", *, spouse_player_id: int | None = None) -> None:
        super().__init__(message or "player is already married")
        self.spouse_player_id = spouse_player_id


class NotMarriedError(FamilyError):
    """The action requires an active marriage."""


class CannotMarryYourselfError(FamilyError):
    """A player cannot propose to themselves."""


class TargetAlreadyMarriedError(FamilyError):
    """The proposal target is already married to somebody else."""

    def __init__(self, message: str = "", *, spouse_player_id: int | None = None) -> None:
        super().__init__(message or "target is already married")
        self.spouse_player_id = spouse_player_id


class MarriageRequirementError(FamilyError):
    """The level or wallet gate for proposing is not met.

    Carries ``kind`` (``level`` | ``money``) and the player's actual value so
    the handler can render the Persian message without querying again.
    """

    def __init__(
        self, message: str = "", *, kind: str = "level", actual: int = 0, required: int = 0
    ) -> None:
        super().__init__(message or "marriage requirements not met")
        self.kind = kind
        self.actual = actual
        self.required = required


class NoPendingRequestError(FamilyError):
    """There is no open marriage request to answer."""


class RequestExpiredError(FamilyError):
    """The request existed but its window has closed."""


class MahriyehUnaffordableError(InsufficientFundsError):
    """Divorce is blocked until the Mahriyeh can be paid.

    Carries the exact numbers so the handler can show the required amount and
    the current balance without querying again.
    """

    def __init__(self, message: str = "", *, required: int = 0, balance: int = 0) -> None:
        super().__init__(message or f"cannot afford mahriyeh of {required}")
        self.required = required
        self.balance = balance


class NotSpouseError(FamilyError):
    """«رابطه» has to be a reply to the spouse's own message."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; normalize before comparing."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class FamilyService:
    """Every family use case: marriage, divorce, cheating, children."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        level_service=None,
        money_service=None,
        rng: random.Random | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._levels = level_service
        self._money = money_service
        self._rng = rng if rng is not None else random.Random()

    # === Lazy settlement =====================================================

    async def settle_due(self, now: datetime | None = None) -> FamilySettlement:
        """Expire stale requests and complete due pregnancies.

        Safe to call as often as you like: each transition is claimed by a
        guarded ``UPDATE``, so concurrent callers never double-apply.
        """
        moment = now or _utc_now()
        expired = await self._expire_requests(moment)
        births = await self._settle_due_births(moment)
        return FamilySettlement(children_born=len(births), requests_expired=expired, births=births)

    async def _expire_requests(self, now: datetime) -> int:
        async with self._session_factory() as session:
            requests = await MarriageRequestRepository(session).list_expired(now)
            count = 0
            for request in requests:
                if not await MarriageRequestRepository(session).claim_expired(request.id, now):
                    continue  # answered by a racing caller
                await FamilyHistoryRepository(session).add(
                    player_id=request.proposer_player_id,
                    event_type=EVENT_REQUEST_EXPIRED,
                    other_player_id=request.target_player_id,
                    note="پاسخی نیامد؛ درخواست ازدواج منقضی شد",
                )
                count += 1
            if count:
                await session.commit()
                logger.info("Expired %s unanswered marriage request(s)", count)
            return count

    async def _settle_due_births(self, now: datetime) -> list[ChildData]:
        births: list[ChildData] = []
        async with self._session_factory() as session:
            marriage_repo = MarriageRepository(session)
            event_repo = RelationshipEventRepository(session)
            child_repo = ChildRepository(session)
            player_repo = PlayerRepository(session)
            history_repo = FamilyHistoryRepository(session)

            for marriage in await marriage_repo.list_due_pregnancies(now):
                # Claim the pregnancy first — the loser of the race moves on.
                if not await marriage_repo.claim_birth(marriage.id):
                    continue

                event_id = marriage.pregnancy_event_id
                event = await event_repo.get_by_id(event_id) if event_id else None
                if event is not None and event.marriage_id != marriage.id:
                    event = None  # stale pointer — never settle the wrong family

                if await child_repo.count_by_marriage(marriage.id) >= constants.MAX_CHILDREN_PER_MARRIAGE:
                    if event is not None:
                        await event_repo.mark_settled(event.id, 0)
                    continue

                child = Child(
                    marriage_id=marriage.id,
                    father_player_id=marriage.husband_player_id,
                    mother_player_id=marriage.wife_player_id,
                    name=self._child_name(await child_repo.count_by_marriage(marriage.id)),
                    birth_date=now,
                    birth_year=current_iranian_year(now),
                )
                child_repo.add(child)
                await session.flush()  # need child.id

                if event is not None:
                    await event_repo.mark_settled(event.id, child.id)

                parents = (marriage.husband_player_id, marriage.wife_player_id)
                for parent_id in parents:
                    other = marriage.wife_player_id if parent_id == parents[0] else parents[0]
                    await player_repo.set_children_count(parent_id, await child_repo.count_by_player(parent_id))
                    await history_repo.add(
                        player_id=parent_id,
                        event_type=EVENT_BIRTH,
                        marriage_id=marriage.id,
                        other_player_id=other,
                        note=f"فرزند خانواده ({child.name}) به دنیا آمد",
                    )

                births.append(
                    ChildData(
                        child_id=child.id,
                        marriage_id=marriage.id,
                        father_player_id=child.father_player_id,
                        mother_player_id=child.mother_player_id,
                        name=child.name,
                        birth_date=now,
                        birth_year=child.birth_year,
                        age_years=0,
                        growth_stage=child.growth_stage,
                    )
                )
                logger.info(
                    "Child %s born into marriage %s (father=%s mother=%s)",
                    child.id,
                    marriage.id,
                    marriage.husband_player_id,
                    marriage.wife_player_id,
                )
            if births:
                await session.commit()

        # XP is granted after the settlement transaction commits — LevelService
        # owns its own commit, exactly like the housing purchase flow.
        for birth in births:
            await self._grant_xp(birth.father_player_id, constants.BIRTH_XP, constants.BIRTH_XP_REASON)
            await self._grant_xp(birth.mother_player_id, constants.BIRTH_XP, constants.BIRTH_XP_REASON)
        return births

    @staticmethod
    def _child_name(index: int) -> str:
        return CHILD_NAMES[index % len(CHILD_NAMES)]

    # === Marriage requests =====================================================

    async def create_request(
        self,
        *,
        proposer_player_id: int,
        target_player_id: int,
        message: str = "",
    ) -> MarriageRequestData:
        """Open an «ازدواج» request against ``target_player_id``.

        Raises:
            PlayerNotFoundError: Either player is unregistered.
            CannotMarryYourselfError: Proposer == target.
            AlreadyMarriedError: The proposer is married.
            TargetAlreadyMarriedError: The target is married.
            MarriageRequirementError: Level / wallet gate not met.
            NoPendingRequestError: Another request is already open for them.
        """
        now = _utc_now()
        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            marriage_repo = MarriageRepository(session)
            request_repo = MarriageRequestRepository(session)

            proposer = await player_repo.get_by_id(proposer_player_id)
            target = await player_repo.get_by_id(target_player_id)
            if proposer is None:
                raise PlayerNotFoundError(f"player_id={proposer_player_id} not found")
            if target is None:
                raise PlayerNotFoundError(f"player_id={target_player_id} not found")
            if proposer.id == target.id:
                raise CannotMarryYourselfError("proposer and target are the same player")

            if await marriage_repo.get_active_for_player(proposer.id) is not None:
                raise AlreadyMarriedError(
                    "proposer is already married", spouse_player_id=proposer.spouse_player_id
                )
            if await marriage_repo.get_active_for_player(target.id) is not None:
                raise TargetAlreadyMarriedError(
                    "target is already married", spouse_player_id=target.spouse_player_id
                )

            if proposer.level < constants.MARRIAGE_MIN_LEVEL:
                raise MarriageRequirementError(
                    f"level {proposer.level} below {constants.MARRIAGE_MIN_LEVEL}",
                    kind="level",
                    actual=proposer.level,
                    required=constants.MARRIAGE_MIN_LEVEL,
                )
            if proposer.money < constants.MARRIAGE_MIN_MONEY:
                raise MarriageRequirementError(
                    f"money {proposer.money} below {constants.MARRIAGE_MIN_MONEY}",
                    kind="money",
                    actual=proposer.money,
                    required=constants.MARRIAGE_MIN_MONEY,
                )

            if await request_repo.has_pending_involving(proposer.id):
                raise NoPendingRequestError("the proposer already has an open request")
            if await request_repo.get_pending_for_target(target.id) is not None:
                raise NoPendingRequestError("the target already has an open request")

            mahriyeh = domain.compute_mahriyeh(
                proposer.level, proposer.money, admin_runtime.effective_market_factor()
            )
            request = MarriageRequest(
                proposer_player_id=proposer.id,
                target_player_id=target.id,
                mahriyeh_amount=mahriyeh,
                message=(message or "").strip()[:256],
                expires_at=now + timedelta(hours=constants.MARRIAGE_REQUEST_EXPIRY_HOURS),
            )
            request_repo.add(request)
            await FamilyHistoryRepository(session).add(
                player_id=proposer.id,
                event_type=EVENT_MARRIAGE_REQUEST,
                other_player_id=target.id,
                amount=mahriyeh,
                note=f"درخواست ازدواج برای {target.display_name} ثبت شد",
            )
            try:
                await session.commit()
            except IntegrityError:
                # Lost the partial-unique "one pending request" race.
                await session.rollback()
                raise NoPendingRequestError("a request involving these players is already open") from None

            logger.info(
                "Marriage request %s opened: %s -> %s (mahriyeh=%s)",
                request.id,
                proposer.id,
                target.id,
                mahriyeh,
            )
            return self._to_request_dto(request, proposer.display_name)

    @staticmethod
    def _to_request_dto(request: MarriageRequest, proposer_name: str) -> MarriageRequestData:
        return MarriageRequestData(
            request_id=request.id,
            proposer_player_id=request.proposer_player_id,
            proposer_name=proposer_name,
            target_player_id=request.target_player_id,
            mahriyeh_amount=request.mahriyeh_amount,
            created_at=request.created_at,
            expires_at=request.expires_at,
            message=request.message,
        )

    async def get_pending_request_for(self, player_id: int) -> MarriageRequestData | None:
        """The open request this player still has to answer."""
        await self._expire_requests(_utc_now())
        async with self._session_factory() as session:
            request = await MarriageRequestRepository(session).get_pending_for_target(player_id)
            if request is None:
                return None
            names = await PlayerRepository(session).get_display_names({request.proposer_player_id})
            return self._to_request_dto(request, names.get(request.proposer_player_id, "?"))

    # === Accept / reject ========================================================

    async def accept_request(self, player_id: int) -> MarriageResult:
        """The target accepts: create the marriage and connect both profiles.

        The request row is claimed atomically before anything else changes, so
        a double accept (or an accept racing the expiry settler) creates
        exactly one marriage. Both family-pointer sides and the marriage row
        are written in the same transaction.

        Raises:
            NoPendingRequestError: Nothing to accept (or it was already answered).
            RequestExpiredError: The window closed.
            PlayerNotFoundError: A player vanished.
            AlreadyMarriedError: Either side married in the meantime.
        """
        now = _utc_now()
        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            marriage_repo = MarriageRepository(session)
            request_repo = MarriageRequestRepository(session)
            history_repo = FamilyHistoryRepository(session)

            request = await request_repo.get_pending_for_target(player_id)
            if request is None:
                raise NoPendingRequestError("no pending marriage request for this player")
            if _as_utc(request.expires_at) <= now:
                raise RequestExpiredError("the request expired before it was answered")

            proposer = await player_repo.get_by_id(request.proposer_player_id)
            target = await player_repo.get_by_id(player_id)
            if proposer is None or target is None:
                raise PlayerNotFoundError("one of the players no longer exists")

            if await marriage_repo.get_active_for_player(proposer.id) is not None:
                raise AlreadyMarriedError("the proposer married in the meantime")
            if await marriage_repo.get_active_for_player(target.id) is not None:
                raise AlreadyMarriedError("the target is already married")

            if not await request_repo.claim_accepted(request.id, now):
                raise NoPendingRequestError("the request was already answered")

            # Snapshot every scalar we still need *before* mutating: the
            # pointer writes below expire the cached Player instances, and an
            # expired attribute cannot be lazily loaded in async code.
            husband_id, wife_id = proposer.id, target.id
            husband_name, wife_name = proposer.display_name, target.display_name
            husband_level, husband_money = proposer.level, proposer.money

            mahriyeh = request.mahriyeh_amount or domain.compute_mahriyeh(
                husband_level, husband_money, admin_runtime.effective_market_factor()
            )
            marriage = Marriage(
                husband_player_id=husband_id,
                wife_player_id=wife_id,
                mahriyeh_amount=mahriyeh,
                relationship_quality=constants.RELATIONSHIP_QUALITY_START,
                started_at=now,
            )
            marriage_repo.add(marriage)
            await session.flush()  # need marriage.id

            await request_repo.set_marriage(request.id, marriage.id)
            await player_repo.set_family_pointers(
                husband_id, spouse_player_id=wife_id, marriage_id=marriage.id, married_since=now
            )
            await player_repo.set_family_pointers(
                wife_id, spouse_player_id=husband_id, marriage_id=marriage.id, married_since=now
            )
            for me, other in ((husband_id, wife_id), (wife_id, husband_id)):
                await history_repo.add(
                    player_id=me,
                    event_type=EVENT_MARRIAGE,
                    marriage_id=marriage.id,
                    other_player_id=other,
                    amount=mahriyeh,
                    note="ازدواج ثبت شد",
                )
            await session.commit()

            logger.info(
                "Marriage %s created: %s + %s (mahriyeh=%s)",
                marriage.id,
                husband_id,
                wife_id,
                mahriyeh,
            )

        xp_husband = await self._grant_xp(husband_id, constants.MARRIAGE_XP, constants.MARRIAGE_XP_REASON)
        xp_wife = await self._grant_xp(wife_id, constants.MARRIAGE_XP, constants.MARRIAGE_XP_REASON)
        return MarriageResult(
            marriage_id=marriage.id,
            husband_player_id=husband_id,
            wife_player_id=wife_id,
            husband_name=husband_name,
            wife_name=wife_name,
            mahriyeh_amount=mahriyeh,
            started_at=now,
            relationship_quality=constants.RELATIONSHIP_QUALITY_START,
            xp_granted_husband=xp_husband,
            xp_granted_wife=xp_wife,
        )

    async def reject_request(self, player_id: int, *, note: str = "") -> MarriageRequestData:
        """The target rejects the open request («رد» — no buttons needed).

        Raises:
            NoPendingRequestError: Nothing to reject / already answered.
        """
        now = _utc_now()
        async with self._session_factory() as session:
            request_repo = MarriageRequestRepository(session)
            player_repo = PlayerRepository(session)
            history_repo = FamilyHistoryRepository(session)

            request = await request_repo.get_pending_for_target(player_id)
            if request is None:
                raise NoPendingRequestError("no pending marriage request for this player")
            if not await request_repo.claim_rejected(request.id, now):
                raise NoPendingRequestError("the request was already answered")

            proposer_id = request.proposer_player_id
            await history_repo.add(
                player_id=proposer_id,
                event_type=EVENT_REQUEST_REJECTED,
                other_player_id=player_id,
                note=(note or "درخواست ازدواج رد شد")[:256],
            )
            names = await player_repo.get_display_names({proposer_id})
            await session.commit()
            return self._to_request_dto(request, names.get(proposer_id, "?"))

    async def cancel_request(self, player_id: int) -> MarriageRequestData:
        """The proposer withdraws their own open request («لغو ازدواج»).

        Raises:
            NoPendingRequestError: The proposer has no open request.
        """
        now = _utc_now()
        async with self._session_factory() as session:
            request_repo = MarriageRequestRepository(session)
            player_repo = PlayerRepository(session)
            history_repo = FamilyHistoryRepository(session)

            request = await request_repo.get_pending_from_proposer(player_id)
            if request is None:
                raise NoPendingRequestError("no pending marriage request to cancel")
            if not await request_repo.claim_cancelled(request.id, now):
                raise NoPendingRequestError("the request was already answered")

            await history_repo.add(
                player_id=player_id,
                event_type=EVENT_REQUEST_REJECTED,
                other_player_id=request.target_player_id,
                note="درخواست ازدواج لغو شد",
            )
            names = await player_repo.get_display_names({request.target_player_id})
            await session.commit()
            return self._to_request_dto(request, names.get(request.target_player_id, "?"))

    # === Divorce ================================================================

    async def divorce(self, player_id: int) -> DivorceResult:
        """End the marriage by paying the stored Mahriyeh to the spouse.

        The initiator pays — Mahriyeh is the price of *leaving*, not a gift.
        The one exception: the wronged spouse (the partner was caught cheating
        at least ``CHEATING_WAIVER_STRIKES`` times) is waived and leaves free.

        Money moves through the wallet's own atomic primitives inside the same
        transaction as the status change, so a divorce nobody can afford simply
        never happens — there is no partial state to clean up.

        Raises:
            NotMarriedError: The player is single.
            MahriyehUnaffordableError: Balance below the Mahriyeh — carries
                ``.required`` / ``.balance`` so the handler can name the amount.
        """
        async with self._session_factory() as session:
            return await self._end_marriage(session, player_id, reason=REASON_INITIATED)

    async def _end_marriage(
        self,
        session: AsyncSession,
        initiator_player_id: int,
        *,
        reason: str,
        payer_override: int | None = None,
        force_unpayable: bool = False,
    ) -> DivorceResult:
        """Shared divorce core — also used by the forced (tier-three) path.

        ``payer_override`` redirects the debt (a forced divorce makes the
        *cheater* pay, not whoever triggered the flow), and
        ``force_unpayable`` records an unaffordable Mahriyeh as owed-but-unpaid
        instead of raising, because the marriage must end either way.
        """
        now = _utc_now()
        player_repo = PlayerRepository(session)
        marriage_repo = MarriageRepository(session)
        child_repo = ChildRepository(session)
        history_repo = FamilyHistoryRepository(session)
        divorce_repo = DivorceRecordRepository(session)

        if await player_repo.get_by_id(initiator_player_id) is None:
            raise PlayerNotFoundError(f"player_id={initiator_player_id} not found")
        marriage = await marriage_repo.get_active_for_player(initiator_player_id)
        if marriage is None:
            raise NotMarriedError("player is not married")

        spouse_id = await marriage_repo.spouse_id_of(marriage, initiator_player_id)
        if spouse_id is None:  # pragma: no cover — the lookup guarantees a spouse
            raise NotMarriedError("the marriage row is inconsistent")

        # The wronged party never pays: whoever the cheating blamed gets a
        # waiver once the strike threshold is reached.
        wronged = marriage.cheater_player_id is not None and marriage.cheater_player_id != initiator_player_id
        waived = (
            reason != REASON_CHEATING
            and wronged
            and domain.can_waive_mahriyeh(marriage.cheating_strikes)
        )
        amount = 0 if waived else marriage.mahriyeh_amount
        payer_id = payer_override if payer_override is not None else initiator_player_id
        payee_id = spouse_id if payer_id == initiator_player_id else initiator_player_id
        if payer_id == payee_id:  # pragma: no cover — defensive
            payee_id = spouse_id

        paid = False
        balance_after = await player_repo.get_money(payer_id) or 0
        if amount > 0:
            if await player_repo.remove_money_if_enough(payer_id, amount):
                if not await player_repo.add_money(payee_id, amount):
                    raise PlayerNotFoundError(f"payee player_id={payee_id} not found")
                paid = True
                balance_after = await player_repo.get_money(payer_id) or 0
            elif not force_unpayable:
                balance = await player_repo.get_money(payer_id)
                raise MahriyehUnaffordableError(
                    f"player {payer_id} cannot afford mahriyeh {amount}",
                    required=amount,
                    balance=balance or 0,
                )

        # The status guard is the lock: a racing divorce loses and pays nothing.
        if not await marriage_repo.end(marriage.id, now):
            raise NotMarriedError("the marriage was already ended by a racing caller")

        children_count = await child_repo.count_by_marriage(marriage.id)
        divorce_repo.add(
            DivorceRecord(
                marriage_id=marriage.id,
                husband_player_id=marriage.husband_player_id,
                wife_player_id=marriage.wife_player_id,
                initiator_player_id=initiator_player_id,
                mahriyeh_amount=amount,
                mahriyeh_paid=paid,
                payer_player_id=payer_id if paid else None,
                payee_player_id=payee_id if paid else None,
                reason=reason,
                children_count=children_count,
            )
        )
        forced = reason == REASON_CHEATING
        for me, other in (
            (marriage.husband_player_id, marriage.wife_player_id),
            (marriage.wife_player_id, marriage.husband_player_id),
        ):
            await history_repo.add(
                player_id=me,
                event_type=EVENT_FORCED_DIVORCE if forced else EVENT_DIVORCE,
                marriage_id=marriage.id,
                other_player_id=other,
                amount=amount,
                quality_delta=0,
                note=(
                    "ازدواج به دلیل خیانت مکرر منقضی شد"
                    if forced
                    else "طلاق ثبت شد (مهریه پرداخت شد)"
                    if paid
                    else "طلاق ثبت شد (بدون مهریه)"
                ),
            )
            await player_repo.set_family_pointers(
                me, spouse_player_id=None, marriage_id=None, married_since=None
            )

        await session.commit()
        logger.info(
            "Divorce: marriage %s ended (initiator=%s mahriyeh=%s paid=%s waived=%s reason=%s)",
            marriage.id,
            initiator_player_id,
            amount,
            paid,
            waived,
            reason,
        )
        return DivorceResult(
            marriage_id=marriage.id,
            initiator_player_id=initiator_player_id,
            mahriyeh_amount=amount,
            mahriyeh_paid=paid,
            mahriyeh_waived=bool(waived),
            payer_player_id=payer_id if paid else None,
            payee_player_id=payee_id if paid else None,
            balance_after=balance_after,
            children_count=children_count,
            reason=reason,
            forced=forced,
        )

    # === Cheating ===============================================================

    async def cheat(self, player_id: int) -> CheatingResult:
        """Roll a hidden «خیانت» attempt.

        Two independent dice: whether the act itself went ahead, and —
        separately — whether it was found out. Only a discovery produces
        consequences, and those escalate per discovery (fine, relationship
        damage, reputation) until the final tier, which ends the marriage on
        the system's initiative with the cheater paying the Mahriyeh.

        Raises:
            NotMarriedError: Only married players can do this.
        """
        await self._expire_requests(_utc_now())
        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            marriage_repo = MarriageRepository(session)
            event_repo = RelationshipEventRepository(session)
            history_repo = FamilyHistoryRepository(session)

            marriage = await marriage_repo.get_active_for_player(player_id)
            if marriage is None:
                raise NotMarriedError("only married players can cheat")
            spouse_id = await marriage_repo.spouse_id_of(marriage, player_id)
            marriage_id = marriage.id
            quality_before = marriage.relationship_quality
            strikes_before = marriage.cheating_strikes

            discovered = self._roll() < constants.CHEATING_DISCOVERY_CHANCE
            success = self._roll() < constants.CHEATING_SUCCESS_CHANCE

            if discovered:
                fine, penalty, forced_tier = domain.cheating_consequence(strikes_before)
                quality_after = domain.apply_quality_delta(quality_before, -penalty)
                await marriage_repo.register_cheating(marriage_id, quality_after, player_id)

                fine_paid = False
                if fine > 0 and await player_repo.remove_money_if_enough(player_id, fine):
                    if not await player_repo.add_money(spouse_id, fine):
                        raise PlayerNotFoundError(f"spouse player_id={spouse_id} not found")
                    fine_paid = True

                note_self = (
                    "خیانتت فاش شد و جریمه شد" if fine_paid else "خیانتت فاش شد (جریمه قابل پرداخت نبود)"
                )
                await history_repo.add(
                    player_id=player_id,
                    event_type=EVENT_CHEATING_DISCOVERED,
                    marriage_id=marriage_id,
                    other_player_id=spouse_id,
                    amount=fine if fine_paid else 0,
                    quality_delta=-penalty,
                    social_penalty=1,
                    note=note_self,
                )
                await history_repo.add(
                    player_id=spouse_id,
                    event_type=EVENT_CHEATING_DISCOVERED,
                    marriage_id=marriage_id,
                    other_player_id=player_id,
                    amount=fine if fine_paid else 0,
                    quality_delta=-penalty,
                    social_penalty=1,
                    note="همسرت خیانت کرد و فاش شد",
                )
                event_repo.add(
                    RelationshipEvent(
                        marriage_id=marriage_id,
                        actor_player_id=player_id,
                        event_type=EV_CHEATING_DISCOVERED,
                        outcome=OUTCOME_NEUTRAL,
                        quality_before=quality_before,
                        quality_after=quality_after,
                        success=False,
                        discovered=True,
                        social_penalty=1,
                    )
                )
                fine_amount = fine
                strikes_after = strikes_before + 1
                social = 1
                # ``fine_paid`` must reflect what the wallet actually accepted,
                # not what was owed — a broke cheater pays nothing.
                paid_fine = fine_paid
            else:
                forced_tier = False
                fine_amount = 0
                paid_fine = False
                strikes_after = strikes_before
                social = 0
                quality_after = (
                    domain.apply_quality_delta(quality_before, -constants.CHEATING_SUCCESS_QUALITY_PENALTY)
                    if success
                    else quality_before
                )
                if success:
                    await marriage_repo.set_quality(marriage_id, quality_after)
                event_repo.add(
                    RelationshipEvent(
                        marriage_id=marriage_id,
                        actor_player_id=player_id,
                        event_type=EVENT_CHEATING_SUCCESS if success else EVENT_CHEATING_FAILED,
                        outcome=OUTCOME_NEUTRAL,
                        quality_before=quality_before,
                        quality_after=quality_after,
                        success=success,
                        discovered=False,
                    )
                )

            balance_after = await player_repo.get_money(player_id) or 0
            await session.commit()

        forced_divorce = False
        if discovered and forced_tier:
            # Third discovery: the marriage ends now, and the cheater pays.
            async with self._session_factory() as inner:
                try:
                    await self._end_marriage(
                        inner,
                        spouse_id,
                        reason=REASON_CHEATING,
                        payer_override=player_id,
                        force_unpayable=True,
                    )
                    forced_divorce = True
                except NotMarriedError:
                    forced_divorce = False

        return CheatingResult(
            success=success,
            discovered=discovered,
            quality_before=quality_before,
            quality_after=quality_after,
            social_penalty=social,
            strikes=strikes_after,
            fine_amount=fine_amount,
            fine_paid=paid_fine,
            forced_divorce=forced_divorce,
            spouse_notified=discovered,
            spouse_player_id=spouse_id,
            balance_after=balance_after,
        )

    def _roll(self) -> float:
        """One dice roll through the injectable RNG (tests force outcomes)."""
        return self._rng.random()

    # === Relationship / pregnancy ==============================================

    async def relationship(
        self, player_id: int, *, target_player_id: int | None = None
    ) -> RelationshipResult:
        """One «رابطه» event with the spouse — may start a pregnancy.

        ``target_player_id`` is whoever's message was replied to; when given it
        must be the spouse, which keeps the command a deliberate act between
        the two of them.

        Raises:
            NotMarriedError: The player is single.
            NotSpouseError: The reply was not addressed to the spouse.
        """
        await self._expire_requests(_utc_now())
        now = _utc_now()
        async with self._session_factory() as session:
            marriage_repo = MarriageRepository(session)
            child_repo = ChildRepository(session)
            event_repo = RelationshipEventRepository(session)
            history_repo = FamilyHistoryRepository(session)

            marriage = await marriage_repo.get_active_for_player(player_id)
            if marriage is None:
                raise NotMarriedError("only married players can have a relationship")
            spouse_id = await marriage_repo.spouse_id_of(marriage, player_id)
            if target_player_id is not None and target_player_id != spouse_id:
                raise NotSpouseError("reply to your spouse's message")

            quality_before = marriage.relationship_quality
            quality_after = domain.apply_quality_delta(
                quality_before, constants.RELATIONSHIP_TIME_QUALITY_BOOST
            )
            await marriage_repo.set_quality(marriage.id, quality_after)

            children = await child_repo.count_by_marriage(marriage.id)
            at_limit = children >= constants.MAX_CHILDREN_PER_MARRIAGE
            chance = domain.pregnancy_chance(quality_after)
            pregnant = (
                not at_limit
                and marriage.pregnant_due_at is None
                and self._roll() < chance
            )

            event = RelationshipEvent(
                marriage_id=marriage.id,
                actor_player_id=player_id,
                event_type=EVENT_RELATIONSHIP,
                outcome=OUTCOME_PREGNANCY if pregnant else OUTCOME_NEUTRAL,
                quality_before=quality_before,
                quality_after=quality_after,
                success=True,
            )
            event_repo.add(event)
            await session.flush()  # need event.id

            due_at = None
            if pregnant:
                due_at = now + timedelta(days=constants.PREGNANCY_DURATION_DAYS)
                event.pregnancy_due_at = due_at
                # Atomic claim: a racing pregnancy for the same couple loses.
                if not await marriage_repo.start_pregnancy(marriage.id, due_at, event.id):
                    pregnant = False
                    due_at = None
                    event.outcome = OUTCOME_NEUTRAL
                    event.pregnancy_due_at = None
                else:
                    for me, other in (
                        (marriage.husband_player_id, marriage.wife_player_id),
                        (marriage.wife_player_id, marriage.husband_player_id),
                    ):
                        await history_repo.add(
                            player_id=me,
                            event_type=EVENT_PREGNANCY,
                            marriage_id=marriage.id,
                            other_player_id=other,
                            note="انتظار ورود فرزند به خانواده",
                        )
            await session.commit()

        xp = await self._grant_xp(
            player_id, constants.RELATIONSHIP_XP, constants.RELATIONSHIP_XP_REASON
        )
        return RelationshipResult(
            quality_before=quality_before,
            quality_after=quality_after,
            success=True,
            pregnancy=pregnant,
            pregnancy_chance=chance,
            pregnancy_due_at=due_at,
            xp_granted=xp,
            blocked_max_children=at_limit,
        )
    # === Reads ==================================================================

    async def get_marriage(self, player_id: int) -> MarriageData | None:
        """The player's active marriage as a DTO (``None`` when single)."""
        async with self._session_factory() as session:
            marriage = await MarriageRepository(session).get_active_for_player(player_id)
            if marriage is None:
                return None
            children = await ChildRepository(session).count_by_marriage(marriage.id)
            return self._to_marriage_dto(marriage, children)

    async def get_family_info(self, player_id: int) -> FamilyInfoData:
        """Profile-facing summary: status, spouse, date, children, Mahriyeh.

        Married players get the live marriage row; single players get their
        divorce count as ``marriage_years == 0`` and ``married == False``.
        """
        async with self._session_factory() as session:
            player = await PlayerRepository(session).get_by_id(player_id)
            if player is None:
                raise PlayerNotFoundError(f"player_id={player_id} not found")
            marriage = await MarriageRepository(session).get_active_for_player(player_id)
            child_repo = ChildRepository(session)
            if marriage is None:
                return FamilyInfoData(
                    married=False,
                    spouse_player_id=None,
                    marriage_years=0,
                    children_count=await child_repo.count_by_player(player_id),
                    relationship_quality=0,
                    quality_label="",
                    mahriyeh_amount=0,
                    mahriyeh_paid=True,
                    cheating_strikes=0,
                )
            spouse_id = await MarriageRepository(session).spouse_id_of(marriage, player_id)
            names = await PlayerRepository(session).get_display_names({spouse_id} if spouse_id else set())
            telegrams = await PlayerRepository(session).get_telegram_user_ids({spouse_id} if spouse_id else set())
            children = await child_repo.count_by_marriage(marriage.id)
            started = _as_utc(marriage.started_at)
            years = max(0, (datetime.now(timezone.utc) - started).days // 365)
            return FamilyInfoData(
                married=True,
                spouse_player_id=spouse_id,
                spouse_name=names.get(spouse_id),
                spouse_telegram_user_id=telegrams.get(spouse_id),
                marriage_date=marriage.started_at,
                marriage_years=years,
                children_count=children,
                relationship_quality=marriage.relationship_quality,
                quality_label=domain.quality_label(marriage.relationship_quality),
                mahriyeh_amount=marriage.mahriyeh_amount,
                mahriyeh_paid=marriage.mahriyeh_paid,
                cheating_strikes=marriage.cheating_strikes,
                pregnant=marriage.pregnant_due_at is not None,
                marriage_id=marriage.id,
            )

    async def list_children(self, player_id: int) -> list[ChildData]:
        """All children of this player (across marriages), oldest first."""
        async with self._session_factory() as session:
            rows = await ChildRepository(session).list_by_player(player_id)
            now = datetime.now(timezone.utc)
            return [
                ChildData(
                    child_id=child.id,
                    marriage_id=child.marriage_id,
                    father_player_id=child.father_player_id,
                    mother_player_id=child.mother_player_id,
                    name=child.name,
                    birth_date=child.birth_date,
                    birth_year=child.birth_year,
                    age_years=max(
                        0,
                        current_iranian_year(now) - child.birth_year
                        if child.birth_year
                        else 0,
                    ),
                    growth_stage=child.growth_stage,
                )
                for child in rows
            ]

    async def get_family_history(
        self, player_id: int, limit: int = 20, offset: int = 0
    ) -> list[FamilyHistoryEntryData]:
        """The player's family timeline (marriages, divorces, births, ...)."""
        async with self._session_factory() as session:
            rows = await FamilyHistoryRepository(session).list_by_player(player_id, limit, offset)
            return [
                FamilyHistoryEntryData(
                    id=row.id,
                    event_type=row.event_type,
                    marriage_id=row.marriage_id,
                    other_player_id=row.other_player_id,
                    amount=row.amount,
                    quality_delta=row.quality_delta,
                    social_penalty=row.social_penalty,
                    note=row.note,
                    created_at=row.created_at,
                )
                for row in rows
            ]

    async def get_divorce_records(self, player_id: int) -> list[DivorceRecord]:
        """Raw divorce history rows (handler-side formatting only)."""
        async with self._session_factory() as session:
            return await DivorceRecordRepository(session).list_by_player(player_id)

    @staticmethod
    def _to_marriage_dto(marriage: Marriage, children_count: int) -> MarriageData:
        return MarriageData(
            marriage_id=marriage.id,
            husband_player_id=marriage.husband_player_id,
            wife_player_id=marriage.wife_player_id,
            started_at=marriage.started_at,
            relationship_quality=marriage.relationship_quality,
            quality_label=domain.quality_label(marriage.relationship_quality),
            mahriyeh_amount=marriage.mahriyeh_amount,
            mahriyeh_paid=marriage.mahriyeh_paid,
            cheating_strikes=marriage.cheating_strikes,
            social_penalties=marriage.social_penalties,
            children_count=children_count,
            pregnant=marriage.pregnant_due_at is not None,
            pregnancy_due_at=marriage.pregnant_due_at,
        )

    # === Shared helpers =========================================================

    async def _grant_xp(self, player_id: int, amount: int, reason: str) -> int:
        """Explicit XP grant through the existing LevelService (never implicit).

        Returns the amount actually granted (0 when no level service is wired,
        so bare unit tests of the domain rules still run).
        """
        if self._levels is None or amount <= 0:
            return 0
        result = await self._levels.add_xp(player_id, amount, reason)
        return int(result.xp_after - result.xp_before)


__all__ = [
    "AlreadyMarriedError",
    "CannotMarryYourselfError",
    "FamilyError",
    "FamilyService",
    "MahriyehUnaffordableError",
    "MarriageRequirementError",
    "NoPendingRequestError",
    "NotMarriedError",
    "NotSpouseError",
    "RequestExpiredError",
    "TargetAlreadyMarriedError",
    "CHILD_NAMES",
]
