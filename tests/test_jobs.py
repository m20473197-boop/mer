"""خر حمالی (jobs and income) tests — time-based salary system."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from app.core import constants
from app.database.models.player_job import PlayerJob
from app.database.repositories.job_repository import JobRepository
from app.services import ServiceRegistry
from app.services.job_service import (
    AlreadyHasJobError,
    JobNotFoundError,
    JobNotEnoughTimeError,
    JobRequirementError,
    JobService,
    NoJobError,
)


async def _set_started_at(services, player_id: int, minutes_ago: int) -> None:
    """Rewind the work-start clock so elapsed time is deterministic."""
    past = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    async with services.jobs._session_factory() as session:
        stmt = (
            update(PlayerJob)
            .where(PlayerJob.player_id == player_id)
            .values(started_at=past)
        )
        await session.execute(stmt, execution_options={"synchronize_session": False})
        await session.commit()


async def test_creating_jobs(services, db):
    # Ensure initial jobs are seeded
    jobs = await services.jobs.ensure_initial_jobs()
    assert len(jobs) == 6

    # Check via repository
    async with db.session_factory() as session:
        repo = JobRepository(session)
        all_jobs = await repo.list_all()
        names = {j.name for j in all_jobs}
        # The catalog is exactly the six required jobs, nothing left over.
        assert names == {
            constants.JOB_MASON_NAME,
            constants.JOB_RESTAURANT_NAME,
            constants.JOB_SALES_NAME,
            constants.JOB_COURIER_NAME,
            constants.JOB_SNAPP_NAME,
            constants.JOB_BANK_CLERK_NAME,
        }

    # Create custom job with hourly salary + employer
    async with db.session_factory() as session:
        repo = JobRepository(session)
        custom = await repo.create_job(
            name="برنامه‌نویس",
            description="تست",
            salary=500_000,
            hourly_salary=750_000,
            employer="استارتاپ زرین",
            cooldown=600,
            required_level=5,
        )
        await session.commit()
        assert custom.id is not None
        assert custom.name == "برنامه‌نویس"
        assert custom.salary == 500_000
        assert custom.hourly_salary == 750_000
        assert custom.employer == "استارتاپ زرین"


async def test_each_job_has_hourly_salary_and_employer(services):
    jobs = await services.jobs.get_available_jobs()
    assert len(jobs) == 6

    for job in jobs:
        assert job.hourly_salary > 0
        assert job.employer.strip() != ""

    salaries = {j.name: j.hourly_salary for j in jobs}
    employers = {j.name: j.employer for j in jobs}
    assert salaries[constants.JOB_MASON_NAME] == constants.JOB_MASON_HOURLY_SALARY
    assert salaries[constants.JOB_SALES_NAME] == constants.JOB_SALES_HOURLY_SALARY
    assert (
        salaries[constants.JOB_COURIER_NAME]
        == constants.JOB_COURIER_HOURLY_SALARY
    )
    assert employers[constants.JOB_MASON_NAME] == constants.JOB_MASON_EMPLOYER
    assert employers[constants.JOB_SALES_NAME] == constants.JOB_SALES_EMPLOYER
    assert (
        employers[constants.JOB_COURIER_NAME] == constants.JOB_COURIER_EMPLOYER
    )


async def test_applying_for_a_job_saves_start_time(services, register):
    player = await register(tg_id=8002)

    jobs = await services.jobs.get_available_jobs()
    mason_job = next(j for j in jobs if j.name == constants.JOB_MASON_NAME)

    result = await services.jobs.apply_job(player.player_id, mason_job.id)

    assert result.success is True
    assert result.job_id == mason_job.id
    assert result.job_name == mason_job.name
    assert result.employer == mason_job.employer
    assert result.hourly_salary == mason_job.hourly_salary

    # Check player job exists with a saved work start time
    player_job = await services.jobs.get_player_job(player.player_id)
    assert player_job is not None
    assert player_job.job_id == mason_job.id
    assert player_job.job_name == mason_job.name
    assert player_job.employer == mason_job.employer
    assert player_job.hourly_salary == mason_job.hourly_salary
    assert player_job.started_at is not None
    assert player_job.total_earnings == 0
    # Just started — no meaningful accrued salary yet.
    assert player_job.worked_minutes == 0
    assert player_job.accrued_salary == 0


async def test_preventing_multiple_active_jobs(services, register):
    player = await register(tg_id=8003)

    jobs = await services.jobs.get_available_jobs()
    mason = next(j for j in jobs if j.name == constants.JOB_MASON_NAME)
    sales = next(j for j in jobs if j.name == constants.JOB_SALES_NAME)

    # Need level 2 for sales, so level up player
    await services.levels.add_xp(player.player_id, 100, reason="level up")  # to level 2

    await services.jobs.apply_job(player.player_id, mason.id)

    # Try to apply for another job — should fail
    with pytest.raises(AlreadyHasJobError):
        await services.jobs.apply_job(player.player_id, sales.id)

    # Still has first job
    pj = await services.jobs.get_player_job(player.player_id)
    assert pj is not None
    assert pj.job_id == mason.id


async def test_checking_job_requirements(services, register):
    player = await register(tg_id=8004)  # level 1

    jobs = await services.jobs.get_available_jobs()
    courier = next(j for j in jobs if j.name == constants.JOB_COURIER_NAME)
    # Specialist requires level 3
    assert courier.required_level == 3

    with pytest.raises(JobRequirementError):
        await services.jobs.apply_job(player.player_id, courier.id)

    # Level up to 3
    # Level 1->2 needs 100, 2->3 needs 135, total 235
    await services.levels.add_xp(player.player_id, 235, reason="level up to 3")
    assert await services.levels.get_level(player.player_id) == 3

    # Now should succeed
    result = await services.jobs.apply_job(player.player_id, courier.id)
    assert result.success is True

    # Test non-existent job
    with pytest.raises(JobNotFoundError):
        await services.jobs.apply_job(player.player_id, 999999)


async def test_settlement_normal_payment(services, register, monkeypatch):
    player = await register(tg_id=8005)

    jobs = await services.jobs.get_available_jobs()
    mason = next(j for j in jobs if j.name == constants.JOB_MASON_NAME)
    await services.jobs.apply_job(player.player_id, mason.id)

    await _set_started_at(services, player.player_id, minutes_ago=120)  # 2 hours
    monkeypatch.setattr(services.jobs, "_roll_employer_event", lambda: ("normal", 0))

    result = await services.jobs.settle_with_employer(player.player_id)

    assert result.event_type == "normal"
    assert result.status == "paid"
    assert result.paid is True
    assert result.worked_minutes == 120
    assert result.hourly_salary == constants.JOB_MASON_HOURLY_SALARY
    assert result.gross_salary == constants.JOB_MASON_HOURLY_SALARY * 2  # 160_000
    assert result.final_amount == result.gross_salary
    assert result.bonus_amount == 0
    assert result.penalty_amount == 0

    # Paid through the wallet
    assert result.balance_after == result.gross_salary
    assert await services.money.get_balance(player.player_id) == result.gross_salary

    # Work timer reset
    pj = await services.jobs.get_player_job(player.player_id)
    assert pj is not None
    assert pj.worked_minutes == 0
    assert pj.total_earnings == result.gross_salary


async def test_settlement_bonus_payment(services, register, monkeypatch):
    player = await register(tg_id=8006)

    jobs = await services.jobs.get_available_jobs()
    mason = next(j for j in jobs if j.name == constants.JOB_MASON_NAME)
    await services.jobs.apply_job(player.player_id, mason.id)

    await _set_started_at(services, player.player_id, minutes_ago=60)  # 1 hour
    monkeypatch.setattr(services.jobs, "_roll_employer_event", lambda: ("bonus", 20))

    result = await services.jobs.settle_with_employer(player.player_id)

    gross = constants.JOB_MASON_HOURLY_SALARY  # 1 hour
    assert result.event_type == "bonus"
    assert result.bonus_percent == 20
    assert result.bonus_amount == gross * 20 // 100
    assert result.final_amount == gross + result.bonus_amount
    assert result.paid is True
    assert await services.money.get_balance(player.player_id) == result.final_amount


async def test_settlement_mistake_penalty(services, register, monkeypatch):
    player = await register(tg_id=8007)

    jobs = await services.jobs.get_available_jobs()
    mason = next(j for j in jobs if j.name == constants.JOB_MASON_NAME)
    await services.jobs.apply_job(player.player_id, mason.id)

    # 2 hours -> 160_000 gross, 30% penalty -> 112_000
    await _set_started_at(services, player.player_id, minutes_ago=120)
    monkeypatch.setattr(services.jobs, "_roll_employer_event", lambda: ("mistake", 30))

    result = await services.jobs.settle_with_employer(player.player_id)

    gross = constants.JOB_MASON_HOURLY_SALARY * 2  # 160_000
    assert result.event_type == "mistake"
    assert result.penalty_percent == 30
    assert result.penalty_amount == gross * 30 // 100  # 48_000
    assert result.final_amount == gross - result.penalty_amount  # 112_000
    assert result.paid is True
    assert await services.money.get_balance(player.player_id) == result.final_amount


async def test_settlement_delayed_payment_comes_later(services, register, monkeypatch):
    player = await register(tg_id=8008)

    jobs = await services.jobs.get_available_jobs()
    mason = next(j for j in jobs if j.name == constants.JOB_MASON_NAME)
    await services.jobs.apply_job(player.player_id, mason.id)

    await _set_started_at(services, player.player_id, minutes_ago=120)
    monkeypatch.setattr(services.jobs, "_roll_employer_event", lambda: ("delayed", 0))

    first = await services.jobs.settle_with_employer(player.player_id)

    assert first.event_type == "delayed"
    assert first.status == "delayed"
    assert first.paid is False
    assert first.final_amount == 0

    # No money received immediately
    assert await services.money.get_balance(player.player_id) == 0

    # Work timer NOT reset — the accrued hours are still pending
    pj = await services.jobs.get_player_job(player.player_id)
    assert pj is not None
    assert pj.worked_minutes >= 120

    # Later, the employer pays normally — the delayed work is included.
    await _set_started_at(services, player.player_id, minutes_ago=120)
    monkeypatch.setattr(services.jobs, "_roll_employer_event", lambda: ("normal", 0))
    second = await services.jobs.settle_with_employer(player.player_id)

    gross = constants.JOB_MASON_HOURLY_SALARY * 2
    assert second.paid is True
    assert second.final_amount == gross
    assert await services.money.get_balance(player.player_id) == gross


async def test_settlement_before_one_minute_is_rejected(services, register):
    player = await register(tg_id=8009)

    jobs = await services.jobs.get_available_jobs()
    mason = next(j for j in jobs if j.name == constants.JOB_MASON_NAME)
    await services.jobs.apply_job(player.player_id, mason.id)

    with pytest.raises(JobNotEnoughTimeError):
        await services.jobs.settle_with_employer(player.player_id)

    # Nothing was paid, timer still running from the start.
    assert await services.money.get_balance(player.player_id) == 0


async def test_employer_event_rolls_stay_in_bounds():
    # Exercise the real random roller with a seeded RNG.
    service = JobService(None, rng=random.Random(12345))  # type: ignore[arg-type]
    valid_types = {"normal", "bonus", "mistake", "delayed"}
    for _ in range(500):
        event_type, percent = service._roll_employer_event()
        assert event_type in valid_types
        if event_type == "mistake":
            assert (
                constants.MISTAKE_PENALTY_MIN_PERCENT
                <= percent
                <= constants.MISTAKE_PENALTY_MAX_PERCENT
            )
        elif event_type == "bonus":
            assert constants.BONUS_MIN_PERCENT <= percent <= constants.BONUS_MAX_PERCENT
        else:
            assert percent == 0


async def test_all_events_are_saved(services, register, monkeypatch):
    player = await register(tg_id=8010)

    jobs = await services.jobs.get_available_jobs()
    mason = next(j for j in jobs if j.name == constants.JOB_MASON_NAME)
    await services.jobs.apply_job(player.player_id, mason.id)

    rolls = [
        ("normal", 0),
        ("bonus", 15),
        ("mistake", 40),
        ("delayed", 0),
    ]
    for event, percent in rolls:
        await _set_started_at(services, player.player_id, minutes_ago=60)
        monkeypatch.setattr(
            services.jobs, "_roll_employer_event", lambda e=event, p=percent: (e, p)
        )
        await services.jobs.settle_with_employer(player.player_id)

    events = await services.jobs.get_salary_events(player.player_id, limit=20)
    # Newest first.
    assert len(events) == 4
    kinds = {e.event_type for e in events}
    assert kinds == {"normal", "bonus", "mistake", "delayed"}

    delayed = next(e for e in events if e.event_type == "delayed")
    assert delayed.status == "delayed"
    assert delayed.final_amount == 0
    assert delayed.gross_salary > 0

    mistake = next(e for e in events if e.event_type == "mistake")
    assert mistake.penalty_percent == 40
    assert mistake.penalty_amount > 0
    assert mistake.final_amount == mistake.gross_salary - mistake.penalty_amount

    bonus = next(e for e in events if e.event_type == "bonus")
    assert bonus.bonus_percent == 15
    assert bonus.final_amount == bonus.gross_salary + bonus.bonus_amount

    assert all(e.employer == mason.employer for e in events)


async def test_database_persistence(db, services, register):
    player = await register(tg_id=8009)

    jobs = await services.jobs.get_available_jobs()
    mason = next(j for j in jobs if j.name == constants.JOB_MASON_NAME)

    await services.jobs.apply_job(player.player_id, mason.id)
    await _set_started_at(services, player.player_id, minutes_ago=60)
    # Deterministic normal payment for this isolated test
    services.jobs._roll_employer_event = lambda: ("normal", 0)
    await services.jobs.settle_with_employer(player.player_id)

    # Simulate restart
    new_services = ServiceRegistry(db.session_factory)

    # Job should persist
    pj = await new_services.jobs.get_player_job(player.player_id)
    assert pj is not None
    assert pj.job_id == mason.id
    assert pj.total_earnings == constants.JOB_MASON_HOURLY_SALARY

    # Events should persist
    events = await new_services.jobs.get_salary_events(player.player_id)
    assert len(events) == 1
    assert events[0].event_type == "normal"
    assert events[0].gross_salary == constants.JOB_MASON_HOURLY_SALARY

    # Money should persist
    assert (
        await new_services.money.get_balance(player.player_id)
        == constants.JOB_MASON_HOURLY_SALARY
    )

    # Available jobs should still exist
    all_jobs = await new_services.jobs.get_available_jobs()
    assert len(all_jobs) >= 3


async def test_leave_job(services, register):
    player = await register(tg_id=8010)

    jobs = await services.jobs.get_available_jobs()
    mason = next(j for j in jobs if j.name == constants.JOB_MASON_NAME)

    await services.jobs.apply_job(player.player_id, mason.id)
    await _set_started_at(services, player.player_id, minutes_ago=60)
    services.jobs._roll_employer_event = lambda: ("normal", 0)
    await services.jobs.settle_with_employer(player.player_id)

    # Leave
    leave_result = await services.jobs.leave_job(player.player_id)
    assert leave_result.success is True
    assert leave_result.total_earnings == constants.JOB_MASON_HOURLY_SALARY

    # No job now
    assert await services.jobs.get_player_job(player.player_id) is None

    # Settle should fail
    with pytest.raises(NoJobError):
        await services.jobs.settle_with_employer(player.player_id)

    # Can apply again
    result = await services.jobs.apply_job(player.player_id, mason.id)
    assert result.success is True


async def test_job_messages_simple():
    from app.bot.messages.job import (
        job_applied_success,
        job_no_job,
        job_settle_too_early,
    )

    applied = job_applied_success("بنایی", "شرکت ساختمانی البرز", 80_000)
    assert "بنایی" in applied
    assert "موفقیت" in applied
    assert "شرکت ساختمانی البرز" in applied
    assert "تومان" in applied

    no_job = job_no_job()
    assert "کاری نداری" in no_job

    too_early = job_settle_too_early()
    assert "دقیقه" in too_early


# --- The «خر حمالی» catalog and the retirement of the old jobs ----------------


async def test_catalog_is_exactly_the_six_required_jobs(services):
    """Names, level gates and hourly rates as specified for the new system."""
    jobs = await services.jobs.get_available_jobs()
    catalog = {(j.name, j.required_level, j.hourly_salary) for j in jobs}
    assert catalog == {
        (constants.JOB_MASON_NAME, 1, 80_000),
        (constants.JOB_RESTAURANT_NAME, 1, 70_000),
        (constants.JOB_SALES_NAME, 2, 90_000),
        (constants.JOB_COURIER_NAME, 3, 120_000),
        (constants.JOB_SNAPP_NAME, 5, 160_000),
        (constants.JOB_BANK_CLERK_NAME, 8, 220_000),
    }

    # ``salary`` is the legacy per-action field and must mirror the hourly rate.
    by_name = {j.name: j for j in jobs}
    for name, (_, _, hourly) in ((j.name, (j.name, j.required_level, j.hourly_salary)) for j in jobs):
        assert by_name[name].salary == hourly

    # Every job is offerable: it has a description and an employer to settle with.
    for job in jobs:
        assert job.description.strip() != ""
        assert job.employer.strip() != ""


async def test_old_jobs_are_deactivated_but_never_deleted(services, db, register):
    """Legacy rows survive with their history; they just stop being offered."""
    # Emulate a database that still has the three old selectable jobs, one of
    # them created the way the pre-hourly schema did (hourly_salary == 0).
    async with db.session_factory() as session:
        repo = JobRepository(session)
        legacy = await repo.create_job(
            name="کارگر",
            description="کار ساده با درآمد کم",
            salary=50_000,
            hourly_salary=0,
            employer="",
            cooldown=300,
            required_level=1,
        )
        admin_job = await repo.create_job(
            name="برنامه‌نویس",
            description="ساخته‌ی ادمین",
            salary=300_000,
            hourly_salary=400_000,
            employer="استارتاپ زرین",
            cooldown=900,
            required_level=4,
        )
        await session.commit()

    jobs = await services.jobs.ensure_initial_jobs()

    assert legacy.name not in {j.name for j in jobs}
    assert admin_job.name in {j.name for j in jobs}  # admin jobs are never touched

    async with db.session_factory() as session:
        repo = JobRepository(session)
        retired = await repo.get_by_name("کارگر")
        assert retired is not None  # row kept, so history still resolves
        assert retired.is_active is False
        # backfilled from the legacy table instead of being left at zero pay
        expected_hourly, expected_employer = constants.JOB_LEGACY_COMPAT["کارگر"]
        assert retired.hourly_salary == expected_hourly
        assert retired.employer == expected_employer
        # …and the untouched values are the ones the old row already had.
        assert retired.salary == 50_000
        assert retired.required_level == 1
        admin_row = await repo.get_by_name("برنامه‌نویس")
        assert admin_row is not None and admin_row.is_active is True
        assert admin_row.hourly_salary == 400_000  # admin values survive a boot

    # Running it again changes nothing (idempotent boot-to-boot).
    again = await services.jobs.ensure_initial_jobs()
    assert [j.name for j in again] == [j.name for j in jobs]


async def test_retired_job_cannot_be_applied_for(services, db, register):
    player = await register(tg_id=8100)
    async with db.session_factory() as session:
        repo = JobRepository(session)
        retired = await repo.create_job(
            name="شغل قدیمی",
            description="-",
            salary=10_000,
            hourly_salary=10_000,
            employer="-",
            cooldown=300,
            required_level=1,
        )
        retired_id = retired.id  # snapshot: update_fields expires the instance
        await repo.update_fields(retired_id, is_active=False)
        await session.commit()

    with pytest.raises(JobNotFoundError):
        await services.jobs.apply_job(player.player_id, retired_id)


async def test_player_already_working_a_retired_job_still_gets_paid(services, db, register, monkeypatch):
    """Removing a job must not strand anyone who is mid-shift at it."""
    player = await register(tg_id=8101)
    jobs = await services.jobs.get_available_jobs()
    mason = next(j for j in jobs if j.name == constants.JOB_MASON_NAME)
    await services.jobs.apply_job(player.player_id, mason.id)
    await _set_started_at(services, player.player_id, minutes_ago=120)

    async with db.session_factory() as session:
        repo = JobRepository(session)
        await repo.update_fields(mason.id, is_active=False)
        await session.commit()

    monkeypatch.setattr(services.jobs, "_roll_employer_event", lambda: ("normal", 0))
    result = await services.jobs.settle_with_employer(player.player_id)

    assert result.paid is True
    assert result.final_amount == constants.JOB_MASON_HOURLY_SALARY * 2
    assert await services.money.get_balance(player.player_id) == result.final_amount


async def test_player_facing_texts_use_the_new_name(services, register):
    """Menus and messages speak «خر حمالی», and still render real job data."""
    from app.bot.keyboards import main_menu
    from app.bot.messages.job import jobs_list_text, jobs_menu_text, my_job_text

    assert constants.JOBS_SYSTEM_NAME == "خر حمالی"
    assert main_menu.BUTTON_JOBS == f"💼 {constants.JOBS_SYSTEM_NAME}"
    for label in (
        main_menu.BUTTON_JOBS,
        main_menu.BUTTON_JOBS_LIST,
        main_menu.BUTTON_JOBS_MY_JOB,
        main_menu.BUTTON_JOBS_LEAVE,
    ):
        assert "شغل" not in label
    assert constants.JOBS_SYSTEM_NAME in jobs_menu_text()

    jobs = await services.jobs.get_available_jobs()
    listing = jobs_list_text(jobs)
    assert "لیست شغل" not in listing
    for job in jobs:
        assert job.name in listing
        assert job.employer in listing
    assert "۸۰٬۰۰۰" in listing  # بنایی's hourly rate, in Persian digits

    # A player with no job and a player with one both read the new wording.
    player = await register(tg_id=8102)
    assert "کاری نداری" in my_job_text(None)
    mason = next(j for j in jobs if j.name == constants.JOB_MASON_NAME)
    await services.jobs.apply_job(player.player_id, mason.id)
    player_job = await services.jobs.get_player_job(player.player_id)
    text = my_job_text(player_job)
    assert f"کار فعلیت: {constants.JOB_MASON_NAME}" in text
    assert "🏢 صاحبکار:" in text  # settlement info is still shown
    assert "شغل" not in text


async def test_job_keyboards_show_the_new_name_and_catalog(services):
    """The actual Telegram keyboards: labels, per-job buttons, back button."""
    from app.bot.keyboards import callbacks
    from app.bot.keyboards.main_menu import build_jobs_list, build_jobs_menu

    menu_rows = build_jobs_menu().inline_keyboard
    labels = [button.text for row in menu_rows for button in row]
    assert "📋 لیست کارها" in labels
    assert "👔 کار من" in labels
    assert "🚪 ترک کار" in labels
    assert not any("شغل" in label for label in labels)

    jobs = await services.jobs.get_available_jobs()
    rows = build_jobs_list(jobs).inline_keyboard
    job_buttons = [row[0] for row in rows if row[0].callback_data.startswith(callbacks.JOBS_APPLY_PREFIX)]
    assert len(job_buttons) == 6
    texts = [button.text for button in job_buttons]
    assert any("بنایی" in t and "۸۰٬۰۰۰" in t and "لول ۱" in t for t in texts)
    assert any("کارمند بانک" in t and "۲۲۰٬۰۰۰" in t and "لول ۸" in t for t in texts)
    # the retired jobs are not on the keyboard at all
    assert not any("کارگر" in t or "متخصص" in t for t in texts)
    assert rows[-2][0].text == "🔙 بازگشت به منوی خر حمالی"


async def test_typing_the_new_command_renders_the_list(services, register, monkeypatch):
    """End-to-end through the real handler: text -> list message + buttons."""
    from datetime import datetime
    from unittest.mock import AsyncMock, MagicMock

    from telegram import Chat, Message, Update, User

    from app.bot.handlers import job as job_handlers

    await register(tg_id=8103)
    reply = AsyncMock()
    monkeypatch.setattr(Message, "reply_text", reply)
    context = MagicMock()
    context.application.bot_data = {"services": services}
    user = User(id=8103, first_name="Ali", is_bot=False)

    for text in ("خر حمالی", "مشاغل"):  # new name and the alias
        message = Message(
            message_id=1,
            date=datetime.now(),
            chat=Chat(id=user.id, type=Chat.PRIVATE),
            from_user=user,
            text=text,
        )
        reply.reset_mock()
        await job_handlers.jobs_text_handler(Update(update_id=1, message=message), context)

        sent = reply.await_args.kwargs["text"]
        markup = reply.await_args.kwargs["reply_markup"]
        assert constants.JOBS_SYSTEM_NAME in sent
        assert constants.JOB_MASON_NAME in sent and constants.JOB_BANK_CLERK_NAME in sent
        assert "کارگر" not in sent  # retired jobs are not on the list
        # six apply buttons + back-to-menu + back-to-main
        assert len(markup.inline_keyboard) == 8


def test_old_text_triggers_still_open_the_system():
    import re

    from app.bot.handlers import job as job_handlers

    for text in ("خر حمالی", "مشاغل"):
        assert re.match(job_handlers.JOBS_TEXT_PATTERN, text)
    for text in ("کار من", "شغل من"):
        assert re.match(job_handlers.MY_JOB_TEXT_PATTERN, text)
    assert not re.match(job_handlers.JOBS_TEXT_PATTERN, "خیانت")
