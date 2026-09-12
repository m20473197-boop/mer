"""Land / Construction / Renovation schema tests.

Old databases (even pre-housing ones) gain the five new tables on first run
after the update; nothing existing is dropped or altered.
"""

from __future__ import annotations

import sqlite3

from sqlalchemy import BigInteger

from app.database.database import Database
from app.database.models.construction_project import ConstructionProject
from app.database.models.land import Land
from app.database.models.renovation_project import RenovationProject

RE_TABLES = (
    "lands",
    "land_transactions",
    "construction_projects",
    "renovation_projects",
    "property_upgrades",
)


def _create_pre_housing_schema(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE players (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            telegram_user_id BIGINT NOT NULL,
            username VARCHAR(32),
            display_name VARCHAR(64) NOT NULL,
            level INTEGER NOT NULL,
            xp INTEGER NOT NULL,
            money BIGINT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (telegram_user_id)
        )
        """
    )
    conn.execute(
        "INSERT INTO players (telegram_user_id, display_name, level, xp, money) "
        "VALUES (777000, 'قدیمی', 1, 0, 5000)"
    )
    conn.commit()
    conn.close()


async def test_old_database_gains_all_realestate_tables(tmp_path):
    db_path = tmp_path / "old.db"
    _create_pre_housing_schema(db_path.as_posix())

    database = Database(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    try:
        await database.create_all()

        conn = sqlite3.connect(db_path.as_posix())
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        finally:
            conn.close()

        for table in RE_TABLES:
            assert table in tables, f"missing table after upgrade: {table}"

        # The old player row survived untouched.
        conn = sqlite3.connect(db_path.as_posix())
        try:
            rows = conn.execute("SELECT telegram_user_id, money FROM players").fetchall()
        finally:
            conn.close()
        assert rows == [(777000, 5000)]
    finally:
        await database.dispose()


async def test_land_and_project_shapes():
    land_columns = {column.name: column for column in Land.__table__.columns}
    assert land_columns["id"].primary_key                     # unique land ID
    assert land_columns["owner_player_id"].nullable           # market parcels unowned
    assert land_columns["built_house_id"].nullable            # vacant until built
    assert not land_columns["area_sqm"].nullable              # size is mandatory
    assert not land_columns["location_quality"].nullable

    project_columns = {
        column.name: column for column in ConstructionProject.__table__.columns
    }
    # Money and durations stay exact integers — never floats.
    assert isinstance(project_columns["cost_total"].type, BigInteger)
    assert isinstance(project_columns["duration_seconds"].type, BigInteger)
    assert not project_columns["completes_at"].nullable       # time-based core

    renovation_columns = {
        column.name: column for column in RenovationProject.__table__.columns
    }
    assert isinstance(renovation_columns["cost"].type, BigInteger)
    assert not renovation_columns["completes_at"].nullable


async def test_create_all_is_idempotent_with_realestate(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{(tmp_path / 'twice.db').as_posix()}")
    try:
        await database.create_all()
        await database.create_all()  # second run must be a no-op, not an error
    finally:
        await database.dispose()
