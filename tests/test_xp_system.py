"""Complete Level/XP system tests — Stage 2.

Covers:
1. Adding XP
2. Removing XP
3. XP history creation
4. Level calculation
5. Level up detection
6. Multiple level increases
7. Preventing negative XP
8. Player status calculation
9. Database persistence
"""

from __future__ import annotations

import pytest

from app.game.player.progression import (
    get_level_progress,
    level_from_total_xp,
    total_xp_for_level,
    xp_for_level_up,
)
from app.game.shared.errors import InvalidAmountError, PlayerNotFoundError


# --- 1. Adding XP --------------------------------------------------------


async def test_adding_xp_increases_total_and_creates_history(services, register):
    player = await register(tg_id=6001)
    result = await services.levels.add_xp(player.player_id, 50, reason="Completed job")

    assert result.xp_before == 0
    assert result.xp_after == 50
    assert result.reason == "Completed job"
    assert result.transaction_id is not None

    # Check history
    history = await services.levels.get_xp_history(player.player_id)
    assert len(history) == 1
    assert history[0].amount == 50
    assert history[0].reason == "Completed job"


async def test_adding_xp_with_default_reason(services, register):
    player = await register(tg_id=6002)
    result = await services.levels.add_xp(player.player_id, 10)

    assert result.reason == "unknown"
    history = await services.levels.get_xp_history(player.player_id)
    assert history[0].reason == "unknown"


# --- 2. Removing XP ------------------------------------------------------


async def test_removing_xp_decreases_and_creates_negative_history(services, register):
    player = await register(tg_id=6003)
    await services.levels.add_xp(player.player_id, 100, reason="init")

    result = await services.levels.remove_xp(player.player_id, 30, reason="penalty")

    assert result.xp_before == 100
    assert result.xp_after == 70
    assert result.reason == "penalty"
    assert result.transaction_id is not None

    history = await services.levels.get_xp_history(player.player_id)
    # History ordered desc, so first should be removal
    assert len(history) == 2
    # Find negative transaction
    amounts = [h.amount for h in history]
    assert -30 in amounts
    assert 100 in amounts


async def test_removing_xp_updates_level_if_needed(services, register):
    player = await register(tg_id=6004)
    # Level 2 requires 100 XP, Level 3 requires 235 total
    await services.levels.add_xp(player.player_id, 250, reason="big gain")
    # Should be level 3
    assert await services.levels.get_level(player.player_id) == 3

    # Remove 200 -> 50 XP, should drop to level 1
    result = await services.levels.remove_xp(player.player_id, 200, reason="loss")
    assert result.new_level == 1
    assert result.leveled_down is True
    assert await services.levels.get_level(player.player_id) == 1


# --- 3. XP history creation ----------------------------------------------


async def test_xp_history_records_every_change(services, register):
    player = await register(tg_id=6005)

    await services.levels.add_xp(player.player_id, 10, reason="job")
    await services.levels.add_xp(player.player_id, 20, reason="skill")
    await services.levels.add_xp(player.player_id, 30, reason="event")

    history = await services.levels.get_xp_history(player.player_id, limit=10)
    assert len(history) == 3
    # Most recent first
    assert history[0].amount == 30
    assert history[0].reason == "event"

    # Check persistence via get_all
    from app.database.repositories.xp_transaction_repository import (
        XPTransactionRepository,
    )

    async with services.levels._session_factory() as session:
        repo = XPTransactionRepository(session)
        all_tx = await repo.get_all_by_player(player.player_id)
        assert len(all_tx) == 3
        assert all_tx[0].amount == 10  # asc order
        assert all_tx[2].amount == 30


async def test_xp_history_supports_custom_reasons(services, register):
    player = await register(tg_id=6006)

    reasons = ["Completed job", "Learning skill", "Daily bonus", "admin_add_xp"]
    for i, r in enumerate(reasons):
        await services.levels.add_xp(player.player_id, 5 + i, reason=r)

    history = await services.levels.get_xp_history(player.player_id)
    recorded_reasons = {h.reason for h in history}
    for r in reasons:
        assert r in recorded_reasons


# --- 4. Level calculation ------------------------------------------------


async def test_level_calculation_is_consistent(services, register):
    player = await register(tg_id=6007)

    # Add XP step by step and verify level matches pure function
    total = 0
    for amount in [10, 50, 90, 100, 200]:
        await services.levels.add_xp(player.player_id, amount, reason="test")
        total += amount
        expected_level = level_from_total_xp(total)
        actual_level = await services.levels.get_level(player.player_id)
        assert actual_level == expected_level
        assert (await services.levels.get_xp(player.player_id)) == total


def test_progression_math_pure_functions():
    # Test pure progression helpers
    assert xp_for_level_up(1) == 100
    assert total_xp_for_level(1) == 0
    assert total_xp_for_level(2) == 100

    prog = get_level_progress(0)
    assert prog.level == 1
    assert prog.xp_in_current_level == 0
    assert prog.xp_needed_for_next == 100
    assert prog.progress_percent == 0.0

    prog2 = get_level_progress(50)
    assert prog2.level == 1
    assert prog2.xp_in_current_level == 50
    assert prog2.progress_percent == 50.0

    prog3 = get_level_progress(100)
    assert prog3.level == 2
    assert prog3.xp_in_current_level == 0


# --- 5. Level up detection ------------------------------------------------


async def test_level_up_detection_single(services, register):
    player = await register(tg_id=6008)

    # Level 1 -> 2 needs 100
    result = await services.levels.add_xp(player.player_id, 100, reason="level up test")

    assert result.leveled_up is True
    assert result.old_level == 1
    assert result.new_level == 2

    # Check level up history
    level_history = await services.levels.get_level_up_history(player.player_id)
    assert len(level_history) == 1
    assert level_history[0].old_level == 1
    assert level_history[0].new_level == 2


async def test_no_level_up_when_not_enough_xp(services, register):
    player = await register(tg_id=6009)

    result = await services.levels.add_xp(player.player_id, 50, reason="small")

    assert result.leveled_up is False
    assert result.old_level == 1
    assert result.new_level == 1

    level_history = await services.levels.get_level_up_history(player.player_id)
    assert len(level_history) == 0


# --- 6. Multiple level increases -----------------------------------------


async def test_multiple_level_ups_in_one_add(services, register):
    player = await register(tg_id=6010)

    # Calculate XP needed for level 4: sum of L1+L2+L3
    xp_for_l4 = total_xp_for_level(4)  # should be 100+135+182=417
    result = await services.levels.add_xp(player.player_id, xp_for_l4, reason="mega")

    assert result.leveled_up is True
    assert result.old_level == 1
    assert result.new_level == 4

    # Level up history should have one record for the jump (1->4)
    # Our implementation records one entry per add_xp that results in level up,
    # storing old and new. This satisfies requirement to store old/new/timestamp.
    level_history = await services.levels.get_level_up_history(player.player_id)
    assert len(level_history) == 1
    assert level_history[0].old_level == 1
    assert level_history[0].new_level == 4

    # Also test incremental level ups create multiple records
    player2 = await register(tg_id=6011)
    await services.levels.add_xp(player2.player_id, 100, reason="to 2")
    await services.levels.add_xp(player2.player_id, 135, reason="to 3")
    await services.levels.add_xp(player2.player_id, 182, reason="to 4")

    history2 = await services.levels.get_level_up_history(player2.player_id)
    assert len(history2) == 3
    # Ordered desc, so latest first
    assert history2[0].new_level == 4
    assert history2[2].old_level == 1


# --- 7. Preventing negative XP -------------------------------------------


async def test_preventing_negative_xp_on_add(services, register):
    player = await register(tg_id=6012)

    with pytest.raises(InvalidAmountError):
        await services.levels.add_xp(player.player_id, 0, reason="zero")
    with pytest.raises(InvalidAmountError):
        await services.levels.add_xp(player.player_id, -10, reason="negative")


async def test_preventing_negative_xp_on_remove(services, register):
    player = await register(tg_id=6013)
    await services.levels.add_xp(player.player_id, 50, reason="init")

    with pytest.raises(InvalidAmountError):
        await services.levels.remove_xp(player.player_id, 0, reason="zero")
    with pytest.raises(InvalidAmountError):
        await services.levels.remove_xp(player.player_id, -5, reason="negative")

    # Cannot remove more than current XP
    with pytest.raises(InvalidAmountError):
        await services.levels.remove_xp(player.player_id, 60, reason="too much")

    # Balance unchanged after failed removal
    assert await services.levels.get_xp(player.player_id) == 50

    # Removing exact balance is allowed and results in 0 XP
    result = await services.levels.remove_xp(player.player_id, 50, reason="all")
    assert result.xp_after == 0
    assert await services.levels.get_xp(player.player_id) == 0


async def test_xp_never_below_zero_after_multiple_removals(services, register):
    player = await register(tg_id=6014)
    await services.levels.add_xp(player.player_id, 100, reason="init")
    await services.levels.remove_xp(player.player_id, 30, reason="a")
    await services.levels.remove_xp(player.player_id, 30, reason="b")

    with pytest.raises(InvalidAmountError):
        await services.levels.remove_xp(player.player_id, 50, reason="c")

    assert await services.levels.get_xp(player.player_id) == 40


# --- 8. Player status calculation ----------------------------------------


async def test_player_status_calculation_includes_progress(services, register):
    player = await register(tg_id=6015)
    await services.levels.add_xp(player.player_id, 50, reason="half")

    status = await services.players.get_status(6015)
    assert status is not None
    assert status.level == 1
    assert status.xp == 50
    assert status.xp_in_current_level == 50
    assert status.xp_needed_for_next == 100
    assert status.progress_percent == 50.0
    assert status.total_xp_for_next_level == 100


async def test_profile_includes_progress_fields(services, register):
    player = await register(tg_id=6016)
    await services.levels.add_xp(player.player_id, 100, reason="level 2")

    profile = await services.players.get_profile(6016)
    assert profile is not None
    assert profile.level == 2
    assert profile.xp == 100
    assert profile.xp_in_current_level == 0
    assert profile.xp_needed_for_next == xp_for_level_up(2)  # 135
    assert profile.progress_percent == 0.0


async def test_progress_percentage_calculation(services, register):
    player = await register(tg_id=6017)
    # Level 1: 0/100, Level 2: 0/135, etc.
    await services.levels.add_xp(player.player_id, 150, reason="test")

    # 150 total: level 2 (100 needed for L2), 50 into L2, needs 135 for next
    progress = await services.levels.get_progress(player.player_id)
    assert progress.level == 2
    assert progress.total_xp == 150
    assert progress.xp_in_current_level == 50
    assert progress.xp_needed_for_next == 135
    assert progress.total_xp_for_current_level == 100
    assert progress.total_xp_for_next_level == 235
    # 50/135 ≈ 37.037%
    assert abs(progress.progress_percent - (50 / 135 * 100)) < 0.01


async def test_required_xp_for_next_level(services, register):
    player = await register(tg_id=6018)
    req = await services.levels.get_required_xp_for_next_level(player.player_id)
    assert req == 100  # Level 1 needs 100

    await services.levels.add_xp(player.player_id, 100, reason="up")
    req2 = await services.levels.get_required_xp_for_next_level(player.player_id)
    assert req2 == 135  # Level 2 needs 135


# --- 9. Database persistence ---------------------------------------------


async def test_xp_and_level_persist_across_sessions(db, services, register):
    player = await register(tg_id=6019)
    await services.levels.add_xp(player.player_id, 250, reason="persist test")

    # Create new service registry with same DB (simulating restart)
    from app.services import ServiceRegistry

    new_services = ServiceRegistry(db.session_factory)

    # Data should survive
    assert await new_services.levels.get_xp(player.player_id) == 250
    level = await new_services.levels.get_level(player.player_id)
    assert level == level_from_total_xp(250)

    history = await new_services.levels.get_xp_history(player.player_id)
    assert len(history) == 1
    assert history[0].amount == 250


async def test_xp_history_persists(db, services, register):
    player = await register(tg_id=6020)
    await services.levels.add_xp(player.player_id, 10, reason="a")
    await services.levels.add_xp(player.player_id, 20, reason="b")
    await services.levels.remove_xp(player.player_id, 5, reason="c")

    from app.services import ServiceRegistry

    new_services = ServiceRegistry(db.session_factory)
    history = await new_services.levels.get_xp_history(player.player_id, limit=10)
    assert len(history) == 3
    amounts = sorted([h.amount for h in history])
    assert amounts == [-5, 10, 20]


async def test_level_up_history_persists(db, services, register):
    player = await register(tg_id=6021)
    await services.levels.add_xp(player.player_id, 100, reason="to 2")
    await services.levels.add_xp(player.player_id, 135, reason="to 3")

    from app.services import ServiceRegistry

    new_services = ServiceRegistry(db.session_factory)
    level_history = await new_services.levels.get_level_up_history(
        player.player_id, limit=10
    )
    assert len(level_history) == 2
    # Check old/new levels are stored
    levels = sorted([(h.old_level, h.new_level) for h in level_history])
    assert (1, 2) in levels
    assert (2, 3) in levels


# --- Additional edge cases ------------------------------------------------


async def test_set_level_admin_helper(services, register):
    player = await register(tg_id=6022)

    result = await services.levels.set_level(player.player_id, 5, reason="admin")
    assert result.new_level == 5
    assert result.xp_after == total_xp_for_level(5)
    assert await services.levels.get_level(player.player_id) == 5

    # Set to lower level
    result2 = await services.levels.set_level(player.player_id, 2, reason="admin down")
    assert result2.new_level == 2
    assert result2.xp_after == total_xp_for_level(2)
    assert await services.levels.get_level(player.player_id) == 2


async def test_add_xp_reason_is_cleaned_and_limited(services, register):
    player = await register(tg_id=6023)

    long_reason = "a" * 200
    result = await services.levels.add_xp(player.player_id, 10, reason=long_reason)

    # Should be truncated to MAX_XP_REASON_LENGTH (128)
    assert len(result.reason) == 128

    # Whitespace cleaning
    result2 = await services.levels.add_xp(
        player.player_id, 10, reason="  multiple   spaces  \n test  "
    )
    assert result2.reason == "multiple spaces test"


async def test_level_progress_pure_function_edge_cases():
    # Zero XP
    p0 = get_level_progress(0)
    assert p0.level == 1
    assert p0.progress_percent == 0.0

    # Exactly at level boundary
    xp_l2 = total_xp_for_level(2)
    p_l2 = get_level_progress(xp_l2)
    assert p_l2.level == 2
    assert p_l2.xp_in_current_level == 0

    # Just before level up
    p_before = get_level_progress(xp_l2 + xp_for_level_up(2) - 1)
    assert p_before.level == 2
    assert p_before.xp_in_current_level == xp_for_level_up(2) - 1
    assert p_before.progress_percent < 100.0
    assert p_before.progress_percent > 99.0
