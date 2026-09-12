"""Profile and status data retrieval tests."""

from __future__ import annotations

from app.game.player.dto import StatusData


async def test_profile_data_retrieval(services, register):
    created = await register(tg_id=5001, username="@kobra", display_name="کبری")

    profile = await services.players.get_profile(5001)

    assert profile == created.profile
    assert profile is not None
    assert profile.display_name == "کبری"
    assert profile.level == 1
    assert profile.xp == 0
    assert profile.money == 0


async def test_profile_reflects_changes(services, register):
    player = await register(tg_id=5002)
    await services.levels.add_xp(player.player_id, 10)
    await services.money.add_money(player.player_id, 750)

    profile = await services.players.get_profile(5002)

    assert profile is not None
    assert profile.xp == 10
    assert profile.money == 750


async def test_profile_for_unknown_user_is_none(services):
    assert await services.players.get_profile(999_999_999) is None


async def test_status_data_retrieval(services, register):
    await register(tg_id=5003)

    status = await services.players.get_status(5003)

    assert status is not None
    assert status.level == 1
    assert status.xp == 0
    assert status.money == 0
    # New progression fields should be populated
    assert status.xp_needed_for_next == 100
    assert status.xp_in_current_level == 0
    assert status.progress_percent == 0.0
    # Also check equality with explicit expected extended values still works via attributes
    # (old test used full equality, now we check core fields)


async def test_status_is_separate_type_from_profile(services, register):
    await register(tg_id=5004)

    status = await services.players.get_status(5004)
    profile = await services.players.get_profile(5004)

    assert status is not None and profile is not None
    assert type(status) is not type(profile)
    assert not hasattr(status, "display_name")


async def test_status_for_unknown_user_is_none(services):
    assert await services.players.get_status(999_999_999) is None
