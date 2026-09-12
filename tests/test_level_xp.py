"""Level/XP service tests."""

from __future__ import annotations

import pytest

from app.game.player.progression import level_from_total_xp, xp_for_level_up
from app.game.shared.errors import InvalidAmountError, PlayerNotFoundError


async def test_add_xp_increases_total_xp(services, register):
    player = await register(tg_id=3001)

    result = await services.levels.add_xp(player.player_id, 40)

    assert result.xp_before == 0
    assert result.xp_after == 40
    assert result.leveled_up is False
    assert await services.levels.get_xp(player.player_id) == 40


async def test_add_xp_detects_level_up(services, register):
    player = await register(tg_id=3002)

    result = await services.levels.add_xp(
        player.player_id, xp_for_level_up(1) + 10
    )

    assert result.leveled_up is True
    assert result.old_level == 1
    assert result.new_level == 2
    assert await services.levels.get_level(player.player_id) == 2


async def test_add_xp_supports_multiple_level_ups(services, register):
    player = await register(tg_id=3003)
    total = xp_for_level_up(1) + xp_for_level_up(2) + 5

    result = await services.levels.add_xp(player.player_id, total)

    assert result.leveled_up is True
    assert result.new_level == 3


async def test_level_always_consistent_with_total_xp(services, register):
    player = await register(tg_id=3005)

    await services.levels.add_xp(player.player_id, 123)

    xp = await services.levels.get_xp(player.player_id)
    level = await services.levels.get_level(player.player_id)
    assert level == level_from_total_xp(xp)


async def test_add_xp_rejects_invalid_amounts(services, register):
    player = await register(tg_id=3006)

    with pytest.raises(InvalidAmountError):
        await services.levels.add_xp(player.player_id, 0)
    with pytest.raises(InvalidAmountError):
        await services.levels.add_xp(player.player_id, -5)


async def test_add_xp_for_missing_player_raises(services):
    with pytest.raises(PlayerNotFoundError):
        await services.levels.add_xp(424242, 10)


async def test_get_xp_and_level_for_missing_player_raise(services):
    with pytest.raises(PlayerNotFoundError):
        await services.levels.get_xp(424242)
    with pytest.raises(PlayerNotFoundError):
        await services.levels.get_level(424242)
