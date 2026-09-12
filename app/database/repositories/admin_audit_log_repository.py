"""Repository for the ``admin_audit_logs`` table (admin action trail)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.admin_audit_log import AdminAuditLog


class AdminAuditLogRepository:
    """All database operations for the admin audit trail."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reads ------------------------------------------------------------

    async def list_page(
        self,
        offset: int,
        limit: int,
        *,
        action_prefix: str | None = None,
    ) -> list[AdminAuditLog]:
        """Audit rows, newest first, optionally filtered by action prefix."""
        statement = select(AdminAuditLog).order_by(AdminAuditLog.id.desc())
        if action_prefix:
            statement = statement.where(
                AdminAuditLog.action.like(f"{action_prefix}%")
            )
        statement = statement.offset(offset).limit(limit)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def count(self, *, action_prefix: str | None = None) -> int:
        statement = select(func.count(AdminAuditLog.id))
        if action_prefix:
            statement = statement.where(
                AdminAuditLog.action.like(f"{action_prefix}%")
            )
        return int((await self._session.execute(statement)).scalar_one())

    # --- Writes ------------------------------------------------------------

    async def add(
        self,
        *,
        admin_telegram_id: int,
        action: str,
        target_type: str | None = None,
        target_id: int | None = None,
        details: str = "",
    ) -> AdminAuditLog:
        """Append one audit row; the owning service commits the transaction."""
        row = AdminAuditLog(
            admin_telegram_id=admin_telegram_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details[:1024],
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def prune_older_than(self, cutoff: datetime) -> int:
        """Delete audit rows older than ``cutoff``; returns rows removed."""
        statement = delete(AdminAuditLog).where(AdminAuditLog.created_at < cutoff)
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return int(result.rowcount or 0)
