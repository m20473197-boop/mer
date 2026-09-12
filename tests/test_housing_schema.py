"""Housing schema tests — new tables appear on old databases, shapes hold.

The bot never drops or alters existing data; ``create_all`` only adds the
missing ``houses`` / ``house_listings`` / ``house_sales`` /
``rental_contracts`` / ``house_transactions`` tables on first run after the
housing update.
"""

from __future__ import annotations

import sqlite3

from sqlalchemy import BigInteger

from app.database.database import Database
from app.database.models.house import House
from app.database.models.house_transaction import HouseTransaction


HOUSING_TABLES = (
    "houses",
    "house_listings",
    "house_sales",
    "rental_contracts",
    "house_transactions",
)


def _create_pre_housing_schema(db_path: str) -> None:
    """A database from before the housing update (only the players table)."""
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
        "VALUES (555000, 'قدیمی', 1, 0, 1000)"
    )
    conn.commit()
    conn.close()


async def test_old_database_gains_all_housing_tables(tmp_path):
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

        for table in HOUSING_TABLES:
            assert table in tables, f"missing table after upgrade: {table}"

        # The old player row survived untouched.
        conn = sqlite3.connect(db_path.as_posix())
        try:
            rows = conn.execute("SELECT telegram_user_id, money FROM players").fetchall()
        finally:
            conn.close()
        assert rows == [(555000, 1000)]
    finally:
        await database.dispose()


async def test_houses_unique_id_primary_key_and_ownership_nullable():
    columns = {column.name: column for column in House.__table__.columns}
    assert columns["id"].primary_key
    assert columns["owner_player_id"].nullable  # system-market houses are unowned


def test_house_prices_stay_exact_integers():
    """Listing prices, deposits and rents are BigInteger — never floats."""
    from app.database.models.house_listing import HouseListing
    from app.database.models.rental_contract import RentalContract

    for model in (HouseListing, RentalContract, HouseTransaction):
        for name in ("price", "deposit", "monthly_rent", "amount"):
            column = model.__table__.columns.get(name)
            if column is not None:
                assert isinstance(column.type, BigInteger), (
                    f"{model.__tablename__}.{name} must be an exact integer"
                )


def test_housing_seeding_is_deterministic():
    from app.game.housing.seeding import build_seed_specs

    first = build_seed_specs()
    second = build_seed_specs()
    assert first == second
    assert all(spec.city and spec.neighborhood for spec in first)
