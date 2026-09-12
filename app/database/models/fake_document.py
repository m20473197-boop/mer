"""Fictional documents owned by players."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base

DOCUMENT_ACTIVE = "active"
DOCUMENT_EXPIRED = "expired"
DOCUMENT_REVOKED = "revoked"


class FakeDocument(Base):
    __tablename__ = "fake_documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'expired', 'revoked')",
            name="ck_fake_documents_status",
        ),
        Index(
            "uq_fake_documents_active_owner_type",
            "owner_player_id",
            "document_type",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_fake_documents_owner_created", "owner_player_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("crime_activities.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    owner_player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DOCUMENT_ACTIVE, server_default=text("'active'")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
