"""Job system handlers — menu, apply, settle, leave, history.

All business logic in JobService, handlers only translate Telegram -> service.
"""

from __future__ import annotations

import logging
import re

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.context import get_services
from app.bot.handlers.guards import requires_feature
from app.bot.keyboards import build_jobs_list, build_jobs_menu, callbacks
from app.bot.messages import job as job_messages
from app.bot.messages import errors as error_messages
from app.core import constants
from app.game.shared.errors import PlayerNotFoundError
from app.services.job_service import (
    AlreadyHasJobError,
    JobNotFoundError,
    JobNotEnoughTimeError,
    JobRequirementError,
    NoJobError,
)

logger = logging.getLogger(__name__)

# Text triggers. The system is now called «خر حمالی», but the old «مشاغل» /
# «شغل من» wording keeps working so players who typed it for months are not
# stranded by the rename.
JOBS_TEXT_TRIGGERS: tuple[str, ...] = (
    constants.JOBS_TEXT_TRIGGER,
    constants.JOBS_TEXT_TRIGGER_LEGACY,
)
MY_JOB_TEXT_TRIGGERS: tuple[str, ...] = (
    constants.MY_JOB_TEXT_TRIGGER,
    constants.MY_JOB_TEXT_TRIGGER_LEGACY,
)
LEAVE_JOB_TEXT_TRIGGER: str = constants.LEAVE_JOB_TEXT_TRIGGER
APPLY_JOB_TEXT_TRIGGER: str = constants.APPLY_JOB_TEXT_TRIGGER


def _trigger_pattern(triggers: tuple[str, ...], suffix: str = "") -> str:
    """Regex matching any of ``triggers`` (optionally followed by arguments)."""
    options = "|".join(re.escape(trigger) for trigger in triggers)
    return f"^({options}){suffix}$"


JOBS_TEXT_PATTERN: str = _trigger_pattern(JOBS_TEXT_TRIGGERS)
MY_JOB_TEXT_PATTERN: str = _trigger_pattern(MY_JOB_TEXT_TRIGGERS)
LEAVE_JOB_TEXT_PATTERN: str = _trigger_pattern((LEAVE_JOB_TEXT_TRIGGER,))
APPLY_JOB_TEXT_PATTERN: str = _trigger_pattern((APPLY_JOB_TEXT_TRIGGER,), ".*")


async def _resolve_player_id(services, tg_id: int) -> int | None:
    """Map a Telegram user id to the internal player id (None if unregistered)."""
    from app.database.repositories.player_repository import PlayerRepository

    async with services.players._session_factory() as session:  # type: ignore
        repo = PlayerRepository(session)
        player = await repo.get_by_telegram_user_id(tg_id)
        return player.id if player is not None else None


@requires_feature("jobs")
async def show_jobs_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.JOBS_MENU:
        return
    await query.answer()

    await query.edit_message_text(
        text=job_messages.jobs_menu_text(), reply_markup=build_jobs_menu()
    )


@requires_feature("jobs")
async def show_jobs_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.JOBS_LIST:
        return
    await query.answer()

    services = get_services(context)
    jobs = await services.jobs.get_available_jobs()

    await query.edit_message_text(
        text=job_messages.jobs_list_text(jobs), reply_markup=build_jobs_list(jobs)
    )


@requires_feature("jobs")
async def show_my_job(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.JOBS_MY_JOB:
        return
    await query.answer()

    services = get_services(context)
    tg_id = query.from_user.id
    player_id = await _resolve_player_id(services, tg_id)
    if player_id is None:
        await query.edit_message_text(
            text=error_messages.NOT_REGISTERED, reply_markup=None
        )
        return

    try:
        player_job = await services.jobs.get_player_job(player_id)
    except PlayerNotFoundError:
        await query.edit_message_text(
            text=error_messages.NOT_REGISTERED, reply_markup=None
        )
        return

    await query.edit_message_text(
        text=job_messages.my_job_text(player_job), reply_markup=build_jobs_menu()
    )


@requires_feature("jobs")
async def settle_job_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """💰 تسویه با صاحبکار — settle the accrued salary."""
    query = update.callback_query
    if query is None or query.data != callbacks.JOBS_SETTLE:
        return
    await query.answer()

    services = get_services(context)
    tg_id = query.from_user.id
    player_id = await _resolve_player_id(services, tg_id)
    if player_id is None:
        await query.edit_message_text(
            text=error_messages.NOT_REGISTERED, reply_markup=None
        )
        return

    try:
        result = await services.jobs.settle_with_employer(player_id)
        await query.edit_message_text(
            text=job_messages.settlement_text(result),
            reply_markup=build_jobs_menu(),
        )
    except NoJobError:
        await query.edit_message_text(
            text=job_messages.job_no_job(), reply_markup=build_jobs_menu()
        )
    except JobNotEnoughTimeError:
        await query.edit_message_text(
            text=job_messages.job_settle_too_early(), reply_markup=build_jobs_menu()
        )
    except Exception as exc:
        logger.error("settle_job_callback failed for %s", tg_id, exc_info=exc)
        await query.edit_message_text(
            text=error_messages.GENERIC, reply_markup=build_jobs_menu()
        )


@requires_feature("jobs")
async def leave_job_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.JOBS_LEAVE:
        return
    await query.answer()

    services = get_services(context)
    tg_id = query.from_user.id
    player_id = await _resolve_player_id(services, tg_id)
    if player_id is None:
        await query.edit_message_text(
            text=error_messages.NOT_REGISTERED, reply_markup=None
        )
        return

    try:
        result = await services.jobs.leave_job(player_id)
        await query.edit_message_text(
            text=job_messages.job_leave_success(result.job_name, result.total_earnings),
            reply_markup=build_jobs_menu(),
        )
    except NoJobError:
        await query.edit_message_text(
            text=job_messages.job_no_job(), reply_markup=build_jobs_menu()
        )
    except Exception as exc:
        logger.error("leave_job_callback failed for %s", tg_id, exc_info=exc)
        await query.edit_message_text(
            text=error_messages.GENERIC, reply_markup=build_jobs_menu()
        )


@requires_feature("jobs")
async def apply_job_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.JOBS_APPLY_PREFIX):
        return
    await query.answer()

    services = get_services(context)
    tg_id = query.from_user.id

    # Extract job_id
    try:
        job_id_str = query.data[len(callbacks.JOBS_APPLY_PREFIX) :]
        job_id = int(job_id_str)
    except ValueError:
        await query.answer(text="شناسه کار نامعتبر است.", show_alert=True)
        return

    player_id = await _resolve_player_id(services, tg_id)
    if player_id is None:
        await query.edit_message_text(
            text=error_messages.NOT_REGISTERED, reply_markup=None
        )
        return

    try:
        result = await services.jobs.apply_job(player_id, job_id)
        await query.edit_message_text(
            text=job_messages.job_applied_success(
                result.job_name, result.employer, result.hourly_salary
            ),
            reply_markup=build_jobs_menu(),
        )
    except JobNotFoundError:
        await query.edit_message_text(
            text=job_messages.job_not_found(), reply_markup=build_jobs_menu()
        )
    except JobRequirementError as exc:
        await query.edit_message_text(
            text=job_messages.job_apply_error(str(exc)), reply_markup=build_jobs_menu()
        )
    except AlreadyHasJobError as exc:
        await query.edit_message_text(
            text=job_messages.job_apply_error(str(exc)), reply_markup=build_jobs_menu()
        )
    except Exception as exc:
        logger.error("apply_job_callback failed for %s", tg_id, exc_info=exc)
        await query.edit_message_text(
            text=error_messages.GENERIC, reply_markup=build_jobs_menu()
        )


@requires_feature("jobs")
async def show_job_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.JOBS_HISTORY:
        return
    await query.answer()

    services = get_services(context)
    tg_id = query.from_user.id
    player_id = await _resolve_player_id(services, tg_id)
    if player_id is None:
        await query.edit_message_text(
            text=error_messages.NOT_REGISTERED, reply_markup=None
        )
        return

    try:
        events = await services.jobs.get_salary_events(player_id, limit=10)
        await query.edit_message_text(
            text=job_messages.salary_events_text(events),
            reply_markup=build_jobs_menu(),
        )
    except Exception as exc:
        logger.error("show_job_history failed for %s", tg_id, exc_info=exc)
        await query.edit_message_text(
            text=error_messages.GENERIC, reply_markup=build_jobs_menu()
        )


# --- Persian command handlers ----------------------------------------


@requires_feature("jobs")
async def jobs_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle 'خر حمالی' — show available jobs."""
    if update.message is None or update.effective_user is None:
        return
    if (update.message.text or "").strip() not in JOBS_TEXT_TRIGGERS:
        return

    services = get_services(context)
    tg_id = update.effective_user.id
    player_id = await _resolve_player_id(services, tg_id)
    if player_id is None:
        await update.message.reply_text(error_messages.NOT_REGISTERED)
        return

    try:
        jobs = await services.jobs.get_available_jobs()
        await update.message.reply_text(
            text=job_messages.jobs_list_text(jobs),
            reply_markup=build_jobs_list(jobs),
        )
    except Exception as exc:
        logger.error("jobs_text_handler failed for %s", tg_id, exc_info=exc)
        await update.message.reply_text(error_messages.GENERIC)


@requires_feature("jobs")
async def my_job_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle 'کار من' — show current job."""
    if update.message is None or update.effective_user is None:
        return
    if (update.message.text or "").strip() not in MY_JOB_TEXT_TRIGGERS:
        return

    services = get_services(context)
    tg_id = update.effective_user.id
    player_id = await _resolve_player_id(services, tg_id)
    if player_id is None:
        await update.message.reply_text(error_messages.NOT_REGISTERED)
        return

    try:
        pj = await services.jobs.get_player_job(player_id)
        await update.message.reply_text(
            text=job_messages.my_job_text(pj), reply_markup=build_jobs_menu()
        )
    except Exception as exc:
        logger.error("my_job_text_handler failed for %s", tg_id, exc_info=exc)
        await update.message.reply_text(error_messages.GENERIC)


@requires_feature("jobs")
async def leave_job_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle 'ترک کار' — leave current job."""
    if update.message is None or update.effective_user is None:
        return
    if (update.message.text or "").strip() != LEAVE_JOB_TEXT_TRIGGER:
        return

    services = get_services(context)
    tg_id = update.effective_user.id
    player_id = await _resolve_player_id(services, tg_id)
    if player_id is None:
        await update.message.reply_text(error_messages.NOT_REGISTERED)
        return

    try:
        result = await services.jobs.leave_job(player_id)
        await update.message.reply_text(
            text=job_messages.job_leave_success(result.job_name, result.total_earnings),
            reply_markup=build_jobs_menu(),
        )
    except NoJobError:
        await update.message.reply_text(job_messages.job_no_job())
    except Exception as exc:
        logger.error("leave_job_text_handler failed for %s", tg_id, exc_info=exc)
        await update.message.reply_text(error_messages.GENERIC)


@requires_feature("jobs")
async def apply_job_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle 'استخدام' — apply for a job.

    Supports:
    - 'استخدام' alone -> shows jobs list
    - 'استخدام <job_name>' or 'استخدام <job_id>' -> tries to apply directly
    """
    if update.message is None or update.effective_user is None:
        return

    raw_text = (update.message.text or "").strip()
    if not raw_text.startswith(APPLY_JOB_TEXT_TRIGGER):
        return

    services = get_services(context)
    tg_id = update.effective_user.id
    player_id = await _resolve_player_id(services, tg_id)
    if player_id is None:
        await update.message.reply_text(error_messages.NOT_REGISTERED)
        return

    # Parse argument after 'استخدام'
    arg = raw_text[len(APPLY_JOB_TEXT_TRIGGER) :].strip()

    if not arg:
        # No arg — show jobs list
        try:
            jobs = await services.jobs.get_available_jobs()
            await update.message.reply_text(
                text=job_messages.jobs_list_text(jobs),
                reply_markup=build_jobs_list(jobs),
            )
        except Exception as exc:
            logger.error("apply_job_text_handler list failed for %s", tg_id, exc_info=exc)
            await update.message.reply_text(error_messages.GENERIC)
        return

    # Try to find job by id or name
    try:
        jobs = await services.jobs.get_available_jobs()
        target_job = None

        # Try by id
        try:
            job_id = int(arg)
            target_job = next((j for j in jobs if j.id == job_id), None)
        except ValueError:
            pass

        # Try by exact name
        if target_job is None:
            target_job = next((j for j in jobs if j.name == arg), None)

        # Try by contains
        if target_job is None:
            for j in jobs:
                if arg in j.name:
                    target_job = j
                    break

        if target_job is None:
            await update.message.reply_text(job_messages.job_not_found())
            return

        result = await services.jobs.apply_job(player_id, target_job.id)
        await update.message.reply_text(
            text=job_messages.job_applied_success(
                result.job_name, result.employer, result.hourly_salary
            ),
            reply_markup=build_jobs_menu(),
        )
    except JobNotFoundError:
        await update.message.reply_text(job_messages.job_not_found())
    except JobRequirementError as exc:
        await update.message.reply_text(job_messages.job_apply_error(str(exc)))
    except AlreadyHasJobError as exc:
        await update.message.reply_text(job_messages.job_apply_error(str(exc)))
    except Exception as exc:
        logger.error("apply_job_text_handler failed for %s", tg_id, exc_info=exc)
        await update.message.reply_text(error_messages.GENERIC)
