"""Database persistence tests — player data must survive a restart."""

from __future__ import annotations

from app.database.database import Database
from app.services import ServiceRegistry


async def test_player_data_survives_restart(tmp_path):
    """Two full lifecycle cycles on the same DB file (bot restart simulation)."""
    db_path = tmp_path / "persist.db"
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"

    # --- First run: register, gain XP, earn money -------------------------
    database = Database(url)
    await database.create_all()
    registry = ServiceRegistry(database.session_factory)
    created = await registry.players.register_or_get(
        telegram_user_id=6001, username="mmd", display_name="ممد"
    )
    assert created.created is True
    await registry.levels.add_xp(created.player_id, 150)
    await registry.money.add_money(created.player_id, 9_999)
    await database.dispose()

    # --- Second run ("restart"): same DB file, fresh engine ---------------
    database = Database(url)
    await database.create_all()  # must be a no-op for existing tables
    registry = ServiceRegistry(database.session_factory)
    again = await registry.players.register_or_get(
        telegram_user_id=6001, username="mmd", display_name="ممد"
    )

    assert again.created is False  # NOT registered twice
    assert again.player_id == created.player_id
    assert again.profile.level == 2
    assert again.profile.xp == 150
    assert again.profile.money == 9_999
    await database.dispose()
