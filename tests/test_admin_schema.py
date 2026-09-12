"""Admin-panel schema tests — new tables and additive column migrations.

Old databases (created before the admin panel) gain the new columns without
losing a single row; new tables are created by the same ``create_all``.
"""

from __future__ import annotations

import sqlite3

from app.database.database import Database


def _create_pre_admin_schema(db_path: str) -> None:
    """Recreate the pre-admin-panel table shapes (no ban flag / overrides)."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE players (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            telegram_user_id BIGINT NOT NULL UNIQUE,
            username VARCHAR(32),
            display_name VARCHAR(64) NOT NULL,
            level INTEGER NOT NULL,
            xp INTEGER NOT NULL,
            money BIGINT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "INSERT INTO players (telegram_user_id, display_name, level, xp, money) "
        "VALUES (700001, 'قدیمی', 3, 250, 500000)"
    )
    conn.execute(
        """
        CREATE TABLE houses (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            city VARCHAR(64) NOT NULL,
            neighborhood VARCHAR(64) NOT NULL,
            area_sqm INTEGER NOT NULL,
            bedrooms INTEGER NOT NULL,
            living_rooms INTEGER NOT NULL,
            bathrooms INTEGER NOT NULL,
            kitchen_type VARCHAR(32) NOT NULL,
            construction_year INTEGER NOT NULL,
            parking BOOLEAN NOT NULL,
            elevator BOOLEAN NOT NULL,
            storage BOOLEAN NOT NULL,
            quality VARCHAR(32) NOT NULL,
            owner_player_id BIGINT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE lands (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            city VARCHAR(64) NOT NULL,
            neighborhood VARCHAR(64) NOT NULL,
            area_sqm INTEGER NOT NULL,
            location_quality VARCHAR(16) NOT NULL,
            owner_player_id BIGINT,
            built_house_id BIGINT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


async def _columns(database: Database, table: str) -> set[str]:
    async with database.engine.begin() as connection:
        rows = (
            await connection.exec_driver_sql(f"PRAGMA table_info({table})")
        ).fetchall()
        return {row[1] for row in rows}


async def test_old_database_gains_admin_columns(tmp_path):
    db_path = tmp_path / "old.db"
    _create_pre_admin_schema(db_path.as_posix())

    database = Database(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    await database.create_all()

    assert "is_banned" in await _columns(database, "players")
    assert "price_override_per_mille" in await _columns(database, "houses")
    assert "price_override_per_mille" in await _columns(database, "lands")
    # New admin/economy tables exist too.
    for table in (
        "bot_settings",
        "market_assets",
        "market_price_ticks",
        "economic_events",
        "admin_audit_logs",
    ):
        assert await _columns(database, table), table

    await database.dispose()


async def test_old_rows_survive_with_sane_defaults(tmp_path):
    db_path = tmp_path / "old.db"
    _create_pre_admin_schema(db_path.as_posix())

    database = Database(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    await database.create_all()

    from app.services import ServiceRegistry

    services = ServiceRegistry(database.session_factory)
    profile = await services.players.get_profile(700001)
    assert profile is not None
    assert (profile.level, profile.xp, profile.money) == (3, 250, 500000)

    detail = await services.admin.get_user_detail(1)
    assert detail.summary.is_banned is False

    await database.dispose()


async def test_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "old.db"
    _create_pre_admin_schema(db_path.as_posix())

    database = Database(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    await database.create_all()
    await database.create_all()  # second boot must be a no-op

    assert "is_banned" in await _columns(database, "players")
    await database.dispose()
