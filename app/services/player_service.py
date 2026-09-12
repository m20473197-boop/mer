"""Player service: registration, profile and status.

This is the transaction boundary for player operations. Registration is
idempotent and duplicate-safe: the unique index on ``telegram_user_id`` is
the final guarantee, and a race between two concurrent ``/start`` updates
falls back to a re-read instead of raising.
"""

from __future__ import annotations

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import constants
from app.database.models.player import Player
from app.database.repositories.player_repository import PlayerRepository
from app.game.player.dto import ProfileData, RegistrationResult, StatusData
from app.game.player.progression import get_level_progress

logger = logging.getLogger(__name__)


class PlayerService:
    """All player-related use cases."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # --- Use cases ---------------------------------------------------------

    async def register_or_get(
        self,
        *,
        telegram_user_id: int,
        username: str | None,
        display_name: str,
    ) -> RegistrationResult:
        """Create the player on first contact; return the existing one otherwise."""
        async with self._session_factory() as session:
            repository = PlayerRepository(session)

            existing = await repository.get_by_telegram_user_id(telegram_user_id)
            if existing is not None:
                return self._existing_result(existing)

            player = Player(
                telegram_user_id=telegram_user_id,
                username=self._clean_username(username),
                display_name=self._clean_display_name(display_name, telegram_user_id),
                level=constants.STARTING_LEVEL,
                xp=constants.STARTING_XP,
                money=constants.STARTING_MONEY,
            )
            repository.add(player)
            try:
                await session.commit()
            except IntegrityError:
                # Lost a race against a concurrent registration — re-read.
                await session.rollback()
                winner = await repository.get_by_telegram_user_id(telegram_user_id)
                if winner is None:
                    raise
                return self._existing_result(winner)

            logger.info(
                "New player registered: player_id=%s telegram_user_id=%s",
                player.id,
                telegram_user_id,
            )
            return RegistrationResult(
                player_id=player.id,
                created=True,
                profile=self._to_profile(player),
            )

    # --- Identity mapping ----------------------------------------------------

    async def resolve_player_id(self, telegram_user_id: int) -> int | None:
        """Map a Telegram user id to the internal player id (``None`` if unknown).

        Public helper so command handlers never dig into the session factory
        the way the early job handlers had to.
        """
        async with self._session_factory() as session:
            player = await PlayerRepository(session).get_by_telegram_user_id(
                telegram_user_id
            )
            return player.id if player is not None else None

    async def display_name_of(self, player_id: int | None) -> str | None:
        """Display name for a player id (``None`` when missing/unspecified)."""
        if player_id is None:
            return None
        async with self._session_factory() as session:
            player = await PlayerRepository(session).get_by_id(player_id)
            return player.display_name if player is not None else None

    async def get_telegram_user_id(self, player_id: int) -> int | None:
        """The reverse mapping — used to deliver private family notices."""
        async with self._session_factory() as session:
            player = await PlayerRepository(session).get_by_id(player_id)
            return player.telegram_user_id if player is not None else None

    async def get_profile(self, telegram_user_id: int) -> ProfileData | None:
        """Full profile data for the profile screen (``None`` if unregistered).

        This is the only read that resolves the spouse's *name* (a second
        lookup); registration and status keep their single-query shape.
        """
        async with self._session_factory() as session:
            repository = PlayerRepository(session)
            player = await repository.get_by_telegram_user_id(telegram_user_id)
            if player is None:
                return None
            profile = self._to_profile(player)
            if profile.spouse_player_id is None:
                return profile
            names = await repository.get_display_names({profile.spouse_player_id})
            spouse_name = names.get(profile.spouse_player_id)
            if spouse_name is None:
                return profile
            from dataclasses import replace

            return replace(profile, spouse_name=spouse_name)

    async def get_status(self, telegram_user_id: int) -> StatusData | None:
        """Basic game state for the status screen (``None`` if unregistered)."""
        async with self._session_factory() as session:
            player = await PlayerRepository(session).get_by_telegram_user_id(
                telegram_user_id
            )
            if player is None:
                return None
            prog = get_level_progress(player.xp)
            return StatusData(
                level=player.level,
                xp=player.xp,
                money=player.money,
                xp_in_current_level=prog.xp_in_current_level,
                xp_needed_for_next=prog.xp_needed_for_next,
                progress_percent=prog.progress_percent,
                total_xp_for_next_level=prog.total_xp_for_next_level,
            )

    # --- Helpers -----------------------------------------------------------

    @staticmethod
    def _existing_result(player: Player) -> RegistrationResult:
        return RegistrationResult(
            player_id=player.id,
            created=False,
            profile=PlayerService._to_profile(player),
        )

    @staticmethod
    def _to_profile(player: Player) -> ProfileData:
        prog = get_level_progress(player.xp)
        return ProfileData(
            display_name=player.display_name,
            level=player.level,
            xp=player.xp,
            money=player.money,
            xp_in_current_level=prog.xp_in_current_level,
            xp_needed_for_next=prog.xp_needed_for_next,
            progress_percent=prog.progress_percent,
            total_xp_for_next_level=prog.total_xp_for_next_level,
            married=player.spouse_player_id is not None,
            spouse_player_id=player.spouse_player_id,
            spouse_name=None,
            marriage_date=player.married_since,
            children_count=player.children_count,
        )

    @staticmethod
    def _clean_username(username: str | None) -> str | None:
        if not username:
            return None
        cleaned = username.strip().removeprefix("@")
        return cleaned[: constants.MAX_USERNAME_LENGTH] or None

    @staticmethod
    def _clean_display_name(display_name: str, telegram_user_id: int) -> str:
        normalized = " ".join(display_name.split())
        cleaned = normalized[: constants.MAX_DISPLAY_NAME_LENGTH].strip()
        return cleaned or f"بازیکن {telegram_user_id}"
