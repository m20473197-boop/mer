"""Migration tests — stored building ages become construction years.

Old databases hold ``houses.building_age_years`` (an age in years). After
``create_all`` the column must be renamed to ``construction_year`` and every
stored age converted to ``current_iranian_year() − age`` — once, safely, with
all other data preserved.
"""

from __future__ import annotations

import sqlite3

from app.database.database import Database
from app.game.housing.construction_year import current_iranian_year


def _create_old_schema_houses(db_path: str) -> None:
    """Recreate the pre-update ``houses`` table shape (building_age_years)."""
    conn = sqlite3.connect(db_path)
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
            building_age_years INTEGER NOT NULL,
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
    # A 10-year-old house (the spec example), a brand-new one and an old one.
    conn.execute(
        "INSERT INTO houses (city, neighborhood, area_sqm, bedrooms, living_rooms, "
        "bathrooms, kitchen_type, building_age_years, parking, elevator, storage, quality) "
        "VALUES ('تهران', 'ونک', 80, 2, 1, 1, 'معمولی', 10, 1, 1, 0, 'خوب')"
    )
    conn.execute(
        "INSERT INTO houses (city, neighborhood, area_sqm, bedrooms, living_rooms, "
        "bathrooms, kitchen_type, building_age_years, parking, elevator, storage, quality) "
        "VALUES ('مشهد', 'سجاد', 60, 1, 1, 1, 'مدرن', 0, 0, 1, 1, 'عالی')"
    )
    conn.execute(
        "INSERT INTO houses (city, neighborhood, area_sqm, bedrooms, living_rooms, "
        "bathrooms, kitchen_type, building_age_years, parking, elevator, storage, quality) "
        "VALUES ('تبریز', 'ولیعصر', 120, 3, 1, 2, 'قدیمی', 30, 1, 0, 0, 'ضعیف')"
    )
    conn.commit()
    conn.close()


async def test_old_database_gains_construction_year_with_data(tmp_path):
    db_path = tmp_path / "old.db"
    _create_old_schema_houses(db_path.as_posix())

    database = Database(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    try:
        await database.create_all()

        conn = sqlite3.connect(db_path.as_posix())
        try:
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(houses)").fetchall()
            }
            rows = conn.execute(
                "SELECT city, area_sqm, construction_year, quality FROM houses "
                "ORDER BY id"
            ).fetchall()
        finally:
            conn.close()

        # The old column is gone; the new one exists.
        assert "building_age_years" not in columns
        assert "construction_year" in columns

        # Ages became construction years (10 → year−10, etc.), data preserved.
        this_year = current_iranian_year()
        assert rows == [
            ("تهران", 80, this_year - 10, "خوب"),
            ("مشهد", 60, this_year - 0, "عالی"),
            ("تبریز", 120, this_year - 30, "ضعیف"),
        ]
    finally:
        await database.dispose()


async def test_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "old.db"
    _create_old_schema_houses(db_path.as_posix())

    database = Database(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    try:
        await database.create_all()
        await database.create_all()  # second boot: no double conversion
        await database.create_all()  # and a third for good measure

        conn = sqlite3.connect(db_path.as_posix())
        try:
            rows = conn.execute(
                "SELECT construction_year FROM houses ORDER BY id"
            ).fetchall()
        finally:
            conn.close()

        this_year = current_iranian_year()
        assert [r[0] for r in rows] == [this_year - 10, this_year, this_year - 30]
    finally:
        await database.dispose()


async def test_fresh_database_has_construction_year_directly(tmp_path):
    database = Database(
        f"sqlite+aiosqlite:///{(tmp_path / 'fresh.db').as_posix()}"
    )
    try:
        await database.create_all()
        from app.database.repositories.house_repository import HouseRepository

        async with database.session_factory() as session:
            house = await HouseRepository(session).create(
                city="تهران",
                neighborhood="نارمک",
                area_sqm=90,
                bedrooms=2,
                living_rooms=1,
                bathrooms=1,
                kitchen_type="معمولی",
                construction_year=current_iranian_year(),
                parking=True,
                elevator=False,
                storage=False,
                quality="خوب",
            )
            await session.commit()
            assert house.construction_year == current_iranian_year()
    finally:
        await database.dispose()
