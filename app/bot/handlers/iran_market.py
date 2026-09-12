"""Telegram handlers for the read-only ``📈 بازار ایران`` screens."""

from __future__ import annotations

import logging
import re

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.bot.context import get_services
from app.bot.keyboards import (
    build_back_to_main,
    build_iran_market_detail,
    build_iran_market_menu,
    callbacks,
)
from app.bot.messages import errors as error_messages
from app.bot.messages import iran_market as market_messages
from app.core import constants
from app.services.iran_market_service import IranMarketAssetNotFoundError

logger = logging.getLogger(__name__)

IRAN_MARKET_TEXT_TRIGGERS: tuple[str, ...] = constants.IRAN_MARKET_TEXT_TRIGGER_ALIASES
IRAN_MARKET_TEXT_PATTERN: str = "^(?:" + "|".join(
    re.escape(item) for item in IRAN_MARKET_TEXT_TRIGGERS
) + ")$"


async def _edit(query, text: str, markup=None) -> None:
    try:
        await query.edit_message_text(text=text, reply_markup=markup)
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise
        logger.debug("Ignored identical Iran market edit")


async def iran_market_text_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Open the stored market snapshot from «بازار ایران»/«بازار»."""
    if update.message is None or update.effective_user is None:
        return
    if (update.message.text or "").strip() not in IRAN_MARKET_TEXT_TRIGGERS:
        return
    services = get_services(context)
    try:
        snapshot = await services.market.get_snapshot()
        await update.message.reply_text(
            market_messages.iran_market_menu_text(snapshot),
            reply_markup=build_iran_market_menu(snapshot.assets),
        )
    except Exception as exc:  # noqa: BLE001 — no traceback to a player
        logger.error("Iran market text screen failed (%s)", type(exc).__name__)
        await update.message.reply_text(error_messages.GENERIC)


async def show_iran_market_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or query.data != callbacks.MARKET_MENU:
        return
    await query.answer()
    services = get_services(context)
    try:
        snapshot = await services.market.get_snapshot()
        await _edit(
            query,
            market_messages.iran_market_menu_text(snapshot),
            build_iran_market_menu(snapshot.assets),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Iran market menu failed (%s)", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_back_to_main())


async def show_iran_market_asset(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None:
        return
    data = query.data or ""
    if not data.startswith(callbacks.MARKET_ASSET_PREFIX):
        return
    await query.answer()
    code = data[len(callbacks.MARKET_ASSET_PREFIX) :]
    services = get_services(context)
    try:
        asset = await services.market.get_asset(code)
        await _edit(
            query,
            market_messages.iran_market_detail_text(asset),
            build_iran_market_detail(),
        )
    except IranMarketAssetNotFoundError:
        await _edit(
            query,
            market_messages.market_asset_not_found_text(),
            build_back_to_main(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Iran market detail failed (%s)", type(exc).__name__)
        await _edit(query, error_messages.GENERIC, build_back_to_main())
