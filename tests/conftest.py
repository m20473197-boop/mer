"""Shared pytest fixtures for the test suite."""

from __future__ import annotations

from typing import Awaitable, Callable

import pytest

from app.database.database import Database
from app.game.player.dto import RegistrationResult
from app.services import ServiceRegistry


@pytest.fixture
async def db(tmp_path) -> Database:
    """A fresh file-backed SQLite database per test (like production)."""
    database = Database(f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    await database.create_all()
    yield database
    await database.dispose()


@pytest.fixture
async def services(db: Database) -> ServiceRegistry:
    registry = ServiceRegistry(db.session_factory)
    # Seed initial jobs for Job system tests
    await registry.jobs.ensure_initial_jobs()
    return registry


@pytest.fixture
def register(services: ServiceRegistry) -> Callable[..., Awaitable[RegistrationResult]]:
    """Convenience factory: register a player with sensible defaults."""

    async def _register(
        tg_id: int,
        username: str | None = "ali",
        display_name: str = "علی",
    ) -> RegistrationResult:
        return await services.players.register_or_get(
            telegram_user_id=tg_id,
            username=username,
            display_name=display_name,
        )

    return _register
