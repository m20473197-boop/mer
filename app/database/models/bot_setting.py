"""BotSetting ORM model — persistent admin-tunable bot configuration."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class BotSetting(Base):
    """One key/value bot setting, managed from the admin panel.

    Keys are defined in ``app.game.admin.runtime`` (``KEY_*`` / feature
    flags). Values are stored as short strings and parsed by the service
    layer; the runtime cache (``app.game.admin.runtime``) mirrors them for
    synchronous call sites.

    Fields:
        key: Primary key (e.g. ``market_conditions``, ``jobs_enabled``).
        value: The stored value as text (e.g. ``1.25``, ``0``).
        updated_at: Last change (UTC).
    """

    __tablename__ = "bot_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(512), nullable=False, default="")

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover — debugging aid only
        return f"<BotSetting key={self.key!r} value={self.value!r}>"
