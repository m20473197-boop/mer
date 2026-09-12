"""Money service tests: exactness, add/remove, guards, insufficiency."""

from __future__ import annotations

import pytest

from app.game.shared.errors import (
    InsufficientFundsError,
    InvalidAmountError,
    PlayerNotFoundError,
)


async def test_new_player_balance_is_zero(services, register):
    player = await register(tg_id=4000)
    assert await services.money.get_balance(player.player_id) == 0


async def test_add_money_increases_balance(services, register):
    player = await register(tg_id=4001)

    first = await services.money.add_money(player.player_id, 250_000)
    second = await services.money.add_money(player.player_id, 1)

    assert first.balance_after == 250_000
    assert second.balance_after == 250_001
    assert await services.money.get_balance(player.player_id) == 250_001


async def test_remove_money_decreases_balance(services, register):
    player = await register(tg_id=4002)
    await services.money.add_money(player.player_id, 500)

    result = await services.money.remove_money(player.player_id, 200)

    assert result.amount == 200
    assert result.balance_after == 300
    assert await services.money.get_balance(player.player_id) == 300


async def test_removing_more_than_balance_is_blocked(services, register):
    player = await register(tg_id=4003)
    await services.money.add_money(player.player_id, 100)

    with pytest.raises(InsufficientFundsError):
        await services.money.remove_money(player.player_id, 101)

    # Atomic refusal: the balance is untouched.
    assert await services.money.get_balance(player.player_id) == 100


async def test_removing_exact_balance_is_allowed(services, register):
    player = await register(tg_id=4004)
    await services.money.add_money(player.player_id, 100)

    result = await services.money.remove_money(player.player_id, 100)

    assert result.balance_after == 0


async def test_invalid_money_amounts_are_rejected(services, register):
    player = await register(tg_id=4005)

    with pytest.raises(InvalidAmountError):
        await services.money.add_money(player.player_id, 0)
    with pytest.raises(InvalidAmountError):
        await services.money.add_money(player.player_id, -5)
    with pytest.raises(InvalidAmountError):
        await services.money.remove_money(player.player_id, 0)
    with pytest.raises(InvalidAmountError):
        await services.money.remove_money(player.player_id, -1)
    with pytest.raises(InvalidAmountError):
        await services.money.has_enough(player.player_id, -1)


async def test_has_enough(services, register):
    player = await register(tg_id=4006)
    await services.money.add_money(player.player_id, 500)

    assert await services.money.has_enough(player.player_id, 500) is True
    assert await services.money.has_enough(player.player_id, 501) is False


async def test_money_is_exact_for_big_integers(services, register):
    player = await register(tg_id=4007)
    big = 10**15

    result = await services.money.add_money(player.player_id, big)

    assert result.balance_after == 10**15  # no float rounding, ever
    assert await services.money.get_balance(player.player_id) == big


async def test_money_operations_on_missing_player_raise(services):
    with pytest.raises(PlayerNotFoundError):
        await services.money.get_balance(424242)
    with pytest.raises(PlayerNotFoundError):
        await services.money.add_money(424242, 10)
    with pytest.raises(PlayerNotFoundError):
        await services.money.remove_money(424242, 10)
    with pytest.raises(PlayerNotFoundError):
        await services.money.has_enough(424242, 10)
