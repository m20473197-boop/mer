"""Additive column-migration tests — old databases gain new job columns."""

# Also covers what happens to the old selectable jobs when the «خر حمالی»
# catalog replaces them.

from __future__ import annotations

import sqlite3

from app.database.database import Database
from app.database.repositories.job_repository import JobRepository


def _create_old_schema_jobs(db_path: str) -> None:
    """Recreate the pre-update ``jobs`` table shape (no hourly_salary/employer)."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE jobs (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(64) NOT NULL UNIQUE,
            description VARCHAR(256) NOT NULL,
            salary BIGINT NOT NULL,
            cooldown INTEGER NOT NULL,
            required_level INTEGER NOT NULL,
            required_skill VARCHAR(64),
            is_active BOOLEAN NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "INSERT INTO jobs (name, description, salary, cooldown, required_level, "
        "is_active) VALUES ('کارگر', 'کار ساده با درآمد کم', 50000, 300, 1, 1)"
    )
    conn.commit()
    conn.close()


async def test_existing_database_gains_new_job_columns(tmp_path):
    db_path = tmp_path / "old.db"
    _create_old_schema_jobs(db_path.as_posix())

    database = Database(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    await database.create_all()

    async with database.engine.begin() as connection:
        columns = {
            row[1]
            for row in (
                await connection.exec_driver_sql("PRAGMA table_info(jobs)")
            ).fetchall()
        }
        assert "hourly_salary" in columns
        assert "employer" in columns

    await database.dispose()


async def test_legacy_job_rows_are_backfilled_then_deactivated(tmp_path):
    """Old rows are kept and made whole, then switched off — never deleted.

    A player who was mid-shift at «کارگر» must not end up with a zero-hours
    contract just because the catalog changed underneath them.
    """
    db_path = tmp_path / "old.db"
    _create_old_schema_jobs(db_path.as_posix())

    database = Database(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    await database.create_all()

    from app.core import constants
    from app.services import ServiceRegistry

    services = ServiceRegistry(database.session_factory)
    jobs = await services.jobs.ensure_initial_jobs()

    # The new catalog is seeded next to the old row…
    assert len(jobs) == 6

    # …the legacy job is no longer offered, but its row and its data survive.
    assert "کارگر" not in {j.name for j in jobs}
    async with database.session_factory() as session:
        legacy = await JobRepository(session).get_by_name("کارگر")
    assert legacy is not None
    assert legacy.is_active is False
    expected_hourly, expected_employer = constants.JOB_LEGACY_COMPAT["کارگر"]
    assert legacy.hourly_salary == expected_hourly
    assert legacy.employer == expected_employer

    # Whatever the old row already had is left alone.
    assert legacy.salary == 50_000
    assert legacy.description == "کار ساده با درآمد کم"
    assert legacy.cooldown == 300
    assert legacy.required_level == 1

    await database.dispose()
