"""Marriage and Family handlers — **commands only** (no menus, no buttons).

Everything the family system does is triggered by a Persian text message, in
the same style as the existing «مشاغل» / «خانه» triggers. Two of them are
reply-commands (they act on the message you answer to), which is how the bot
learns *who* you are proposing to or spending time with:

* «ازدواج»  — reply to the target player's message → opens a request
* «رابطه»   — reply to your spouse's message       → relationship event

Accepting and rejecting are also plain commands («قبول» / «رد»), so the whole
system stays inside the existing handler structure without adding a single
button. Cheating («خیانت») is deliberately answered **privately**: in a group
chat the reply is replaced by a direct message, so nothing leaks into the
public thread.

Handlers translate Telegram → service calls and back; all rules live in
``FamilyService``.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.bot.context import get_services
from app.bot.messages import errors as error_messages
from app.bot.messages import family as family_messages
from app.core import constants
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

logger = logging.getLogger(__name__)

# ``telegram.Chat.type`` values that are one-to-one, where answering in place
# is private by definition.
PRIVATE_CHAT_TYPES: frozenset[str] = frozenset({"private", "sender"})


# === Plumbing ================================================================


async def _player_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    services = get_services(context)
    user = update.effective_user
    if user is None:
        return None
    return await services.players.resolve_player_id(user.id)


async def _reply_or_hide(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
) -> None:
    """Answer in private chats; in groups fall back to a private DM.

    «خیانت» must not echo into a group thread — the attempt is hidden, so a
    group update is answered by messaging the player directly instead.
    """
    message = update.message
    if message is None:
        return
    if message.chat.type in PRIVATE_CHAT_TYPES:
        await message.reply_text(text)
        return
    if update.effective_user is None:
        return
    try:
        await context.bot.send_message(chat_id=update.effective_user.id, text=text)
    except BadRequest as exc:
        logger.debug("Could not deliver private family notice: %s", exc)
        # Nothing private is possible (user blocked the bot) — say as little as
        # we can publicly rather than leaking the content of the message.
        await message.reply_text("🤫 پیام خصوصی برات ارسال شد.")


async def _notify(context: ContextTypes.DEFAULT_TYPE, telegram_user_id: int | None, text: str) -> None:
    """Send a private notice, tolerating users who blocked the bot."""
    if telegram_user_id is None:
        return
    try:
        await context.bot.send_message(chat_id=telegram_user_id, text=text)
    except BadRequest as exc:
        logger.debug("Private family notice not deliverable: %s", exc)


async def _settle_and_announce(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run the lazy settler and DM the parents of any baby that just arrived.

    Marriages settle on read (same strategy as construction/renovation), so no
    scheduler is needed: opening a family screen completes whatever is due.
    """
    services = get_services(context)
    result = await services.family.settle_due()
    for child in result.births:
        for parent_id in (child.father_player_id, child.mother_player_id):
            tg_id = await services.players.get_telegram_user_id(parent_id)
            name = await services.players.display_name_of(parent_id)
            await _notify(context, tg_id, family_messages.child_birth_notice(child, name or ""))


# === Marriage ================================================================


async def marriage_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«ازدواج» as a reply to another player's message → create a request."""
    message = update.message
    if message is None:
        return
    await _settle_and_announce(update, context)

    player_id = await _player_id(update, context)
    if player_id is None:
        await message.reply_text(error_messages.NOT_REGISTERED)
        return

    replied = message.reply_to_message
    if replied is None or replied.from_user is None or replied.from_user.is_bot:
        await message.reply_text(family_messages.marriage_needs_reply())
        return

    services = get_services(context)
    target_player_id = await services.players.resolve_player_id(replied.from_user.id)
    if target_player_id is None:
        await message.reply_text(family_messages.not_registered_reply())
        return

    note = (message.text or "").strip()
    # Everything after the trigger word is kept as the proposal note.
    trigger = constants.MARRIAGE_TRIGGER
    if note.lower().startswith(trigger.lower()):
        note = note[len(trigger):].strip()

    try:
        request = await services.family.create_request(
            proposer_player_id=player_id, target_player_id=target_player_id, message=note
        )
    except CannotMarryYourselfError:
        await message.reply_text(family_messages.cannot_marry_yourself())
        return
    except AlreadyMarriedError as exc:
        name = await services.players.display_name_of(exc.spouse_player_id or 0)
        await message.reply_text(family_messages.already_married(name or "همسرت"))
        return
    except TargetAlreadyMarriedError:
        name = replied.from_user.first_name or "آن بازیکن"
        await message.reply_text(family_messages.target_already_married(name))
        return
    except MarriageRequirementError as exc:
        if exc.kind == "money":
            await message.reply_text(family_messages.requirement_money(exc.actual))
        else:
            await message.reply_text(family_messages.requirement_level(exc.actual))
        return
    except NoPendingRequestError:
        await message.reply_text(
            "📨 تو یا طرف مقابل الان یه درخواست ازدواج باز دارید؛ اول همون رو مشخص کن."
        )
        return
    except PlayerNotFoundError:
        await message.reply_text(error_messages.NOT_REGISTERED)
        return

    target_name = replied.from_user.first_name or "طرف مقابل"
    await message.reply_text(family_messages.marriage_request_created(request, target_name))

    target_tg = await services.players.get_telegram_user_id(target_player_id)
    await _notify(
        context,
        target_tg,
        family_messages.marriage_request_incoming(request, request.proposer_name),
    )


async def accept_marriage_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«قبول» — accept the open request addressed to you."""
    message = update.message
    if message is None:
        return
    await _settle_and_announce(update, context)

    player_id = await _player_id(update, context)
    if player_id is None:
        await message.reply_text(error_messages.NOT_REGISTERED)
        return

    services = get_services(context)
    try:
        result = await services.family.accept_request(player_id)
    except (NoPendingRequestError, RequestExpiredError):
        await message.reply_text(family_messages.marriage_already_answered())
        return
    except AlreadyMarriedError:
        await message.reply_text(family_messages.already_married("همسرت"))
        return
    except PlayerNotFoundError:
        await message.reply_text(error_messages.NOT_REGISTERED)
        return

    await message.reply_text(family_messages.marriage_accepted(result))

    proposer_tg = await services.players.get_telegram_user_id(result.husband_player_id)
    if proposer_tg != message.chat.id:
        await _notify(
            context,
            proposer_tg,
            f"💍 {result.wife_name} درخواست ازدواجت رو قبول کرد! زندگی مشترکتون شروع شد 🎉",
        )


async def reject_marriage_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«رد» — reject the open request addressed to you."""
    message = update.message
    if message is None:
        return
    player_id = await _player_id(update, context)
    if player_id is None:
        await message.reply_text(error_messages.NOT_REGISTERED)
        return

    services = get_services(context)
    try:
        request = await services.family.reject_request(player_id)
    except NoPendingRequestError:
        await message.reply_text("🤷 درخواست ازدواج بازی برای «رد» کردن نداری.")
        return

    await message.reply_text("🚫 درخواست رد شد.")
    proposer_tg = await services.players.get_telegram_user_id(request.proposer_player_id)
    await _notify(context, proposer_tg, family_messages.marriage_rejected(request.proposer_name))


async def cancel_marriage_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«لغو ازدواج» — withdraw your own open request."""
    message = update.message
    if message is None:
        return
    player_id = await _player_id(update, context)
    if player_id is None:
        await message.reply_text(error_messages.NOT_REGISTERED)
        return

    services = get_services(context)
    try:
        request = await services.family.cancel_request(player_id)
    except NoPendingRequestError:
        await message.reply_text("🤷 درخواست ازدواج بازی برای «لغو» کردن نداری.")
        return

    await message.reply_text(family_messages.marriage_cancelled(request.proposer_name))


# === Divorce =================================================================


async def divorce_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«طلاق» — end the marriage by paying the stored Mahriyeh."""
    message = update.message
    if message is None:
        return
    await _settle_and_announce(update, context)

    player_id = await _player_id(update, context)
    if player_id is None:
        await message.reply_text(error_messages.NOT_REGISTERED)
        return

    services = get_services(context)
    try:
        result = await services.family.divorce(player_id)
    except NotMarriedError:
        await message.reply_text(family_messages.not_married())
        return
    except MahriyehUnaffordableError as exc:
        await message.reply_text(family_messages.divorce_unaffordable(exc.required, exc.balance))
        return

    ex_name = await services.players.display_name_of(
        result.payee_player_id or result.initiator_player_id
    )
    await message.reply_text(family_messages.divorce_done(result, ex_name or "همسرت"))

    other = result.payee_player_id if result.payer_player_id == player_id else result.payer_player_id
    other_tg = await services.players.get_telegram_user_id(other or 0)
    if other_tg is not None and other_tg != message.chat.id:
        await _notify(context, other_tg, f"💔 ازدواجت تموم شد. مهریه: {result.mahriyeh_amount:,}".replace(",", "٬"))


# === Cheating ================================================================


async def cheating_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«خیانت» — hidden attempt; only a discovery produces consequences."""
    message = update.message
    if message is None:
        return
    await _settle_and_announce(update, context)

    player_id = await _player_id(update, context)
    if player_id is None:
        await message.reply_text(error_messages.NOT_REGISTERED)
        return

    services = get_services(context)
    try:
        result = await services.family.cheat(player_id)
    except NotMarriedError:
        await _reply_or_hide(update, context, family_messages.not_married())
        return

    if result.discovered:
        text = family_messages.cheating_discovered(result)
    elif result.success:
        text = family_messages.cheating_success(result)
    else:
        text = family_messages.cheating_failed()

    await _reply_or_hide(update, context, text)

    if result.discovered and result.spouse_player_id is not None:
        spouse_tg = await services.players.get_telegram_user_id(result.spouse_player_id)
        spouse_name = await services.players.display_name_of(player_id)
        await _notify(
            context,
            spouse_tg,
            f"🕵️ متأسفیم که باید این رو بگیم: {spouse_name} بهت خیانت کرد و فاش شد.",
        )


# === Relationship ============================================================


async def relationship_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«رابطه» as a reply to the spouse's message — may start a pregnancy."""
    message = update.message
    if message is None:
        return
    await _settle_and_announce(update, context)

    player_id = await _player_id(update, context)
    if player_id is None:
        await message.reply_text(error_messages.NOT_REGISTERED)
        return

    services = get_services(context)
    info = await _safe_family_info(services, player_id)
    if info is None or not info.married:
        await message.reply_text(family_messages.not_married())
        return

    target_player_id = None
    replied = message.reply_to_message
    if replied is not None and replied.from_user is not None and not replied.from_user.is_bot:
        target_player_id = await services.players.resolve_player_id(replied.from_user.id)

    try:
        result = await services.family.relationship(player_id, target_player_id=target_player_id)
    except NotSpouseError:
        await message.reply_text(family_messages.relationship_must_reply_to_spouse())
        return
    except NotMarriedError:
        await message.reply_text(family_messages.not_married())
        return

    await message.reply_text(family_messages.relationship_result(result, info.spouse_name))


# === Read-only screens =======================================================


async def family_info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«خانواده» — marriage status, spouse, date, children, Mahriyeh."""
    message = update.message
    if message is None:
        return
    await _settle_and_announce(update, context)

    player_id = await _player_id(update, context)
    if player_id is None:
        await message.reply_text(error_messages.NOT_REGISTERED)
        return

    services = get_services(context)
    info = await _safe_family_info(services, player_id)
    if info is None:
        await message.reply_text(error_messages.NOT_REGISTERED)
        return
    await message.reply_text(family_messages.family_info(info))


async def children_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«فرزندان» — the player's children."""
    message = update.message
    if message is None:
        return
    await _settle_and_announce(update, context)

    player_id = await _player_id(update, context)
    if player_id is None:
        await message.reply_text(error_messages.NOT_REGISTERED)
        return
    services = get_services(context)
    children = await services.family.list_children(player_id)
    await message.reply_text(family_messages.children_list(children))


async def family_history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«تاریخچه خانواده» — the family timeline."""
    message = update.message
    if message is None:
        return
    await _settle_and_announce(update, context)

    player_id = await _player_id(update, context)
    if player_id is None:
        await message.reply_text(error_messages.NOT_REGISTERED)
        return
    services = get_services(context)
    entries = await services.family.get_family_history(player_id)
    await message.reply_text(family_messages.family_history_list(entries))


async def family_help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«راهنمای خانواده» — the command list (text only, no menu)."""
    if update.message is None:
        return
    await update.message.reply_text(family_messages.commands_help())


async def _safe_family_info(services, player_id: int):
    try:
        return await services.family.get_family_info(player_id)
    except PlayerNotFoundError:
        return None


__all__ = [
    "accept_marriage_handler",
    "cancel_marriage_handler",
    "children_handler",
    "cheating_handler",
    "divorce_handler",
    "family_help_handler",
    "family_history_handler",
    "family_info_handler",
    "reject_marriage_handler",
    "relationship_handler",
    "marriage_text_handler",
]
