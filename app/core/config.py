"""Application configuration.

Secrets (the bot token above all) never live in code — they are read from
environment variables, optionally backed by a local ``.env`` file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from app.core import constants

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

_DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///data/iran_life_bot.db"
_SQLITE_URL_PREFIX = "sqlite+aiosqlite:///"


class ConfigError(RuntimeError):
    """Raised when the configuration is invalid or incomplete."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable runtime settings."""

    bot_token: str
    database_url: str
    log_level: str
    admin_ids: tuple[int, ...]


def _parse_admin_ids(raw: str) -> tuple[int, ...]:
    """Parse comma-separated admin IDs, e.g. '123,456,789'."""
    if not raw.strip():
        return ()
    ids: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            # Ignore invalid entries but log later if needed
            continue
    return tuple(ids)


def load_settings(env_file: Path | None = None) -> Settings:
    """Load settings from the environment (and an optional ``.env`` file).

    Raises:
        ConfigError: If the mandatory bot token is missing.
    """
    load_dotenv(env_file if env_file is not None else PROJECT_ROOT / ".env")

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise ConfigError(
            "BOT_TOKEN is not set. "
            "Copy .env.example to .env and paste the token you got from @BotFather."
        )

    database_url = load_database_url(env_file=env_file)
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"
    admin_ids_raw = os.getenv("ADMIN_IDS", "").strip()
    # Fall back to the canonical owner ID so the panel always has an admin.
    admin_ids = _parse_admin_ids(admin_ids_raw) or constants.ADMIN_TELEGRAM_IDS

    return Settings(
        bot_token=bot_token,
        database_url=database_url,
        log_level=log_level,
        admin_ids=admin_ids,
    )


def load_database_url(env_file: Path | None = None) -> str:
    """Resolve the database URL without requiring a bot token.

    Useful for maintenance scripts (e.g. initializing the database).
    """
    load_dotenv(env_file if env_file is not None else PROJECT_ROOT / ".env")
    raw = os.getenv("DATABASE_URL", "").strip() or _DEFAULT_DATABASE_URL
    return _resolve_sqlite_path(raw)


def _resolve_sqlite_path(url: str) -> str:
    """Anchor relative SQLite paths to the project root (cwd-independent)."""
    if not url.startswith(_SQLITE_URL_PREFIX):
        return url
    path_part = url[len(_SQLITE_URL_PREFIX):]
    if not path_part or path_part.startswith("/"):
        return url
    absolute = (PROJECT_ROOT / path_part).resolve()
    return f"{_SQLITE_URL_PREFIX}{absolute.as_posix()}"
