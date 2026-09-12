"""Land, Construction and Renovation handlers.

All business logic lives in RealEstateService; these handlers only translate
between Telegram objects and service calls. The construction flow is a fully
button-driven wizard: type → floors → size → rooms → quality → facilities →
confirm — every choice carried inside compact ASCII callback data.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.context import get_services
from app.bot.handlers.guards import requires_feature
from app.bot.keyboards import build_back_to_main, callbacks
from app.bot.keyboards.realestate import (
    build_construction_confirmation,
    build_land_buy_confirmation,
    build_land_info,
    build_lands_market,
    build_my_lands,
    build_option_grid,
    build_renovation_confirmation,
    build_renovation_options,
    build_renovatable_houses,
    build_status_screen,
    build_vacant_lands,
)
from app.bot.messages import errors as error_messages
from app.bot.messages import realestate as re_messages
from app.bot.messages.formatters import fa_int
from app.game.realestate import construction as construction_domain
from app.game.realestate.dto import LandWithStatus
from app.game.shared.errors import DomainError, InsufficientFundsError
from app.services.realestate_service import (
    AlreadyRenovatingError,
    LandBusyError,
    LandNotAvailableError,
    LandNotFoundError,
    NothingToRenovateError,
    ProjectNotFoundError,
    RenovationBlockedError,
    SpecInvalidError,
)

logger = logging.getLogger(__name__)

# Text triggers (exact-match Persian commands)
LANDS_MY_TEXT_TRIGGER = "زمین‌های من"
LANDS_MARKET_TEXT_TRIGGER = "خرید زمین"
BUILD_TEXT_TRIGGER = "ساخت خانه"
STATUS_TEXT_TRIGGER = "وضعیت ساخت"
RENOVATE_TEXT_TRIGGER = "بازسازی خانه"


async def _resolve_player_id(services, tg_id: int) -> int | None:
    """Map a Telegram user id to the internal player id (None if unregistered)."""
    from app.database.repositories.player_repository import PlayerRepository

    async with services.players._session_factory() as session:  # type: ignore[attr-defined]
        player = await PlayerRepository(session).get_by_telegram_user_id(tg_id)
        return player.id if player is not None else None


async def _edit(query, text: str, markup=None) -> None:
    """Edit a callback message, tolerating harmless no-op edits."""
    from telegram.error import BadRequest

    try:
        await query.edit_message_text(text=text, reply_markup=markup)
    except BadRequest as exc:
        if "not modified" in str(exc).lower():
            logger.debug("Ignored identical message edit")
        else:
            raise


def _error_text(exc: DomainError) -> str:
    """Translate a real-estate domain error into its friendly Persian text."""
    mapping = {
        LandNotFoundError: re_messages.land_not_found_text,
        LandNotAvailableError: re_messages.land_not_available_text,
        LandBusyError: re_messages.land_busy_text,
        SpecInvalidError: re_messages.spec_invalid_text,
        ProjectNotFoundError: re_messages.project_not_found_text,
        AlreadyRenovatingError: re_messages.already_renovating_text,
        RenovationBlockedError: re_messages.renovation_blocked_text,
        NothingToRenovateError: re_messages.nothing_to_renovate_text,
        InsufficientFundsError: re_messages.insufficient_funds_text,
    }
    factory = mapping.get(type(exc))
    return factory() if factory else error_messages.GENERIC


def _parse_id(raw: str) -> int | None:
    try:
        return int(raw)
    except ValueError:
        return None


async def _settle_and_answer(query, services) -> int | None:
    """Settle due projects first, then resolve the player (None if unknown)."""
    try:
        await services.realestate.settle_due()
    except Exception:  # noqa: BLE001 — settlement is lazy, never blocks a screen
        logger.warning("settle_due failed", exc_info=True)
    return await _resolve_player_id(services, query.from_user.id)


# --- Land market -------------------------------------------------------------------


@requires_feature("realestate")
async def show_lands_market(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.RE_LANDS_MARKET:
        return
    await query.answer()

    services = get_services(context)
    entries = await services.realestate.get_available_lands()
    await _edit(query, re_messages.lands_market_text(entries), build_lands_market(entries))


@requires_feature("realestate")
async def show_land_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.RE_LAND_INFO_PREFIX):
        return
    await query.answer()

    land_id = _parse_id(query.data[len(callbacks.RE_LAND_INFO_PREFIX):])
    if land_id is None:
        return

    services = get_services(context)
    viewer_id = await _resolve_player_id(services, query.from_user.id)
    try:
        info = await services.realestate.get_land_info(land_id, viewer_id)
    except LandNotFoundError:
        await _edit(query, re_messages.land_not_found_text(), None)
        return
    await _edit(
        query, re_messages.land_info_text(info), build_land_info(info, viewer_id)
    )


@requires_feature("realestate")
async def show_land_buy_confirmation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.RE_LAND_BUY_PREFIX):
        return
    await query.answer()

    land_id = _parse_id(query.data[len(callbacks.RE_LAND_BUY_PREFIX):])
    if land_id is None:
        return

    services = get_services(context)
    viewer_id = await _resolve_player_id(services, query.from_user.id)
    if viewer_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return
    try:
        info = await services.realestate.get_land_info(land_id, viewer_id)
    except LandNotFoundError:
        await _edit(query, re_messages.land_not_found_text(), None)
        return
    await _edit(
        query,
        re_messages.land_buy_confirmation_text(info),
        build_land_buy_confirmation(land_id),
    )


@requires_feature("realestate")
async def confirm_land_buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.RE_LAND_BUY_OK_PREFIX):
        return
    await query.answer()

    land_id = _parse_id(query.data[len(callbacks.RE_LAND_BUY_OK_PREFIX):])
    if land_id is None:
        return

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        result = await services.realestate.buy_land(player_id, land_id)
    except DomainError as exc:
        await _edit(query, _error_text(exc), None)
        return
    except Exception as exc:
        logger.error("confirm_land_buy failed for %s", query.from_user.id, exc_info=exc)
        await _edit(query, error_messages.GENERIC, None)
        return

    info = await services.realestate.get_land_info(land_id, player_id)
    await _edit(
        query,
        re_messages.land_purchased_text(result),
        build_land_info(info, player_id),
    )


# --- My lands -------------------------------------------------------------------------


@requires_feature("realestate")
async def show_my_lands(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.RE_LANDS_MY:
        return
    await query.answer()

    services = get_services(context)
    player_id = await _settle_and_answer(query, services)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        assets = await services.realestate.get_my_lands(player_id)
    except Exception as exc:
        logger.error("show_my_lands failed for %s", query.from_user.id, exc_info=exc)
        await _edit(query, error_messages.GENERIC, None)
        return

    await _edit(query, re_messages.my_lands_text(assets), build_my_lands(assets))


# --- Construction wizard ------------------------------------------------------------------


def _vacant_lands(assets) -> list[LandWithStatus]:
    return [
        item
        for item in assets.lands
        if item.land.built_house_id is None and item.active_construction is None
    ]


@requires_feature("realestate")
async def show_build_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.RE_BUILD_MENU:
        return
    await query.answer()

    services = get_services(context)
    player_id = await _settle_and_answer(query, services)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    assets = await services.realestate.get_my_lands(player_id)
    vacant = _vacant_lands(assets)
    await _edit(
        query,
        (
            "🏗️ ساخت خانه — روی کدوم زمین؟\n"
            "━━━━━━━━━━━━━━━\n"
            "زمین خالی‌ات رو انتخاب کن تا نقشه ساخت رو جلو ببریم 👇"
        ),
        build_vacant_lands(vacant),
    )


async def _load_land_for_step(services, player_id: int, land_id: int):
    """Fetch the parcel for a wizard step; returns (land_dto, error_text)."""
    try:
        land_dto, _floors, _max_floors = await services.realestate.get_land_for_building(
            land_id, player_id
        )
        return land_dto, None
    except DomainError as exc:
        return None, _error_text(exc)


def _spec_step_callback(land_id: int, *parts: object) -> str:
    joined = "_".join(str(p) for p in parts if p is not None)
    return f"{callbacks.RE_BUILD_SPEC_PREFIX}{land_id}{'_' + joined if joined else ''}"


@requires_feature("realestate")
async def show_build_type_picker(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Step 1 — building type («re_b_<land>»)."""
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.RE_BUILD_LAND_PREFIX):
        return
    await query.answer()

    land_id = _parse_id(query.data[len(callbacks.RE_BUILD_LAND_PREFIX):])
    if land_id is None:
        return

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    land, error = await _load_land_for_step(services, player_id, land_id)
    if error:
        await _edit(query, error, None)
        return

    options = [
        ("🏢 آپارتمانی (۲ تا ۴ طبقه)", _spec_step_callback(land_id, "a")),
        ("🏡 ویلایی (تک‌طبقه)", _spec_step_callback(land_id, "v")),
    ]
    await _edit(
        query,
        re_messages.build_type_text(land),
        build_option_grid(options, back_callback=callbacks.RE_BUILD_MENU),
    )


def _parse_build_spec(payload: str) -> tuple[int, str, int, int, int, str] | None:
    """Parse the accumulated ``re_bs_`` payload into wizard state.

    Returns ``(land_id, type_token, floors, size, bedrooms, quality_token)``
    with ``None``-meaning values as -1 / "" for steps not chosen yet.
    """
    parts = payload.split("_")
    if len(parts) < 2:
        return None
    land_id = _parse_id(parts[0])
    if land_id is None or parts[1] not in ("a", "v"):
        return None
    building_type = parts[1]
    floors = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else -1
    size = int(parts[3]) if len(parts) >= 4 and parts[3].isdigit() else -1
    bedrooms = int(parts[4]) if len(parts) >= 5 and parts[4].isdigit() else -1
    quality = parts[5] if len(parts) >= 6 and parts[5] in ("m", "g", "e") else ""
    return land_id, building_type, floors, size, bedrooms, quality


@requires_feature("realestate")
async def show_build_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Steps 2–6 — dispatched by how much blueprint is already chosen."""
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.RE_BUILD_SPEC_PREFIX):
        return
    await query.answer()

    payload = query.data[len(callbacks.RE_BUILD_SPEC_PREFIX):]
    parsed = _parse_build_spec(payload)
    if parsed is None:
        await query.answer(text=re_messages.spec_invalid_text(), show_alert=True)
        return
    land_id, building_type, floors, size, bedrooms, quality = parsed

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    land, error = await _load_land_for_step(services, player_id, land_id)
    if error:
        await _edit(query, error, None)
        return

    # Villa pins the floor count; apartments pick it.
    if building_type == construction_domain.TYPE_VILLA:
        floors = construction_domain.VILLA_FLOORS

    back_one = _spec_step_callback(land_id, building_type)

    # Step 2 — floors (apartments only)
    if floors == -1:
        options = [
            (
                f"🏢 {fa_int(f)} طبقه",
                _spec_step_callback(land_id, building_type, f),
            )
            for f in range(
                construction_domain.APARTMENT_MIN_FLOORS,
                construction_domain.APARTMENT_MAX_FLOORS + 1,
            )
        ]
        await _edit(
            query,
            re_messages.build_floors_text(land),
            build_option_grid(options, back_callback=back_one),
        )
        return

    # Step 3 — total built area
    if size == -1:
        presets = construction_domain.size_presets(land.area_sqm, floors)
        options = [
            (
                f"📐 {fa_int(area)} متر",
                _spec_step_callback(land_id, building_type, floors, area),
            )
            for area in presets
        ]
        await _edit(
            query,
            re_messages.build_size_text(land, floors),
            build_option_grid(options, back_callback=back_one),
        )
        return

    # Step 4 — bedrooms
    if bedrooms == -1:
        max_bedrooms = construction_domain.bedroom_max(size)
        options = [
            (
                f"🛏️ {fa_int(count)} اتاق",
                _spec_step_callback(land_id, building_type, floors, size, count),
            )
            for count in range(1, max_bedrooms + 1)
        ]
        await _edit(
            query,
            re_messages.build_bedrooms_text(land, floors, size),
            build_option_grid(options, back_callback=back_one),
        )
        return

    # Step 5 — quality / material grade
    if not quality:
        options = [
            (
                f"⭐ {label} ({material})",
                _spec_step_callback(land_id, building_type, floors, size, bedrooms, token),
            )
            for token, label in construction_domain.QUALITY_TOKENS.items()
            for material in [construction_domain.MATERIAL_LABELS[token]]
        ]
        await _edit(
            query,
            re_messages.build_quality_text(land, floors, size, bedrooms),
            build_option_grid(options, back_callback=back_one),
        )
        return

    # Step 6 — facilities presets
    facilities = [
        (
            "🅿️ ساده (بدون امکانات)",
            False,
            False,
            False,
        ),
        (
            "🚗 خانواده (پارکینگ + انباری)",
            True,
            False,
            True,
        ),
        (
            "✨ کامل (پارکینگ + انباری"
            + (" + آسانسور" if building_type == construction_domain.TYPE_APARTMENT else "")
            + ")",
            True,
            building_type == construction_domain.TYPE_APARTMENT,
            True,
        ),
    ]
    options = [
        (
            label,
            f"{callbacks.RE_BUILD_CONFIRM_PREFIX}"
            f"{land_id}_{building_type}_{floors}_{size}_{bedrooms}_{quality}"
            f"_P{int(parking)}E{int(elevator)}S{int(storage)}",
        )
        for label, parking, elevator, storage in facilities
    ]
    await _edit(
        query,
        re_messages.build_facilities_text(land, floors, size, bedrooms, quality),
        build_option_grid(options, back_callback=back_one),
    )


def _parse_full_blueprint(payload: str):
    """Parse ``land_t_fl_sz_br_q_P<p>E<e>S<s>`` into a BuildingSpec (or None)."""
    import re

    match = re.fullmatch(
        r"(\d+)_([av])_(\d+)_(\d+)_(\d+)_([mge])_P([01])E([01])S([01])", payload
    )
    if match is None:
        return None
    land_id, building_type, floors, size, bedrooms, quality, p, e, s = match.groups()
    spec = construction_domain.BuildingSpec(
        land_id=int(land_id),
        building_type=building_type,
        floors=int(floors),
        area_sqm=int(size),
        bedrooms=int(bedrooms),
        quality_token=quality,
        parking=p == "1",
        elevator=e == "1",
        storage=s == "1",
    )
    return spec


@requires_feature("realestate")
async def show_construction_confirmation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.RE_BUILD_CONFIRM_PREFIX):
        return
    await query.answer()

    payload = query.data[len(callbacks.RE_BUILD_CONFIRM_PREFIX):]
    spec = _parse_full_blueprint(payload)
    if spec is None:
        await query.answer(text=re_messages.spec_invalid_text(), show_alert=True)
        return

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    land, error = await _load_land_for_step(services, player_id, spec.land_id)
    if error:
        await _edit(query, error, None)
        return

    try:
        construction_domain.validate_spec(spec, land.area_sqm)
    except ValueError:
        await _edit(query, re_messages.spec_invalid_text(), None)
        return

    cost = construction_domain.construction_cost(spec)
    duration = construction_domain.construction_duration_seconds(spec)
    await _edit(
        query,
        re_messages.construction_confirm_text(land, spec, cost, duration),
        build_construction_confirmation(spec.land_id, payload),
    )


@requires_feature("realestate")
async def confirm_construction(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.RE_BUILD_EXEC_PREFIX):
        return
    await query.answer()

    payload = query.data[len(callbacks.RE_BUILD_EXEC_PREFIX):]
    spec = _parse_full_blueprint(payload)
    if spec is None:
        await query.answer(text=re_messages.spec_invalid_text(), show_alert=True)
        return

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        result = await services.realestate.start_construction(player_id, spec.land_id, spec)
    except DomainError as exc:
        await _edit(query, _error_text(exc), None)
        return
    except Exception as exc:
        logger.error("confirm_construction failed for %s", query.from_user.id, exc_info=exc)
        await _edit(query, error_messages.GENERIC, None)
        return

    await _edit(
        query,
        re_messages.construction_started_text(result),
        build_status_screen(
            await services.realestate.get_projects_status(player_id)
        ),
    )


@requires_feature("realestate")
async def cancel_construction(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.RE_BUILD_CANCEL_PREFIX):
        return
    await query.answer()

    project_id = _parse_id(query.data[len(callbacks.RE_BUILD_CANCEL_PREFIX):])
    if project_id is None:
        return

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        result = await services.realestate.cancel_construction(player_id, project_id)
    except DomainError as exc:
        await _edit(query, _error_text(exc), None)
        return
    except Exception as exc:
        logger.error("cancel_construction failed for %s", query.from_user.id, exc_info=exc)
        await _edit(query, error_messages.GENERIC, None)
        return

    status = await services.realestate.get_projects_status(player_id)
    await _edit(
        query,
        re_messages.construction_cancelled_text(result) + "\n\n" + re_messages.status_text(status),
        build_status_screen(status),
    )


# --- Construction / renovation status ------------------------------------------------------


@requires_feature("realestate")
async def show_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.RE_STATUS:
        return
    await query.answer()

    services = get_services(context)
    player_id = await _settle_and_answer(query, services)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        status = await services.realestate.get_projects_status(player_id)
    except Exception as exc:
        logger.error("show_status failed for %s", query.from_user.id, exc_info=exc)
        await _edit(query, error_messages.GENERIC, None)
        return

    await _edit(query, re_messages.status_text(status), build_status_screen(status))


# --- Renovation ------------------------------------------------------------------------------


@requires_feature("realestate")
async def show_renov_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.RE_RENOV_MENU:
        return
    await query.answer()

    services = get_services(context)
    player_id = await _settle_and_answer(query, services)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    houses = await services.realestate.get_renovatable_houses(player_id)
    await _edit(
        query,
        re_messages.renovatable_houses_text(houses, services.realestate.house_value),
        build_renovatable_houses(houses),
    )


@requires_feature("realestate")
async def show_renovation_options(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.RE_RENOV_OPTS_PREFIX):
        return
    await query.answer()

    house_id = _parse_id(query.data[len(callbacks.RE_RENOV_OPTS_PREFIX):])
    if house_id is None:
        return

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        house, _label, value, options = await services.realestate.get_renovation_options(
            player_id, house_id
        )
    except DomainError as exc:
        await _edit(query, _error_text(exc), None)
        return
    except Exception as exc:
        logger.error("show_renovation_options failed for %s", query.from_user.id, exc_info=exc)
        await _edit(query, error_messages.GENERIC, None)
        return

    await _edit(
        query,
        re_messages.renovation_options_text(house, value),
        build_renovation_options(house_id, options),
    )


def _parse_renov_payload(payload: str) -> tuple[int, str] | None:
    import re

    match = re.fullmatch(r"(\d+)_(q|k|ba|r|p|e|s|m)", payload)
    if match is None:
        return None
    return int(match.group(1)), match.group(2)


@requires_feature("realestate")
async def show_renovation_confirmation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.RE_RENOV_CONFIRM_PREFIX):
        return
    await query.answer()

    parsed = _parse_renov_payload(query.data[len(callbacks.RE_RENOV_CONFIRM_PREFIX):])
    if parsed is None:
        return
    house_id, renovation_type = parsed

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        _house, _label, value, options = await services.realestate.get_renovation_options(
            player_id, house_id
        )
        option = next(
            (o for o in options if o.renovation_type == renovation_type), None
        )
        if option is None or not option.applicable:
            await _edit(query, re_messages.nothing_to_renovate_text(), None)
            return
    except DomainError as exc:
        await _edit(query, _error_text(exc), None)
        return

    await _edit(
        query,
        re_messages.renovation_confirm_text(option, value),
        build_renovation_confirmation(house_id, renovation_type),
    )


@requires_feature("realestate")
async def confirm_renovation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data.startswith(callbacks.RE_RENOV_OK_PREFIX):
        return
    await query.answer()

    parsed = _parse_renov_payload(query.data[len(callbacks.RE_RENOV_OK_PREFIX):])
    if parsed is None:
        return
    house_id, renovation_type = parsed

    services = get_services(context)
    player_id = await _resolve_player_id(services, query.from_user.id)
    if player_id is None:
        await _edit(query, error_messages.NOT_REGISTERED, build_back_to_main())
        return

    try:
        result = await services.realestate.start_renovation(
            player_id, house_id, renovation_type
        )
    except DomainError as exc:
        await _edit(query, _error_text(exc), None)
        return
    except Exception as exc:
        logger.error("confirm_renovation failed for %s", query.from_user.id, exc_info=exc)
        await _edit(query, error_messages.GENERIC, None)
        return

    status = await services.realestate.get_projects_status(player_id)
    await _edit(
        query,
        re_messages.renovation_started_text(result),
        build_status_screen(status),
    )


# --- Text triggers --------------------------------------------------------------------------


@requires_feature("realestate")
async def lands_my_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    if (update.message.text or "").strip() != LANDS_MY_TEXT_TRIGGER:
        return
    services = get_services(context)
    player_id = await _resolve_player_id(services, update.effective_user.id)
    if player_id is None:
        await update.message.reply_text(error_messages.NOT_REGISTERED)
        return
    await services.realestate.settle_due()
    assets = await services.realestate.get_my_lands(player_id)
    await update.message.reply_text(
        re_messages.my_lands_text(assets), reply_markup=build_my_lands(assets)
    )


@requires_feature("realestate")
async def lands_market_text_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.message is None or update.effective_user is None:
        return
    if (update.message.text or "").strip() != LANDS_MARKET_TEXT_TRIGGER:
        return
    services = get_services(context)
    player_id = await _resolve_player_id(services, update.effective_user.id)
    if player_id is None:
        await update.message.reply_text(error_messages.NOT_REGISTERED)
        return
    entries = await services.realestate.get_available_lands()
    await update.message.reply_text(
        re_messages.lands_market_text(entries), reply_markup=build_lands_market(entries)
    )


@requires_feature("realestate")
async def build_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    if (update.message.text or "").strip() != BUILD_TEXT_TRIGGER:
        return
    services = get_services(context)
    player_id = await _resolve_player_id(services, update.effective_user.id)
    if player_id is None:
        await update.message.reply_text(error_messages.NOT_REGISTERED)
        return
    await services.realestate.settle_due()
    assets = await services.realestate.get_my_lands(player_id)
    vacant = _vacant_lands(assets)
    await update.message.reply_text(
        "🏗️ ساخت خانه — روی کدوم زمین؟",
        reply_markup=build_vacant_lands(vacant),
    )


@requires_feature("realestate")
async def status_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    if (update.message.text or "").strip() != STATUS_TEXT_TRIGGER:
        return
    services = get_services(context)
    player_id = await _resolve_player_id(services, update.effective_user.id)
    if player_id is None:
        await update.message.reply_text(error_messages.NOT_REGISTERED)
        return
    await services.realestate.settle_due()
    status = await services.realestate.get_projects_status(player_id)
    await update.message.reply_text(
        re_messages.status_text(status), reply_markup=build_status_screen(status)
    )


@requires_feature("realestate")
async def renovate_text_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.message is None or update.effective_user is None:
        return
    if (update.message.text or "").strip() != RENOVATE_TEXT_TRIGGER:
        return
    services = get_services(context)
    player_id = await _resolve_player_id(services, update.effective_user.id)
    if player_id is None:
        await update.message.reply_text(error_messages.NOT_REGISTERED)
        return
    await services.realestate.settle_due()
    houses = await services.realestate.get_renovatable_houses(player_id)
    await update.message.reply_text(
        re_messages.renovatable_houses_text(houses, services.realestate.house_value),
        reply_markup=build_renovatable_houses(houses),
    )
