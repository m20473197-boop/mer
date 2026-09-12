"""Marriage and Family service tests — the whole feature, on the real stack.

Real ``Database`` + services + repositories (only Telegram is simulated
elsewhere). Randomness is forced by stubbing ``FamilyService._roll``, which is
the single dice entry point, so every chance-dependent rule (discovery,
pregnancy) is asserted exactly rather than statistically.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.database.models.child import Child
from app.database.models.divorce_record import DivorceRecord
from app.database.models.marriage import Marriage
from app.database.models.relationship_event import RelationshipEvent
from app.game.family import domain
from app.game.shared.errors import PlayerNotFoundError
from app.services.family_service import (
    AlreadyMarriedError,
    CannotMarryYourselfError,
    MahriyehUnaffordableError,
    MarriageRequirementError,
    NoPendingRequestError,
    NotMarriedError,
    NotSpouseError,
    RequestExpiredError,
    TargetAlreadyMarriedError,
)
from app.core import constants


# === Helpers =================================================================


async def setup_adult(services, tg_id: int, name: str, *, money: int = 50_000_000, level: int = 5):
    """A player who satisfies every marriage gate."""
    result = await services.players.register_or_get(
        telegram_user_id=tg_id, username=name[:20], display_name=name
    )
    await services.levels.set_level(result.player_id, level)
    if money:
        await services.money.add_money(result.player_id, money)
    return result


async def marry(services, a_id: int, b_id: int):
    """Propose from ``a_id`` to ``b_id`` and accept — returns MarriageResult."""
    await services.family.create_request(proposer_player_id=a_id, target_player_id=b_id)
    return await services.family.accept_request(b_id)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def force_rolls(service, values: list[float]):
    """Feed ``service._roll`` a fixed sequence (then repeat the last value)."""
    state = {"i": 0}

    def _roll() -> float:
        index = min(state["i"], len(values) - 1)
        state["i"] += 1
        return values[index]

    service._roll = _roll  # type: ignore[method-assign]


async def row_count(session_factory, model) -> int:
    async with session_factory() as session:
        return int((await session.execute(select(func.count(model.id)))).scalar_one() or 0)


async def marriage_row(services, player_id: int) -> Marriage:
    async with services.family._session_factory() as session:  # noqa: SLF001
        row = (
            await session.execute(
                select(Marriage).where(
                    (Marriage.husband_player_id == player_id)
                    | (Marriage.wife_player_id == player_id)
                )
            )
        ).scalars().one()
        return row


async def fast_forward_pregnancy(services, player_id: int, *, days: int = 8) -> None:
    """Move the due date into the past (same technique as the realestate tests)."""
    async with services.family._session_factory() as session:  # noqa: SLF001
        marriage = (
            await session.execute(
                select(Marriage).where(
                    (Marriage.husband_player_id == player_id)
                    | (Marriage.wife_player_id == player_id)
                )
            )
        ).scalars().one()
        marriage.pregnant_due_at = datetime.now(timezone.utc) - timedelta(days=days)
        await session.commit()


# === Marriage request ========================================================


async def test_marriage_request_is_created_and_visible_to_target(services, register):
    a = await setup_adult(services, 9001, "امیر")
    b = await setup_adult(services, 9002, "سارا")

    request = await services.family.create_request(
        proposer_player_id=a.player_id, target_player_id=b.player_id, message="سلام"
    )

    assert request.proposer_player_id == a.player_id
    assert request.target_player_id == b.player_id
    assert request.message == "سلام"
    assert request.mahriyeh_amount > 0

    # ``created_at`` is written by SQL ``func.now()`` (naive) while ``expires_at``
    # is written by Python (aware) — the same asymmetry ``_as_utc`` exists for.

    window = _aware(request.expires_at) - _aware(request.created_at)
    # ``created_at`` is stamped by SQL at INSERT time, so it trails the Python
    # ``expires_at`` base by a few microseconds — compare with a tolerance.
    assert abs(window - timedelta(hours=constants.MARRIAGE_REQUEST_EXPIRY_HOURS)) < timedelta(seconds=5)

    pending = await services.family.get_pending_request_for(b.player_id)
    assert pending is not None
    assert pending.request_id == request.request_id
    assert pending.proposer_name == "امیر"


async def test_cannot_propose_to_yourself(services):
    a = await setup_adult(services, 9003, "تنها")
    with pytest.raises(CannotMarryYourselfError):
        await services.family.create_request(proposer_player_id=a.player_id, target_player_id=a.player_id)


async def test_proposal_requires_min_level(services):
    a = await setup_adult(services, 9004, "کم‌لول", level=1)
    b = await setup_adult(services, 9005, "پُر‌لول")
    with pytest.raises(MarriageRequirementError) as exc:
        await services.family.create_request(proposer_player_id=a.player_id, target_player_id=b.player_id)
    assert exc.value.kind == "level"
    assert exc.value.required == constants.MARRIAGE_MIN_LEVEL


async def test_proposal_requires_min_money(services):
    a = await setup_adult(services, 9006, "بی‌پول", money=0)
    await services.levels.set_level(a.player_id, constants.MARRIAGE_MIN_LEVEL)
    b = await setup_adult(services, 9007, "ثروتمند")
    with pytest.raises(MarriageRequirementError) as exc:
        await services.family.create_request(proposer_player_id=a.player_id, target_player_id=b.player_id)
    assert exc.value.kind == "money"
    assert exc.value.required == constants.MARRIAGE_MIN_MONEY


async def test_unknown_player_proposal_raises(services):
    a = await setup_adult(services, 9008, "واقعی")
    with pytest.raises(PlayerNotFoundError):
        await services.family.create_request(proposer_player_id=a.player_id, target_player_id=424242)


async def test_only_one_open_request_per_target(services):
    a = await setup_adult(services, 9009, "اولین")
    c = await setup_adult(services, 9010, "دومین")
    b = await setup_adult(services, 9011, "هدف")

    await services.family.create_request(proposer_player_id=a.player_id, target_player_id=b.player_id)
    with pytest.raises(NoPendingRequestError):
        await services.family.create_request(proposer_player_id=c.player_id, target_player_id=b.player_id)


# === Accept / reject =========================================================


async def test_accept_creates_marriage_and_connects_both_profiles(services):
    a = await setup_adult(services, 9012, "همسر۱")
    b = await setup_adult(services, 9013, "همسر۲")

    result = await marry(services, a.player_id, b.player_id)

    assert result.husband_player_id == a.player_id
    assert result.wife_player_id == b.player_id
    assert await row_count(services.family._session_factory, Marriage) == 1  # noqa: SLF001

    async with services.family._session_factory() as session:  # noqa: SLF001
        from app.database.models.player import Player

        pa = (await session.execute(select(Player).where(Player.id == a.player_id))).scalars().one()
        pb = (await session.execute(select(Player).where(Player.id == b.player_id))).scalars().one()
    # Both directions are stored, plus the marriage date.
    assert pa.spouse_player_id == b.player_id and pb.spouse_player_id == a.player_id
    assert pa.marriage_id == result.marriage_id == pb.marriage_id
    assert pa.married_since is not None and pb.married_since is not None
    assert (pa.children_count, pb.children_count) == (0, 0)


async def test_accept_stores_mahriyeh_and_marriage_date(services):
    a = await setup_adult(services, 9014, "مرد")
    b = await setup_adult(services, 9015, "زن")

    request = await services.family.create_request(proposer_player_id=a.player_id, target_player_id=b.player_id)
    result = await services.family.accept_request(b.player_id)

    assert result.mahriyeh_amount == request.mahriyeh_amount
    marriage = await marriage_row(services, a.player_id)
    assert marriage.mahriyeh_amount == request.mahriyeh_amount
    assert marriage.mahriyeh_paid is False
    assert marriage.started_at is not None
    assert marriage.relationship_quality == constants.RELATIONSHIP_QUALITY_START


async def test_accept_grants_xp_to_both_spouses_through_level_service(services):
    a = await setup_adult(services, 9016, "ایکس‌پی۱")
    b = await setup_adult(services, 9017, "ایکس‌پی۲")

    result = await marry(services, a.player_id, b.player_id)

    assert result.xp_granted_husband == constants.MARRIAGE_XP
    assert result.xp_granted_wife == constants.MARRIAGE_XP
    reasons = {
        tx.reason
        for tx in await services.levels.get_xp_history(a.player_id)
    }
    assert constants.MARRIAGE_XP_REASON in reasons


async def test_double_accept_creates_exactly_one_marriage(services):
    a = await setup_adult(services, 9018, "یک")
    b = await setup_adult(services, 9019, "دو")
    await services.family.create_request(proposer_player_id=a.player_id, target_player_id=b.player_id)

    await services.family.accept_request(b.player_id)
    with pytest.raises(NoPendingRequestError):
        await services.family.accept_request(b.player_id)

    assert await row_count(services.family._session_factory, Marriage) == 1  # noqa: SLF001


async def test_reject_closes_the_request(services):
    a = await setup_adult(services, 9020, "خواستگار")
    b = await setup_adult(services, 9021, "مورد‌نظر")
    await services.family.create_request(proposer_player_id=a.player_id, target_player_id=b.player_id)

    await services.family.reject_request(b.player_id)

    assert await services.family.get_pending_request_for(b.player_id) is None
    assert await services.family.get_marriage(a.player_id) is None
    history = await services.family.get_family_history(a.player_id)
    assert any(entry.event_type == "request_rejected" for entry in history)


async def test_accepting_without_a_request_is_refused(services):
    a = await setup_adult(services, 9022, "تنها")
    with pytest.raises(NoPendingRequestError):
        await services.family.accept_request(a.player_id)


async def test_expired_request_cannot_be_accepted(services):
    a = await setup_adult(services, 9023, "صبر")
    b = await setup_adult(services, 9024, "تأخیر")
    await services.family.create_request(proposer_player_id=a.player_id, target_player_id=b.player_id)

    async with services.family._session_factory() as session:  # noqa: SLF001
        from app.database.models.marriage_request import MarriageRequest

        request = (await session.execute(select(MarriageRequest))).scalars().one()
        request.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await session.commit()

    with pytest.raises(RequestExpiredError):
        await services.family.accept_request(b.player_id)
    # The lazy settler turns it into history, once.
    settlement = await services.family.settle_due()
    assert settlement.requests_expired == 1
    assert await services.family.get_pending_request_for(b.player_id) is None


async def test_cancel_request_by_proposer(services):
    a = await setup_adult(services, 9025, "پشیمون")
    b = await setup_adult(services, 9026, "بی‌خبر")
    await services.family.create_request(proposer_player_id=a.player_id, target_player_id=b.player_id)

    await services.family.cancel_request(a.player_id)

    assert await services.family.get_pending_request_for(b.player_id) is None
    with pytest.raises(NoPendingRequestError):
        await services.family.cancel_request(a.player_id)


# === Married-player restrictions =============================================


async def test_married_player_cannot_marry_someone_else(services):
    a = await setup_adult(services, 9027, "شوهردار")
    b = await setup_adult(services, 9028, "همسر")
    c = await setup_adult(services, 9029, "سومین")
    await marry(services, a.player_id, b.player_id)

    with pytest.raises(AlreadyMarriedError) as exc:
        await services.family.create_request(proposer_player_id=a.player_id, target_player_id=c.player_id)
    assert exc.value.spouse_player_id == b.player_id


async def test_marrying_an_already_married_target_is_refused(services):
    a = await setup_adult(services, 9030, "آزاد")
    b = await setup_adult(services, 9031, "متأهل")
    c = await setup_adult(services, 9032, "همسرِ ب")
    await marry(services, b.player_id, c.player_id)

    with pytest.raises(TargetAlreadyMarriedError):
        await services.family.create_request(proposer_player_id=a.player_id, target_player_id=b.player_id)


@pytest.mark.parametrize(
    "method",
    ["cheat", "divorce"],
)
async def test_unmarried_players_are_blocked_from_family_actions(services, method):
    a = await setup_adult(services, 9033, "مجرد")
    with pytest.raises(NotMarriedError):
        await getattr(services.family, method)(a.player_id)


async def test_relationship_requires_marriage(services):
    a = await setup_adult(services, 9034, "مجرد۲")
    with pytest.raises(NotMarriedError):
        await services.family.relationship(a.player_id)


async def test_relationship_must_target_the_spouse(services):
    a = await setup_adult(services, 9035, "شوهر")
    b = await setup_adult(services, 9036, "زن")
    c = await setup_adult(services, 9037, "غریبه")
    await marry(services, a.player_id, b.player_id)

    with pytest.raises(NotSpouseError):
        await services.family.relationship(a.player_id, target_player_id=c.player_id)


# === Divorce and Mahriyeh ====================================================


async def test_divorce_pays_the_stored_mahriyeh_through_the_wallet(services):
    a = await setup_adult(services, 9038, "پرداخت‌کننده", money=50_000_000)
    b = await setup_adult(services, 9039, "دریافت‌کننده", money=1_000_000)
    result = await marry(services, a.player_id, b.player_id)

    divorce = await services.family.divorce(a.player_id)

    assert divorce.mahriyeh_amount == result.mahriyeh_amount
    assert divorce.mahriyeh_paid is True
    assert divorce.payer_player_id == a.player_id
    assert divorce.payee_player_id == b.player_id
    assert await services.money.get_balance(a.player_id) == 50_000_000 - result.mahriyeh_amount
    assert await services.money.get_balance(b.player_id) == 1_000_000 + result.mahriyeh_amount


async def test_divorce_blocked_when_payer_cannot_afford_mahriyeh(services):
    a = await setup_adult(services, 9040, "ته‌دست")
    b = await setup_adult(services, 9041, "همسر")
    result = await marry(services, a.player_id, b.player_id)
    # Spend everything *after* the wedding — the wallet gate is on proposing.
    await services.money.remove_money(a.player_id, await services.money.get_balance(a.player_id))

    with pytest.raises(MahriyehUnaffordableError) as exc:
        await services.family.divorce(a.player_id)

    assert exc.value.required == result.mahriyeh_amount
    assert exc.value.balance == 0
    # Nothing moved: still married, no divorce record, spouse unpaid.
    assert (await services.family.get_marriage(a.player_id)) is not None
    assert await row_count(services.family._session_factory, DivorceRecord) == 0  # noqa: SLF001
    assert await services.money.get_balance(b.player_id) == 50_000_000


async def test_divorce_ends_marriage_and_writes_history(services):
    a = await setup_adult(services, 9042, "مطلق۱")
    b = await setup_adult(services, 9043, "مطلق۲")
    marriage = await marry(services, a.player_id, b.player_id)

    await services.family.divorce(a.player_id)

    assert (await services.family.get_marriage(a.player_id)) is None
    assert (await services.family.get_marriage(b.player_id)) is None
    row = await marriage_row(services, a.player_id)
    assert row.status == "divorced" and row.ended_at is not None
    # Denormalized profile pointers are cleared on both sides.
    async with services.family._session_factory() as session:  # noqa: SLF001
        from app.database.models.player import Player

        pa = (await session.execute(select(Player).where(Player.id == a.player_id))).scalars().one()
        pb = (await session.execute(select(Player).where(Player.id == b.player_id))).scalars().one()
    assert pa.spouse_player_id is None and pb.spouse_player_id is None
    assert pa.marriage_id is None and pb.marriage_id is None

    records = await services.family.get_divorce_records(a.player_id)
    assert [r.marriage_id for r in records] == [marriage.marriage_id]
    assert records[0].mahriyeh_paid is True
    for player_id in (a.player_id, b.player_id):
        types = {e.event_type for e in await services.family.get_family_history(player_id)}
        assert {"marriage", "divorce"} <= types


async def test_divorce_is_not_double_paid(services):
    a = await setup_adult(services, 9044, "عجول")
    b = await setup_adult(services, 9045, "همسرش")
    await marry(services, a.player_id, b.player_id)

    await services.family.divorce(a.player_id)
    with pytest.raises(NotMarriedError):
        await services.family.divorce(a.player_id)
    assert await row_count(services.family._session_factory, DivorceRecord) == 0 + 1  # noqa: SLF001


async def test_wronged_spouse_divorces_free_after_a_discovery(services):
    a = await setup_adult(services, 9046, "خیانتکار")
    b = await setup_adult(services, 9047, "صاحب‌حق")
    marriage = await marry(services, a.player_id, b.player_id)

    force_rolls(services.family, [0.0, 0.0])  # discovered, and the act happened
    await services.family.cheat(a.player_id)

    balance_before = await services.money.get_balance(b.player_id)
    result = await services.family.divorce(b.player_id)

    assert result.mahriyeh_waived is True
    assert result.mahriyeh_paid is False
    assert await services.money.get_balance(b.player_id) == balance_before
    assert (await services.family.get_marriage(a.player_id)) is None
    del marriage


# === Cheating ================================================================


async def test_cheating_is_recorded_on_the_marriage(services):
    a = await setup_adult(services, 9048, "آروم")
    b = await setup_adult(services, 9049, "بی‌خبر")
    await marry(services, a.player_id, b.player_id)

    force_rolls(services.family, [0.99, 0.0])  # not discovered, act succeeded
    result = await services.family.cheat(a.player_id)

    assert result.discovered is False
    assert result.success is True
    assert result.spouse_notified is False
    assert result.quality_after < result.quality_before
    row = await marriage_row(services, a.player_id)
    assert row.cheating_strikes == 0  # only a discovery counts
    assert row.social_penalties == 0
    # No cheating entry may reach either spouse's timeline.
    for player_id in (a.player_id, b.player_id):
        types = {e.event_type for e in await services.family.get_family_history(player_id)}
        assert "cheating_discovered" not in types


async def test_cheating_failed_attempt_has_no_consequence(services):
    a = await setup_adult(services, 9050, "ترسو")
    b = await setup_adult(services, 9051, "همسر")
    await marry(services, a.player_id, b.player_id)

    force_rolls(services.family, [0.99, 0.99])  # not discovered, and it did not happen
    result = await services.family.cheat(a.player_id)

    assert (result.success, result.discovered) == (False, False)
    assert result.quality_after == result.quality_before


async def test_discovery_damages_relationship_and_charges_a_fine(services):
    a = await setup_adult(services, 9052, "لو‌رفته", money=50_000_000)
    b = await setup_adult(services, 9053, "همسرِ آگاه", money=0)
    await marry(services, a.player_id, b.player_id)

    force_rolls(services.family, [0.0, 0.0])  # discovered
    result = await services.family.cheat(a.player_id)

    fine, penalty, _ = domain.cheating_consequence(0)
    assert result.discovered and result.spouse_notified
    assert result.strikes == 1
    assert result.fine_amount == fine
    assert result.quality_after == result.quality_before - penalty
    assert await services.money.get_balance(a.player_id) == 50_000_000 - fine
    assert await services.money.get_balance(b.player_id) == fine  # spouse is compensated
    row = await marriage_row(services, a.player_id)
    assert (row.cheating_strikes, row.social_penalties) == (1, 1)
    assert row.cheater_player_id == a.player_id


async def test_spouse_is_notified_in_the_history(services):
    a = await setup_adult(services, 9054, "خائن")
    b = await setup_adult(services, 9055, "فریب‌خورده")
    await marry(services, a.player_id, b.player_id)

    force_rolls(services.family, [0.0, 0.0])
    await services.family.cheat(a.player_id)

    entries = await services.family.get_family_history(b.player_id)
    assert any(e.event_type == "cheating_discovered" for e in entries)


async def test_consequences_escalate_and_third_discovery_forces_divorce(services):
    a = await setup_adult(services, 9056, "مکرر", money=500_000_000)
    b = await setup_adult(services, 9057, "تحمل‌کرده", money=0)
    marriage = await marry(services, a.player_id, b.player_id)

    force_rolls(services.family, [0.0, 0.0])
    first = await services.family.cheat(a.player_id)
    second = await services.family.cheat(a.player_id)
    assert first.fine_amount < second.fine_amount  # each discovery costs more
    assert second.strikes == 2
    assert (await services.family.get_marriage(a.player_id)) is not None

    third = await services.family.cheat(a.player_id)
    assert third.strikes == 3
    assert third.forced_divorce is True
    assert (await services.family.get_marriage(a.player_id)) is None

    # The cheater pays the Mahriyeh even though the system ended the marriage.
    # The spouse also collected all three escalating fines (1M + 5M + 10M),
    # since a fine compensates the wronged partner rather than leaving the game.
    fines_paid = sum(tier[0] for tier in constants.CHEATING_CONSEQUENCES)
    # ``b`` started with nothing, so the whole balance is fines + Mahriyeh.
    assert await services.money.get_balance(b.player_id) == marriage.mahriyeh_amount + fines_paid
    record = (await services.family.get_divorce_records(b.player_id))[0]
    assert record.reason == "cheating" and record.payer_player_id == a.player_id


async def test_forced_divorce_happens_even_when_the_fine_is_unpayable(services):
    a = await setup_adult(services, 9058, "بی‌پول")
    b = await setup_adult(services, 9059, "همسر")
    await marry(services, a.player_id, b.player_id)
    # Broke *and* married: every fine and the Mahriyeh are now unaffordable.
    await services.money.remove_money(a.player_id, await services.money.get_balance(a.player_id))

    force_rolls(services.family, [0.0, 0.0])
    for _ in range(2):
        await services.family.cheat(a.player_id)
    third = await services.family.cheat(a.player_id)

    # Broke, so no fine was taken — but the marriage still ends, and an
    # unaffordable Mahriyeh cannot block it either.
    assert third.fine_paid is False
    assert third.forced_divorce is True
    assert (await services.family.get_marriage(a.player_id)) is None


async def test_discovery_is_gated_by_the_configured_chance(services):
    a = await setup_adult(services, 9060, "تصادفی")
    b = await setup_adult(services, 9061, "همسر")
    await marry(services, a.player_id, b.player_id)

    boundary = constants.CHEATING_DISCOVERY_CHANCE
    force_rolls(services.family, [boundary - 1e-9])
    assert (await services.family.cheat(a.player_id)).discovered is True
    force_rolls(services.family, [boundary + 1e-9])
    assert (await services.family.cheat(a.player_id)).discovered is False

    # The two dice are independent, so they must not sum past certainty.
    total = constants.CHEATING_SUCCESS_CHANCE + constants.CHEATING_DISCOVERY_CHANCE
    assert total <= 1.0


# === Relationship and pregnancy ==============================================


async def test_relationship_raises_quality_and_grants_xp(services):
    a = await setup_adult(services, 9062, "مهربان")
    b = await setup_adult(services, 9063, "همسر")
    await marry(services, a.player_id, b.player_id)

    force_rolls(services.family, [0.99])  # no pregnancy
    result = await services.family.relationship(a.player_id, target_player_id=b.player_id)

    assert result.quality_after == result.quality_before + constants.RELATIONSHIP_TIME_QUALITY_BOOST
    assert result.pregnancy is False
    assert result.xp_granted == constants.RELATIONSHIP_XP
    row = await marriage_row(services, a.player_id)
    assert row.relationship_quality == result.quality_after
    events = await row_count(services.family._session_factory, RelationshipEvent)  # noqa: SLF001
    assert events == 1


async def test_quality_boost_is_capped_at_the_maximum(services):
    a = await setup_adult(services, 9064, "عاشق")
    b = await setup_adult(services, 9065, "معشوق")
    await marry(services, a.player_id, b.player_id)
    async with services.family._session_factory() as session:  # noqa: SLF001
        marriage = (await session.execute(select(Marriage))).scalars().one()
        marriage.relationship_quality = constants.RELATIONSHIP_QUALITY_MAX
        await session.commit()

    force_rolls(services.family, [0.99])
    result = await services.family.relationship(a.player_id)
    assert result.quality_after == constants.RELATIONSHIP_QUALITY_MAX


async def test_pregnancy_is_pending_then_creates_the_child(services):
    a = await setup_adult(services, 9066, "پدر")
    b = await setup_adult(services, 9067, "مادر")
    marriage = await marry(services, a.player_id, b.player_id)

    force_rolls(services.family, [0.0])  # under the pregnancy chance
    event = await services.family.relationship(a.player_id)
    assert event.pregnancy is True
    assert event.pregnancy_due_at is not None
    assert (await services.family.get_marriage(a.player_id)).pregnant is True

    # Nothing is born before the due date.
    assert await services.family.settle_due() is not None
    assert await row_count(services.family._session_factory, Child) == 0  # noqa: SLF001

    await fast_forward_pregnancy(services, a.player_id)
    settlement = await services.family.settle_due()

    assert settlement.children_born == 1
    child = settlement.births[0]
    assert child.marriage_id == marriage.marriage_id
    assert child.father_player_id == a.player_id
    assert child.mother_player_id == b.player_id
    assert child.name and child.birth_year > 0 and child.growth_stage == "newborn"

    # Family information updated on both profiles.
    async with services.family._session_factory() as session:  # noqa: SLF001
        from app.database.models.player import Player

        pa = (await session.execute(select(Player).where(Player.id == a.player_id))).scalars().one()
        pb = (await session.execute(select(Player).where(Player.id == b.player_id))).scalars().one()
    assert (pa.children_count, pb.children_count) == (1, 1)
    assert [c.child_id for c in await services.family.list_children(a.player_id)] == [child.child_id]
    assert [c.child_id for c in await services.family.list_children(b.player_id)] == [child.child_id]


async def test_birth_grants_xp_once_to_each_parent(services):
    a = await setup_adult(services, 9068, "پدر۲")
    b = await setup_adult(services, 9069, "مادر۲")
    await marry(services, a.player_id, b.player_id)
    force_rolls(services.family, [0.0])
    await services.family.relationship(a.player_id)
    await fast_forward_pregnancy(services, a.player_id)

    await services.family.settle_due()
    again = await services.family.settle_due()  # already settled

    assert again.children_born == 0
    for player_id in (a.player_id, b.player_id):
        births = [t for t in await services.levels.get_xp_history(player_id) if t.reason == constants.BIRTH_XP_REASON]
        assert len(births) == 1
        assert births[0].amount == constants.BIRTH_XP


async def test_no_second_pregnancy_while_one_is_pending(services):
    a = await setup_adult(services, 9070, "عجله")
    b = await setup_adult(services, 9071, "همسر")
    await marry(services, a.player_id, b.player_id)

    force_rolls(services.family, [0.0])
    assert (await services.family.relationship(a.player_id)).pregnancy is True
    force_rolls(services.family, [0.0])
    assert (await services.family.relationship(a.player_id)).pregnancy is False


async def test_family_size_is_capped(services):
    a = await setup_adult(services, 9072, "پرجمعیت")
    b = await setup_adult(services, 9073, "همسر")
    await marry(services, a.player_id, b.player_id)

    for _ in range(constants.MAX_CHILDREN_PER_MARRIAGE):
        force_rolls(services.family, [0.0])
        await services.family.relationship(a.player_id)
        await fast_forward_pregnancy(services, a.player_id)
        await services.family.settle_due()

    assert len(await services.family.list_children(a.player_id)) == constants.MAX_CHILDREN_PER_MARRIAGE

    force_rolls(services.family, [0.0])
    result = await services.family.relationship(a.player_id)
    assert result.pregnancy is False
    assert result.blocked_max_children is True


# === Profile / information integration =======================================


async def test_profile_exposes_marriage_information(services):
    a = await setup_adult(services, 9074, "پروفایل‌دار")
    b = await setup_adult(services, 9075, "همسرِ پروفایل")
    marriage = await marry(services, a.player_id, b.player_id)

    profile = await services.players.get_profile(9074)

    assert profile.married is True
    assert profile.spouse_player_id == b.player_id
    assert profile.spouse_name == "همسرِ پروفایل"
    assert profile.marriage_date is not None
    assert profile.children_count == 0
    assert _aware(profile.marriage_date) == _aware(marriage.started_at)


async def test_family_info_reports_live_marriage_state(services):
    a = await setup_adult(services, 9076, "خانواده‌دار")
    b = await setup_adult(services, 9077, "همسرش")
    await marry(services, a.player_id, b.player_id)

    info = await services.family.get_family_info(a.player_id)

    assert info.married and info.spouse_name == "همسرش"
    assert info.children_count == 0
    assert info.mahriyeh_amount > 0 and info.mahriyeh_paid is False
    assert info.quality_label == domain.quality_label(constants.RELATIONSHIP_QUALITY_START)
    assert info.marriage_id is not None


async def test_family_info_for_a_single_player(services):
    a = await setup_adult(services, 9078, "مجرد۳")
    info = await services.family.get_family_info(a.player_id)
    assert info.married is False
    assert info.spouse_name is None
    assert info.marriage_date is None


# === Pure domain rules =======================================================


def test_mahriyeh_is_computed_from_level_wealth_and_market():
    base = constants.MARRIYEH_BASE
    small = domain.compute_mahriyeh(level=3, money=0)
    bigger = domain.compute_mahriyeh(level=9, money=0)
    rich = domain.compute_mahriyeh(level=3, money=100_000_000)

    assert small >= base and bigger > small and rich > small
    assert small % 100_000 == 0  # clean steps, integer money only
    assert domain.compute_mahriyeh(3, 0, market_factor=2.0) > small
    assert domain.compute_mahriyeh(999, 10**15) <= constants.MARRIYEH_MAX


def test_pregnancy_chance_rises_with_relationship_quality():
    cold = domain.pregnancy_chance(10)
    warm = domain.pregnancy_chance(100)
    assert 0.0 < cold < warm <= 1.0
    assert cold == pytest.approx(
        constants.RELATIONSHIP_PREGNANCY_BASE_CHANCE * (2.0 - constants.PREGNANCY_QUALITY_FACTOR_AT_100 + 0.1 * 1.2)
    )


def test_cheating_consequence_tiers_never_index_out_of_range():
    first = domain.cheating_consequence(0)
    last = domain.cheating_consequence(len(constants.CHEATING_CONSEQUENCES) - 1)
    beyond = domain.cheating_consequence(500)

    assert first[0] < last[0] and last[2] is True
    assert beyond == last
    assert domain.can_waive_mahriyeh(constants.CHEATING_WAIVER_STRIKES) is True
    assert domain.can_waive_mahriyeh(0) is False


def test_quality_math_is_bounded():
    assert domain.clamp_quality(-50) == constants.RELATIONSHIP_QUALITY_MIN
    assert domain.clamp_quality(10_000) == constants.RELATIONSHIP_QUALITY_MAX
    assert domain.apply_quality_delta(99, 25) == constants.RELATIONSHIP_QUALITY_MAX


# === Structure reserved for the next systems =================================


async def test_child_growth_and_expense_hooks_work(services):
    """The columns the growth / family-expense systems will use are live now."""
    from app.database.models.child import STAGE_ADULT, stage_for_age
    from app.database.repositories.child_repository import ChildRepository

    a = await setup_adult(services, 9080, "پدر۳")
    b = await setup_adult(services, 9081, "مادر۳")
    await marry(services, a.player_id, b.player_id)
    force_rolls(services.family, [0.0])
    await services.family.relationship(a.player_id)
    await fast_forward_pregnancy(services, a.player_id)
    child = (await services.family.settle_due()).births[0]

    assert stage_for_age(0) == "newborn"
    assert stage_for_age(5) == "infant"
    assert stage_for_age(10) == "child"
    assert stage_for_age(15) == "teen"
    assert stage_for_age(25) == STAGE_ADULT

    async with services.family._session_factory() as session:  # noqa: SLF001
        repo = ChildRepository(session)
        await repo.set_growth_stage(child.child_id, stage_for_age(15))
        await repo.add_expenses(child.child_id, 250_000)
        await repo.add_expenses(child.child_id, 100_000)
        await session.commit()

    async with services.family._session_factory() as session:  # noqa: SLF001
        row = await session.get(Child, child.child_id)
    assert row.growth_stage == "teen"
    assert row.expenses_total == 350_000


# === Schema / migration ======================================================


async def test_family_tables_are_created(db):
    async with db.engine.begin() as conn:
        names = {
            row[0]
            for row in (await conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
        }
    assert {
        "marriages",
        "marriage_requests",
        "divorce_records",
        "children",
        "relationship_events",
        "family_history",
    } <= names


async def test_legacy_databases_gain_family_columns_without_losing_rows(tmp_path):
    """Re-running create_all on a DB without the family tables is additive."""
    from app.database.database import Database

    fresh = Database(f"sqlite+aiosqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    await fresh.create_all()
    async with fresh.session_factory() as session:
        from app.database.models.player import Player

        session.add(
            Player(telegram_user_id=123, display_name="قدیمی", level=1, xp=0, money=0)
        )
        await session.commit()
    await fresh.dispose()

    again = Database(f"sqlite+aiosqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    await again.create_all()
    async with again.session_factory() as session:
        player = (
            await session.execute(select(__import__("app.database.models.player", fromlist=["Player"]).Player))
        ).scalars().one()
        assert player.display_name == "قدیمی"
        assert player.children_count == 0 and player.spouse_player_id is None
    await again.dispose()
