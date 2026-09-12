"""Focused verification for the fictional 🕳️ خلاف use cases."""

from __future__ import annotations

import random
from dataclasses import replace
from datetime import timedelta

import pytest

from app.bot.keyboards import callbacks
from app.bot.keyboards.main_menu import build_main_menu
from app.game.crime.catalog import ShotiMissionTemplate
from app.game.crime.errors import (
    CrimeActiveMissionError,
    CrimeDuplicateDocumentError,
    CrimeInvalidTargetError,
)
from app.services.crime_service import CrimeService


def _crime_service(services, **changes) -> CrimeService:
    defaults = {
        "information_success_percent": 100,
        "information_cooldown_seconds": 0,
        "laundering_cooldown_seconds": 0,
        "bank_hack_success_percent": 100,
        "bank_hack_amount": 100_000,
        "bank_hack_cooldown_seconds": 0,
    }
    defaults.update(changes)
    config = replace(services.crime.config, **defaults)
    return CrimeService(
        services.crime._session_factory,  # noqa: SLF001 - focused service fixture
        money_service=services.money,
        bank_service=services.bank,
        vehicle_service=services.vehicles,
        config=config,
        rng=random.Random(7),
    )


@pytest.mark.asyncio
async def test_information_selling_reward_history_and_idempotency(services, register):
    actor = await register(100, username="actor", display_name="فروشنده")
    target = await register(101, username="target", display_name="هدف")
    crime = _crime_service(services)

    result = await crime.sell_information(actor.player_id, target.player_id, operation_key="info-1")
    duplicate = await crime.sell_information(
        actor.player_id, target.player_id, operation_key="info-1"
    )

    assert result.success is True
    assert result.reward_amount == crime.config.information_reward
    assert duplicate.activity.activity_id == result.activity.activity_id
    assert await services.money.get_balance(actor.player_id) == crime.config.information_reward
    rows, total, _, _ = await crime.get_history(actor.player_id)
    assert total == 1
    assert rows[0].success is True

    with pytest.raises(CrimeInvalidTargetError):
        await crime.sell_information(actor.player_id, actor.player_id, operation_key="self-1")


@pytest.mark.asyncio
async def test_laundering_debits_then_pays_once_when_due(services, register):
    player = await register(110, username="launder", display_name="شست‌وشو")
    await services.money.add_money(player.player_id, 1_000_000)
    crime = _crime_service(services, laundering_processing_seconds=30)
    before = await services.money.get_balance(player.player_id)

    operation = await crime.start_laundering(
        player.player_id, 500_000, operation_key="launder-1"
    )
    assert operation.status == "pending"
    assert operation.fee_amount == 50_000
    assert await services.money.get_balance(player.player_id) == before - 500_000

    await crime.process_due_operations(now=operation.process_at)
    after_first = await services.money.get_balance(player.player_id)
    await crime.process_due_operations(now=operation.process_at + timedelta(seconds=1))
    assert after_first == before - 50_000
    assert await services.money.get_balance(player.player_id) == after_first
    assert (await crime.get_laundering_history(player.player_id))[0].status == "completed"


@pytest.mark.asyncio
async def test_fake_documents_ownership_and_duplicate_active_record(services, register):
    player = await register(120, username="docs", display_name="مدرک‌دار")
    crime = _crime_service(services)

    document = await crime.issue_fake_document(
        player.player_id, "identity", operation_key="doc-1"
    )
    assert document.status == "active"
    assert await crime.owns_document(player.player_id, "identity") is True
    with pytest.raises(CrimeDuplicateDocumentError):
        await crime.issue_fake_document(player.player_id, "identity", operation_key="doc-2")
    assert {row.document_type for row in await crime.list_documents(player.player_id)} == {"identity"}


@pytest.mark.asyncio
async def test_shoti_uses_owned_eligible_vehicle_and_settles_once(services, register):
    player = await register(130, username="driver", display_name="راننده")
    await services.money.add_money(player.player_id, 2_000_000_000)
    await services.vehicles.ensure_catalog()
    crime = _crime_service(
        services,
        shoti_success_base_percent=100,
        shoti_vehicle_modifiers={
            "peugeot_405": 100,
            "peugeot_pars": 100,
            "zantia": 100,
            "samand": 100,
        },
        shoti_templates=(ShotiMissionTemplate("تهران", "قم", "قطعات", 400_000, 0, 0, 30),),
    )
    ownership = await services.vehicles.purchase(player.player_id, 7)
    eligible = await crime.get_eligible_vehicles(player.player_id)
    assert [item.ownership_id for item in eligible] == [ownership.ownership.ownership_id]

    mission = await crime.start_shoti_mission(
        player.player_id, ownership.ownership.ownership_id, operation_key="shoti-1"
    )
    with pytest.raises(CrimeActiveMissionError):
        await crime.start_shoti_mission(
            player.player_id, ownership.ownership.ownership_id, operation_key="shoti-2"
        )
    balance_before_settlement = await services.money.get_balance(player.player_id)
    await crime.process_due_operations(now=mission.completes_at)
    balance_after = await services.money.get_balance(player.player_id)
    await crime.process_due_operations(now=mission.completes_at + timedelta(seconds=1))
    assert balance_after == balance_before_settlement + 400_000
    assert await services.money.get_balance(player.player_id) == balance_after
    assert (await crime.get_shoti_missions(player.player_id))[0].status == "completed"


@pytest.mark.asyncio
async def test_bank_hack_transfers_only_on_success_and_is_idempotent(services, register):
    attacker = await register(140, username="hacker", display_name="نفوذگر")
    target = await register(141, username="banked", display_name="حساب‌دار")
    await services.money.add_money(target.player_id, 100_000)
    await services.bank.deposit(target.player_id, 100_000, operation_id="seed-bank")
    crime = _crime_service(services)

    result = await crime.hack_bank_account(
        attacker.player_id, target.player_id, operation_key="hack-1"
    )
    duplicate = await crime.hack_bank_account(
        attacker.player_id, target.player_id, operation_key="hack-1"
    )
    assert result.success is True
    assert result.transferred_amount == 100_000
    assert duplicate.activity.activity_id == result.activity.activity_id
    assert (await services.bank.get_account(attacker.player_id, process_interest=False)).balance == 100_000
    assert (await services.bank.get_account(target.player_id, process_interest=False)).balance == 0

    no_transfer = _crime_service(services, bank_hack_success_percent=0)
    failed = await no_transfer.hack_bank_account(
        attacker.player_id, target.player_id, operation_key="hack-fail"
    )
    assert failed.success is False
    assert failed.transferred_amount == 0
    assert (await services.bank.get_account(attacker.player_id, process_interest=False)).balance == 100_000


def test_crime_is_in_main_menu_but_shoti_is_not_a_main_menu_callback():
    markup = build_main_menu()
    data = {button.callback_data for row in markup.inline_keyboard for button in row}
    labels = {button.text for row in markup.inline_keyboard for button in row}
    assert callbacks.CRIME_MENU in data
    assert callbacks.CRIME_SHOTI not in data
    assert "🕳️ خلاف" in labels
    assert "🏎️ شوتی" not in labels
