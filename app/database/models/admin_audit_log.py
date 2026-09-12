"""AdminAuditLog ORM model — the immutable trail of every admin action."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class AdminAuditLog(Base):
    """One logged admin action.

    Every mutating admin-panel operation writes exactly one row here, inside
    the same transaction as the change itself whenever possible, so the log
    can never drift from reality. Rows are append-only (only the 🗄 cleanup
    tools may prune very old rows).

    Fields:
        id: Primary key.
        admin_telegram_id: The admin's Telegram user ID.
        action: Machine action name (e.g. ``user_add_money``, ``job_create``).
        target_type: What was touched (``player``/``house``/``land``/...) or None.
        target_id: The touched row ID, when there is a single target.
        details: Short human-readable detail line (amounts, old→new, ...).
        created_at: When it happened.
    """

    __tablename__ = "admin_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    admin_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(48), nullable=False, index=True)

    target_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    details: Mapped[str] = mapped_column(String(1024), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    def __repr__(self) -> str:  # pragma: no cover — debugging aid only
        return (
            f"<AdminAuditLog id={self.id} action={self.action!r} "
            f"admin={self.admin_telegram_id}>"
        )
