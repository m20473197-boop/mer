"""Database access for players.

Repositories are the only place where queries live. Services call them and
own the transaction; Telegram handlers never touch this layer directly.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.player import Player


class PlayerRepository:
    """All database operations for the ``players`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reads -----------------------------------------------------------

    async def get_by_id(self, player_id: int) -> Player | None:
        return await self._session.get(Player, player_id)

    async def get_by_telegram_user_id(self, telegram_user_id: int) -> Player | None:
        statement = select(Player).where(Player.telegram_user_id == telegram_user_id)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def exists(self, player_id: int) -> bool:
        statement = select(Player.id).where(Player.id == player_id).limit(1)
        return (await self._session.execute(statement)).scalar() is not None

    async def get_money(self, player_id: int) -> int | None:
        """Return the balance, or ``None`` when the player does not exist."""
        statement = select(Player.money).where(Player.id == player_id)
        return (await self._session.execute(statement)).scalar_one_or_none()

    # --- Admin reads -------------------------------------------------------

    async def list_page(self, offset: int, limit: int) -> list[Player]:
        """One page of players, oldest first."""
        statement = select(Player).order_by(Player.id).offset(offset).limit(limit)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def count(self) -> int:
        result = await self._session.execute(select(func.count(Player.id)))
        return int(result.scalar_one())

    async def count_banned(self) -> int:
        result = await self._session.execute(
            select(func.count(Player.id)).where(Player.is_banned.is_(True))
        )
        return int(result.scalar_one())

    async def count_active_since(self, since: datetime) -> int:
        """Players with any activity (row update) at or after ``since``."""
        result = await self._session.execute(
            select(func.count(Player.id)).where(Player.updated_at >= since)
        )
        return int(result.scalar_one())

    async def sum_money(self) -> int:
        """Total money in circulation (sum of all wallets)."""
        result = await self._session.execute(select(func.sum(Player.money)))
        return int(result.scalar_one() or 0)

    async def search(self, query: str, limit: int = 10) -> list[Player]:
        """Find players by Telegram ID, username or display name."""
        cleaned = query.strip().removeprefix("@")
        if not cleaned:
            return []
        conditions = [
            Player.username.ilike(f"%{cleaned}%"),
            Player.display_name.ilike(f"%{cleaned}%"),
        ]
        if cleaned.lstrip("+-").isdigit():
            number = int(cleaned)
            conditions.append(Player.telegram_user_id == number)
            conditions.append(Player.id == number)
        statement = (
            select(Player).where(or_(*conditions)).order_by(Player.id).limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    # --- Admin writes ------------------------------------------------------

    async def set_banned(self, player_id: int, banned: bool) -> bool:
        """Ban or unban a player. Returns ``False`` when missing."""
        statement = (
            update(Player).where(Player.id == player_id).values(is_banned=banned)
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        # The UPDATE bypasses the identity map — expire any cached instance
        # so later reads in this session see the new flag.
        cached = await self._session.get(Player, player_id)
        if cached is not None:
            self._session.expire(cached)
        return bool(result.rowcount)

    # --- Family reads / writes ---------------------------------------------

    async def get_family_pointers(self, player_id: int) -> Player | None:
        """The player row (family pointers included) or ``None`` when missing."""
        return await self._session.get(Player, player_id)

    async def get_display_names(self, player_ids: set[int]) -> dict[int, str]:
        """Bulk name lookup — keeps spouse/parent rendering to one query."""
        if not player_ids:
            return {}
        statement = select(Player.id, Player.display_name).where(
            Player.id.in_(player_ids)
        )
        rows = (await self._session.execute(statement)).all()
        return {row[0]: row[1] for row in rows}

    async def get_telegram_user_ids(self, player_ids: set[int]) -> dict[int, int]:
        """Map internal player ids to Telegram user ids (for notifications)."""
        if not player_ids:
            return {}
        statement = select(Player.id, Player.telegram_user_id).where(
            Player.id.in_(player_ids)
        )
        rows = (await self._session.execute(statement)).all()
        return {row[0]: row[1] for row in rows}

    async def set_family_pointers(
        self,
        player_id: int,
        *,
        spouse_player_id: int | None,
        marriage_id: int | None,
        married_since: datetime | None,
    ) -> bool:
        """Point a player at their spouse / marriage (one side of a pair).

        Note: the ``UPDATE`` bypasses the identity map, so the cached instance
        is expired to keep later reads honest. Callers must therefore read any
        value they still need from a loaded Player *before* calling this.
        """
        statement = (
            update(Player)
            .where(Player.id == player_id)
            .values(
                spouse_player_id=spouse_player_id,
                marriage_id=marriage_id,
                married_since=married_since,
            )
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        cached = await self._session.get(Player, player_id)
        if cached is not None:
            self._session.expire(cached)
        return bool(result.rowcount)

    async def set_children_count(self, player_id: int, count: int) -> bool:
        """Denormalized child counter shown on the profile."""
        statement = (
            update(Player).where(Player.id == player_id).values(children_count=count)
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        cached = await self._session.get(Player, player_id)
        if cached is not None:
            self._session.expire(cached)
        return bool(result.rowcount)

    # --- Writes ------------------------------------------------------------

    def add(self, player: Player) -> None:
        """Stage a new player; the owning service commits the transaction."""
        self._session.add(player)

    async def add_money(self, player_id: int, amount: int) -> bool:
        """Atomically increase the balance.

        Returns:
            ``False`` when the player does not exist.
        """
        statement = (
            update(Player)
            .where(Player.id == player_id)
            .values(money=Player.money + amount)
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)

    async def remove_money_if_enough(self, player_id: int, amount: int) -> bool:
        """Atomically remove money, but only if the balance covers it.

        The check and the subtraction happen in a single SQL statement, so a
        concurrent operation can never drive the balance below zero.

        Returns:
            ``False`` when the player is missing or the balance is too low.
        """
        statement = (
            update(Player)
            .where(Player.id == player_id, Player.money >= amount)
            .values(money=Player.money - amount)
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)
