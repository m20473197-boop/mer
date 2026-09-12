"""Level/XP service — complete progression system.

Every present and future system (jobs, education, businesses, events, ...)
must grant XP through this service, so progression rules stay isolated in
one place. XP is never granted implicitly and never generated randomly.

The service:
* Grants XP with reason and history
* Removes XP (never below zero) with history
* Detects level-ups and records them
* Calculates progress percentage and required XP for next level
* Exposes pure progression math via DTOs
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import constants
from app.database.models.player import Player
from app.database.repositories.level_up_repository import LevelUpRepository
from app.database.repositories.player_repository import PlayerRepository
from app.database.repositories.xp_transaction_repository import (
    XPTransactionRepository,
)
from app.game.player.dto import (
    AddXpResult,
    LevelProgressData,
    LevelUpData,
    RemoveXpResult,
    XPTransactionData,
)
from app.game.player.progression import (
    get_level_progress,
    level_from_total_xp,
    xp_for_level_up,
)
from app.game.shared.errors import InvalidAmountError, PlayerNotFoundError

logger = logging.getLogger(__name__)


class LevelService:
    """Complete Level/XP progression service with history."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # --- Basic reads -------------------------------------------------------

    async def get_xp(self, player_id: int) -> int:
        player = await self._get_player(player_id)
        return player.xp

    async def get_level(self, player_id: int) -> int:
        player = await self._get_player(player_id)
        return player.level

    async def get_progress(self, player_id: int) -> LevelProgressData:
        """Full progress snapshot for a player."""
        player = await self._get_player(player_id)
        prog = get_level_progress(player.xp)
        return LevelProgressData(
            level=prog.level,
            total_xp=prog.total_xp,
            xp_in_current_level=prog.xp_in_current_level,
            xp_needed_for_next=prog.xp_needed_for_next,
            total_xp_for_current_level=prog.total_xp_for_current_level,
            total_xp_for_next_level=prog.total_xp_for_next_level,
            progress_percent=prog.progress_percent,
        )

    async def get_required_xp_for_next_level(self, player_id: int) -> int:
        """XP needed to go from current level to next."""
        player = await self._get_player(player_id)
        return xp_for_level_up(player.level)

    async def get_xp_history(
        self, player_id: int, limit: int = 50, offset: int = 0
    ) -> list[XPTransactionData]:
        async with self._session_factory() as session:
            repo = XPTransactionRepository(session)
            if not await PlayerRepository(session).exists(player_id):
                raise PlayerNotFoundError(f"player_id={player_id} not found")
            transactions = await repo.list_by_player(player_id, limit, offset)
            return [
                XPTransactionData(
                    id=t.id,
                    player_id=t.player_id,
                    amount=t.amount,
                    reason=t.reason,
                    created_at=t.created_at,
                )
                for t in transactions
            ]

    async def get_level_up_history(
        self, player_id: int, limit: int = 50, offset: int = 0
    ) -> list[LevelUpData]:
        async with self._session_factory() as session:
            repo = LevelUpRepository(session)
            if not await PlayerRepository(session).exists(player_id):
                raise PlayerNotFoundError(f"player_id={player_id} not found")
            records = await repo.list_by_player(player_id, limit, offset)
            return [
                LevelUpData(
                    id=r.id,
                    player_id=r.player_id,
                    old_level=r.old_level,
                    new_level=r.new_level,
                    created_at=r.created_at,
                )
                for r in records
            ]

    # --- XP mutations ------------------------------------------------------

    async def add_xp(
        self, player_id: int, amount: int, reason: str = "unknown"
    ) -> AddXpResult:
        """Add XP, save history, detect level-up and record it.

        Args:
            player_id: Target player.
            amount: Positive XP amount.
            reason: Reason for audit trail (e.g. "Completed job").

        Raises:
            InvalidAmountError: If amount <=0 or reason empty/invalid.
            PlayerNotFoundError: If player does not exist.
        """
        if amount <= 0:
            raise InvalidAmountError("XP amount must be a positive integer")
        clean_reason = self._clean_reason(reason)

        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            player = await player_repo.get_by_id(player_id)
            if player is None:
                raise PlayerNotFoundError(f"player_id={player_id} not found")

            xp_before = player.xp
            old_level = player.level

            # Apply XP
            player.xp = xp_before + amount
            new_level = level_from_total_xp(player.xp)

            # History: XP transaction
            xp_repo = XPTransactionRepository(session)
            tx = xp_repo.add(player_id=player_id, amount=amount, reason=clean_reason)

            # Level up handling
            leveled_up = new_level > old_level
            if leveled_up:
                player.level = new_level
                level_repo = LevelUpRepository(session)
                level_repo.add(
                    player_id=player_id, old_level=old_level, new_level=new_level
                )
            else:
                # Ensure level is still consistent (in case of manual edits)
                player.level = new_level

            await session.flush()  # to get tx.id
            tx_id = tx.id
            await session.commit()

            prog = get_level_progress(player.xp)

            result = AddXpResult(
                player_id=player.id,
                xp_before=xp_before,
                xp_after=player.xp,
                old_level=old_level,
                new_level=new_level,
                leveled_up=leveled_up,
                reason=clean_reason,
                xp_needed_for_next=prog.xp_needed_for_next,
                progress_percent=prog.progress_percent,
                xp_in_current_level=prog.xp_in_current_level,
                transaction_id=tx_id,
            )

        if result.leveled_up:
            logger.info(
                "Player %s leveled up: %s -> %s (reason=%s + %s XP)",
                player_id,
                result.old_level,
                result.new_level,
                clean_reason,
                amount,
            )
        else:
            logger.debug(
                "XP added: player=%s amount=%s reason=%s",
                player_id,
                amount,
                clean_reason,
            )
        return result

    async def remove_xp(
        self, player_id: int, amount: int, reason: str = "unknown"
    ) -> RemoveXpResult:
        """Remove XP, never below zero, with history.

        Level may decrease if XP drops below threshold — level is always
        derived from total XP.

        Raises:
            InvalidAmountError: If amount <=0 or would make XP negative.
            PlayerNotFoundError: If player missing.
        """
        if amount <= 0:
            raise InvalidAmountError("XP amount must be a positive integer")
        clean_reason = self._clean_reason(reason)

        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            player = await player_repo.get_by_id(player_id)
            if player is None:
                raise PlayerNotFoundError(f"player_id={player_id} not found")

            xp_before = player.xp
            old_level = player.level

            if xp_before < amount:
                raise InvalidAmountError("XP cannot go below zero")

            player.xp = xp_before - amount
            new_level = level_from_total_xp(player.xp)
            player.level = new_level

            # History: negative amount for removal
            xp_repo = XPTransactionRepository(session)
            tx = xp_repo.add(
                player_id=player_id, amount=-amount, reason=clean_reason
            )

            # Note: we do NOT create level_up history on level down — only ups
            # are recorded for future rewards. Level down is just a state change.

            await session.flush()
            tx_id = tx.id
            await session.commit()

            prog = get_level_progress(player.xp)

            result = RemoveXpResult(
                player_id=player.id,
                xp_before=xp_before,
                xp_after=player.xp,
                old_level=old_level,
                new_level=new_level,
                leveled_down=new_level < old_level,
                reason=clean_reason,
                xp_needed_for_next=prog.xp_needed_for_next,
                progress_percent=prog.progress_percent,
                xp_in_current_level=prog.xp_in_current_level,
                transaction_id=tx_id,
            )

        logger.info(
            "XP removed: player=%s amount=%s reason=%s %s->%s",
            player_id,
            amount,
            clean_reason,
            old_level,
            new_level,
        )
        return result

    async def set_level(
        self, player_id: int, new_level: int, reason: str = "admin_set_level"
    ) -> AddXpResult:
        """Admin helper: set player's level directly by adjusting XP.

        Sets XP to the exact total required to reach ``new_level``.
        If new_level > current, grants XP; if lower, removes XP.
        Creates appropriate history records.

        Raises:
            InvalidAmountError: If new_level <1.
            PlayerNotFoundError: If player missing.
        """
        if new_level < 1:
            raise InvalidAmountError("Level must be >= 1")

        from app.game.player.progression import total_xp_for_level

        target_total_xp = total_xp_for_level(new_level)

        async with self._session_factory() as session:
            player_repo = PlayerRepository(session)
            player = await player_repo.get_by_id(player_id)
            if player is None:
                raise PlayerNotFoundError(f"player_id={player_id} not found")

            xp_before = player.xp
            old_level = player.level

            if target_total_xp == xp_before and new_level == old_level:
                # No change needed
                prog = get_level_progress(player.xp)
                return AddXpResult(
                    player_id=player.id,
                    xp_before=xp_before,
                    xp_after=xp_before,
                    old_level=old_level,
                    new_level=new_level,
                    leveled_up=False,
                    reason=reason,
                    xp_needed_for_next=prog.xp_needed_for_next,
                    progress_percent=prog.progress_percent,
                    xp_in_current_level=prog.xp_in_current_level,
                    transaction_id=None,
                )

            # Determine delta
            delta = target_total_xp - xp_before

            # Update player
            player.xp = target_total_xp
            player.level = new_level

            xp_repo = XPTransactionRepository(session)
            tx_id = None
            if delta != 0:
                tx = xp_repo.add(
                    player_id=player_id, amount=delta, reason=self._clean_reason(reason)
                )
                await session.flush()
                tx_id = tx.id

            # Record level change if up
            if new_level > old_level:
                level_repo = LevelUpRepository(session)
                level_repo.add(
                    player_id=player_id, old_level=old_level, new_level=new_level
                )

            await session.commit()
            prog = get_level_progress(player.xp)

            return AddXpResult(
                player_id=player.id,
                xp_before=xp_before,
                xp_after=player.xp,
                old_level=old_level,
                new_level=new_level,
                leveled_up=new_level > old_level,
                reason=reason,
                xp_needed_for_next=prog.xp_needed_for_next,
                progress_percent=prog.progress_percent,
                xp_in_current_level=prog.xp_in_current_level,
                transaction_id=tx_id,
            )

    # --- Helpers -----------------------------------------------------------

    async def _get_player(self, player_id: int) -> Player:
        async with self._session_factory() as session:
            player = await PlayerRepository(session).get_by_id(player_id)
            if player is None:
                raise PlayerNotFoundError(f"player_id={player_id} not found")
            return player

    @staticmethod
    def _clean_reason(reason: str) -> str:
        if not reason or not reason.strip():
            return "unknown"
        cleaned = " ".join(reason.strip().split())
        return cleaned[: constants.MAX_XP_REASON_LENGTH]
