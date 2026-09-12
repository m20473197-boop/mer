"""Unit tests for the pure progression math."""

from __future__ import annotations

import pytest

from app.core import constants
from app.game.player.progression import (
    level_from_total_xp,
    total_xp_for_level,
    xp_for_level_up,
)


def test_first_level_up_costs_base_xp():
    assert xp_for_level_up(1) == constants.XP_BASE_PER_LEVEL


def test_level_1_requires_no_xp():
    assert total_xp_for_level(1) == 0


def test_level_from_total_xp_boundaries():
    first_step = xp_for_level_up(1)
    assert level_from_total_xp(0) == 1
    assert level_from_total_xp(first_step - 1) == 1
    assert level_from_total_xp(first_step) == 2
    assert level_from_total_xp(first_step + first_step - 1) == 2


def test_round_trip_level_and_total_xp():
    for level in range(1, 9):
        assert level_from_total_xp(total_xp_for_level(level)) == level


def test_curve_is_strictly_increasing():
    costs = [xp_for_level_up(level) for level in range(1, 15)]
    assert all(b > a for a, b in zip(costs, costs[1:]))


def test_invalid_inputs_are_rejected():
    with pytest.raises(ValueError):
        xp_for_level_up(0)
    with pytest.raises(ValueError):
        total_xp_for_level(-1)
    with pytest.raises(ValueError):
        level_from_total_xp(-5)
