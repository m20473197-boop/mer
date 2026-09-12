"""Configuration guard tests."""

from __future__ import annotations

import pytest

from app.core.config import ConfigError, load_database_url, load_settings


def test_missing_bot_token_fails_clearly(monkeypatch, tmp_path):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    with pytest.raises(ConfigError, match="BOT_TOKEN"):
        load_settings(env_file=tmp_path / "nonexistent.env")


def test_settings_load_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_TOKEN", "123456:ABC-test-token")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    settings = load_settings(env_file=tmp_path / "nonexistent.env")

    assert settings.bot_token == "123456:ABC-test-token"
    assert settings.log_level == "INFO"
    assert settings.database_url.startswith("sqlite+aiosqlite:///")


def test_relative_sqlite_url_is_anchored_to_project_root(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///data/custom.db")
    monkeypatch.delenv("BOT_TOKEN", raising=False)

    url = load_database_url(env_file=tmp_path / "nonexistent.env")

    assert url.endswith("/data/custom.db")
    assert not url.startswith("sqlite+aiosqlite:///data")
