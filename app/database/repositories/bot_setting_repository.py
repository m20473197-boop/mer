"""Repository for the ``bot_settings`` table (admin-tuned configuration)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.bot_setting import BotSetting


class BotSettingRepository:
    """All database operations for bot settings."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reads ------------------------------------------------------------

    async def get(self, key: str) -> str | None:
        setting = await self._session.get(BotSetting, key)
        return setting.value if setting is not None else None

    async def get_all(self) -> dict[str, str]:
        result = await self._session.execute(select(BotSetting))
        return {row.key: row.value for row in result.scalars().all()}

    # --- Writes ------------------------------------------------------------

    async def set(self, key: str, value: str) -> BotSetting:
        """Upsert one setting; the owning service commits the transaction."""
        setting = await self._session.get(BotSetting, key)
        if setting is None:
            setting = BotSetting(key=key, value=value)
            self._session.add(setting)
        else:
            setting.value = value
            self._session.add(setting)
        await self._session.flush()
        return setting
