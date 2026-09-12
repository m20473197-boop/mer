"""Registration tests: creation, starting values, duplicate prevention."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.database.models.player import Player


async def test_register_creates_new_player(register):
    result = await register(tg_id=1001)

    assert result.created is True
    assert isinstance(result.player_id, int)
    assert result.player_id > 0
    assert result.profile.display_name == "علی"


async def test_starting_values_are_persisted_in_database(services, register, db):
    await register(tg_id=1002)

    async with db.session_factory() as session:
        player = (
            await session.execute(select(Player).where(Player.telegram_user_id == 1002))
        ).scalar_one()

    assert player.telegram_user_id == 1002
    assert player.level == 1
    assert player.xp == 0
    assert player.money == 0
    assert player.created_at is not None
    assert player.updated_at is not None


async def test_new_player_starts_at_level_1(register):
    result = await register(tg_id=1010)
    assert result.profile.level == 1


async def test_new_player_starts_with_zero_xp(register):
    result = await register(tg_id=1011)
    assert result.profile.xp == 0


async def test_new_player_starts_with_zero_money(register):
    result = await register(tg_id=1012)
    assert result.profile.money == 0


async def test_second_start_does_not_create_duplicate(services, register, db):
    first = await register(tg_id=1003)
    second = await register(tg_id=1003, username="new_name", display_name="علی دومی")

    assert first.created is True
    assert second.created is False
    assert second.player_id == first.player_id
    # Existing data is kept untouched — no re-initialization.
    assert second.profile.level == 1
    assert second.profile.xp == 0
    assert second.profile.money == 0

    async with db.session_factory() as session:
        rows = (await session.execute(select(Player))).scalars().all()
    assert len(rows) == 1


async def test_concurrent_registration_creates_single_player(services, register, db):
    results = await asyncio.gather(
        register(tg_id=1004),
        register(tg_id=1004),
        register(tg_id=1004),
    )

    assert sum(1 for r in results if r.created) == 1
    assert len({r.player_id for r in results}) == 1

    async with db.session_factory() as session:
        rows = (await session.execute(select(Player))).scalars().all()
    assert len(rows) == 1


async def test_find_player_by_telegram_user_id(services, register):
    await register(tg_id=2001, username="kobra", display_name="کبری")

    profile = await services.players.get_profile(2001)
    assert profile is not None
    assert profile.display_name == "کبری"

    missing = await services.players.get_profile(987654321)
    assert missing is None
