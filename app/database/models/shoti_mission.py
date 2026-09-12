"""Persisted fictional شوتی missions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base

SHOTI_PENDING = "pending"
SHOTI_PROCESSING = "processing"
SHOTI_COMPLETED = "completed"
SHOTI_FAILED = "failed"
SHOTI_CANCELLED = "cancelled"


class ShotiMission(Base):
    __tablename__ = "shoti_missions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')",
            name="ck_shoti_missions_status",
        ),
        CheckConstraint("reward >= 0", name="ck_shoti_missions_reward_nonnegative"),
        CheckConstraint("difficulty BETWEEN 0 AND 100", name="ck_shoti_missions_difficulty"),
        CheckConstraint("risk BETWEEN 0 AND 100", name="ck_shoti_missions_risk"),
        CheckConstraint("duration_seconds >= 0", name="ck_shoti_missions_duration"),
        Index(
            "uq_shoti_active_player",
            "player_id",
            unique=True,
            sqlite_where=text("status IN ('pending', 'processing')"),
            postgresql_where=text("status IN ('pending', 'processing')"),
        ),
        Index("ix_shoti_player_started", "player_id", "started_at"),
        Index("ix_shoti_due", "status", "completes_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("crime_activities.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vehicle_ownership_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("vehicle_ownerships.id", ondelete="RESTRICT"), nullable=False
    )
    vehicle_model_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("vehicle_models.id", ondelete="RESTRICT"), nullable=False
    )
    vehicle_name: Mapped[str] = mapped_column(String(128), nullable=False)
    origin: Mapped[str] = mapped_column(String(64), nullable=False)
    destination: Mapped[str] = mapped_column(String(64), nullable=False)
    shipment: Mapped[str] = mapped_column(Text, nullable=False)
    reward: Mapped[int] = mapped_column(BigInteger, nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False)
    risk: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SHOTI_PENDING, server_default=text("'pending'")
    )
    success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reward_paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
