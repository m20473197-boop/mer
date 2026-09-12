"""Async database engine and session management.

The connection URL drives everything: the default is SQLite (via
``aiosqlite``), and moving to PostgreSQL later only requires changing
``DATABASE_URL`` in the environment — no game code changes needed.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.database import models as _models  # noqa: F401  (registers all ORM models)
from app.database.models.base import Base
from app.game.housing.construction_year import current_iranian_year

logger = logging.getLogger(__name__)

_SQLITE_PREFIX = "sqlite"
_MEMORY_MARKER = ":memory:"

# Additive column migrations for existing SQLite databases. ``create_all`` only
# creates *missing tables* — it never alters existing ones — so when a model
# gains a column we must backfill it with an idempotent ``ALTER TABLE ... ADD
# COLUMN``. Keys are table names; values are (column_name, column_definition).
_SQLITE_COLUMN_MIGRATIONS: dict[str, list[tuple[str, str]]] = {
    # The time-based salary system added these to the existing jobs table.
    "jobs": [
        ("hourly_salary", "BIGINT NOT NULL DEFAULT 0"),
        ("employer", "VARCHAR(64) NOT NULL DEFAULT ''"),
    ],
    # The admin panel added the ban flag to players and per-property price
    # overrides (per-mille scale factors, NULL = purely dynamic price).
    "players": [
        ("is_banned", "BOOLEAN NOT NULL DEFAULT 0"),
        # The Marriage and Family system added the denormalized family
        # pointers (the authoritative rows are the new ``marriages`` table).
        ("spouse_player_id", "BIGINT"),
        ("marriage_id", "BIGINT"),
        ("married_since", "DATETIME"),
        ("children_count", "INTEGER NOT NULL DEFAULT 0"),
    ],
    "houses": [
        ("price_override_per_mille", "INTEGER"),
    ],
    "lands": [
        ("price_override_per_mille", "INTEGER"),
    ],
}

# Column renames for existing SQLite databases: (table, old_name, new_name).
# Applied idempotently — only when the old column exists and the new one
# does not.
_SQLITE_COLUMN_RENAMES: tuple[tuple[str, str, str], ...] = (
    # The construction-year update: stored building age → construction year.
    ("houses", "building_age_years", "construction_year"),
)

# Construction years are Solar-Hijri (≥ 1330); anything below this threshold
# in the renamed column is a stale *age* from the old system and must be
# converted to a construction year exactly once.
_CONSTRUCTION_YEAR_THRESHOLD: int = 1330


class Database:
    """Owns the async engine and the session factory for the whole app."""

    def __init__(self, database_url: str, *, echo: bool = False) -> None:
        self._database_url = database_url
        self._ensure_sqlite_parent_dir(database_url)

        engine_kwargs: dict = {"echo": echo}
        if database_url.startswith(_SQLITE_PREFIX) and _MEMORY_MARKER in database_url:
            # Share a single in-memory database across connections (tests).
            engine_kwargs["poolclass"] = StaticPool

        self._engine: AsyncEngine = create_async_engine(database_url, **engine_kwargs)
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
            autoflush=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    async def create_all(self) -> None:
        """Create any missing tables and apply additive column migrations.

        Existing tables and rows are never dropped or recreated, so player
        data safely survives bot restarts. Column renames (e.g. the
        construction-year update of ``houses``) run before the additive
        backfills so the schema is consistent within one startup.
        """
        async with self._engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        if self._database_url.startswith(_SQLITE_PREFIX):
            await self._rename_columns()
            await self._add_missing_columns()
            await self._convert_building_ages_to_construction_years()

    async def _rename_columns(self) -> None:
        """Rename columns on existing SQLite tables (idempotent)."""
        async with self._engine.begin() as connection:
            for table_name, old_name, new_name in _SQLITE_COLUMN_RENAMES:
                existing = await self._existing_columns(connection, table_name)
                if not existing:
                    continue  # Table does not exist yet — create_all handles it.
                if old_name in existing and new_name not in existing:
                    await connection.exec_driver_sql(
                        f"ALTER TABLE {table_name} RENAME COLUMN {old_name} TO {new_name}"
                    )
                    logger.info(
                        "Migrated %s: column %s renamed to %s",
                        table_name,
                        old_name,
                        new_name,
                    )

    async def _convert_building_ages_to_construction_years(self) -> None:
        """Convert stale stored ages into real construction years (once).

        After the ``building_age_years`` → ``construction_year`` rename, the
        renamed column still holds the old ages (0…~100). Real construction
        years are Solar-Hijri (≥ 1330), so a single guarded UPDATE converts
        every stale age exactly ``current_iranian_year() − age`` and stays
        a no-op on databases that already hold proper years.
        """
        async with self._engine.begin() as connection:
            existing = await self._existing_columns(connection, "houses")
            if "construction_year" not in existing:
                return
            current_year = current_iranian_year()
            result = await connection.exec_driver_sql(
                f"UPDATE houses SET construction_year = {current_year} - construction_year "
                f"WHERE construction_year < {_CONSTRUCTION_YEAR_THRESHOLD}"
            )
            converted = result.rowcount
            if converted:
                logger.info(
                    "Migrated houses: %s stored building ages converted to "
                    "construction years (base year %s)",
                    converted,
                    current_year,
                )

    async def _add_missing_columns(self) -> None:
        """Backfill new columns on existing SQLite tables (idempotent)."""
        async with self._engine.begin() as connection:
            for table_name, columns in _SQLITE_COLUMN_MIGRATIONS.items():
                existing = await self._existing_columns(connection, table_name)
                if not existing:
                    continue  # Table does not exist yet — create_all handles it.
                for column_name, column_ddl in columns:
                    if column_name in existing:
                        continue
                    await connection.exec_driver_sql(
                        f"ALTER TABLE {table_name} "
                        f"ADD COLUMN {column_name} {column_ddl}"
                    )

    @staticmethod
    async def _existing_columns(connection, table_name: str) -> set[str]:
        """The column names of ``table_name`` (empty set if it doesn't exist)."""
        return {
            row[1]
            for row in (
                await connection.exec_driver_sql(f"PRAGMA table_info({table_name})")
            ).fetchall()
        }

    async def dispose(self) -> None:
        """Close all connections (called on shutdown)."""
        await self._engine.dispose()

    @staticmethod
    def _ensure_sqlite_parent_dir(url: str) -> None:
        if not url.startswith(_SQLITE_PREFIX):
            return
        path_part = url.split("///", 1)[-1]
        if not path_part or _MEMORY_MARKER in path_part:
            return
        Path(path_part).parent.mkdir(parents=True, exist_ok=True)
