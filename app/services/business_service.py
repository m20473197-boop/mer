"""Business System service — predefined ownership and daily income.

Players can only start a business from the code catalog in
``app/game/business/catalog.py``. This service owns every business rule:
wallet sufficiency, the per-player ownership cap, catalog validation, and the
once-per-day random income settlement. Handlers never touch the database.

Daily income is settled lazily when a business screen is opened or when the
player taps «درآمد امروز». That gives the same result as a scheduler without
requiring a background worker: an active business receives at most one credit
for each calendar day.
"""

from __future__ import annotations

import logging
import random
from datetime import date, datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import constants
from app.database.models.business import Business
from app.database.repositories.business_repository import BusinessRepository
from app.database.repositories.player_repository import PlayerRepository
from app.game.business.catalog import (
    BusinessDefinition,
    get_business_definition,
    list_business_definitions,
)
from app.game.business.dto import (
    BusinessData,
    BusinessDefinitionData,
    BusinessIncomeResult,
    BusinessStartResult,
)
from app.game.shared.errors import DomainError, PlayerNotFoundError

logger = logging.getLogger(__name__)


class BusinessNotFoundError(DomainError):
    """The requested business type or owned business does not exist."""


class BusinessUnavailableError(DomainError):
    """A predefined business is currently closed in the catalog."""


class BusinessAlreadyOwnedError(DomainError):
    """The player already owns this business type."""


class BusinessLimitReachedError(DomainError):
    """The player has reached the configured business ownership cap."""


class BusinessNotOwnedError(DomainError):
    """The requested owned business belongs to another player."""


class BusinessInactiveError(DomainError):
    """An inactive owned business cannot generate daily income."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BusinessService:
    """Complete Business System use cases."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        money_service,
        rng: random.Random | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._money_service = money_service
        self._rng = rng if rng is not None else random.Random()

    # --- Conversion helpers -------------------------------------------------

    @staticmethod
    def _definition_to_dto(definition: BusinessDefinition) -> BusinessDefinitionData:
        return BusinessDefinitionData(
            key=definition.key,
            name=definition.name,
            startup_cost=definition.startup_cost,
            min_daily_income=definition.min_daily_income,
            max_daily_income=definition.max_daily_income,
            is_available=definition.is_available,
        )

    @staticmethod
    def _to_business_dto(business: Business) -> BusinessData:
        return BusinessData(
            id=business.id,
            owner_player_id=business.owner_player_id,
            business_type=business.business_type,
            name=business.name,
            startup_cost=business.startup_cost,
            min_daily_income=business.min_daily_income,
            max_daily_income=business.max_daily_income,
            is_active=business.is_active,
            balance=business.balance,
            latest_daily_income=business.latest_daily_income,
            last_income_date=business.last_income_date,
            started_at=business.started_at,
            created_at=business.created_at,
            updated_at=business.updated_at,
        )

    @staticmethod
    def _today(day: date | None) -> date:
        return day if day is not None else _utc_now().date()

    def _daily_roll(self, business: Business) -> int:
        return self._rng.randint(business.min_daily_income, business.max_daily_income)

    async def _require_player(self, session: AsyncSession, player_id: int) -> None:
        if not await PlayerRepository(session).exists(player_id):
            raise PlayerNotFoundError(f"player_id={player_id} not found")

    # --- Catalog ------------------------------------------------------------

    async def get_available_businesses(self) -> list[BusinessDefinitionData]:
        """Return all predefined businesses, including closed entries."""
        return [
            self._definition_to_dto(item) for item in list_business_definitions()
        ]

    # A descriptive alias for callers that want to emphasize that this is a
    # catalog, not arbitrary player-created data.
    async def get_business_catalog(self) -> list[BusinessDefinitionData]:
        return await self.get_available_businesses()

    # --- Starting a business -----------------------------------------------

    async def start_business(
        self, player_id: int, business_type: str
    ) -> BusinessStartResult:
        """Buy and start one configured business for ``player_id``."""
        definition = get_business_definition(business_type)
        if definition is None:
            raise BusinessNotFoundError(f"business type {business_type!r} not found")
        if not definition.is_available:
            raise BusinessUnavailableError(definition.name)
        if definition.startup_cost <= 0:
            raise BusinessUnavailableError(definition.name)
        if definition.min_daily_income <= 0 or definition.max_daily_income < definition.min_daily_income:
            raise BusinessUnavailableError(definition.name)

        async with self._session_factory() as session:
            await self._require_player(session, player_id)
            repository = BusinessRepository(session)

            if await repository.get_by_owner_and_type(player_id, definition.key) is not None:
                raise BusinessAlreadyOwnedError(definition.name)
            if await repository.count_by_owner(player_id) >= constants.BUSINESS_MAX_PER_PLAYER:
                raise BusinessLimitReachedError(
                    f"maximum {constants.BUSINESS_MAX_PER_PLAYER} businesses"
                )

            # The debit is performed by the existing wallet service inside
            # this same transaction; the new business and the debit therefore
            # commit or roll back together.
            wallet_result = await self._money_service.remove_money_in_transaction(
                session, player_id, definition.startup_cost
            )
            started_at = _utc_now()
            try:
                business = await repository.create(
                    owner_player_id=player_id,
                    business_type=definition.key,
                    name=definition.name,
                    startup_cost=definition.startup_cost,
                    min_daily_income=definition.min_daily_income,
                    max_daily_income=definition.max_daily_income,
                    started_at=started_at,
                )
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                # The unique owner/type constraint is the final concurrency
                # guard. No wallet debit survives this rollback.
                raise BusinessAlreadyOwnedError(definition.name) from exc

            logger.info(
                "Player %s started business %s (%s)",
                player_id,
                definition.key,
                definition.name,
            )
            return BusinessStartResult(
                business=self._to_business_dto(business),
                startup_cost=definition.startup_cost,
                wallet_balance_after=wallet_result.balance_after,
            )

    async def purchase_business(
        self, player_id: int, business_type: str
    ) -> BusinessStartResult:
        """Alias for UI/command callers that call starting a purchase."""
        return await self.start_business(player_id, business_type)

    # --- Daily income -------------------------------------------------------

    async def _generate_one(
        self,
        session: AsyncSession,
        repository: BusinessRepository,
        business: Business,
        player_id: int,
        income_date: date,
    ) -> BusinessIncomeResult:
        if not business.is_active:
            raise BusinessInactiveError(business.name)

        if business.last_income_date == income_date:
            return BusinessIncomeResult(
                business=self._to_business_dto(business),
                generated=False,
                amount_added=0,
                income_date=income_date,
            )

        amount = self._daily_roll(business)
        updated = await repository.add_daily_income(
            business_id=business.id,
            owner_player_id=player_id,
            income_date=income_date,
            amount=amount,
        )
        await session.flush()
        await session.refresh(business)
        if not updated:
            # Another request won the same-day race. Return the persisted row
            # and do not claim that this request added money.
            return BusinessIncomeResult(
                business=self._to_business_dto(business),
                generated=False,
                amount_added=0,
                income_date=income_date,
            )

        return BusinessIncomeResult(
            business=self._to_business_dto(business),
            generated=True,
            amount_added=amount,
            income_date=income_date,
        )

    async def generate_daily_income(
        self,
        player_id: int,
        business_id: int,
        *,
        day: date | None = None,
    ) -> BusinessIncomeResult:
        """Generate one daily credit for one owned business, at most once."""
        income_date = self._today(day)
        async with self._session_factory() as session:
            await self._require_player(session, player_id)
            repository = BusinessRepository(session)
            business = await repository.get_by_id(business_id)
            if business is None:
                raise BusinessNotFoundError(f"business_id={business_id} not found")
            if business.owner_player_id != player_id:
                raise BusinessNotOwnedError(business.name)

            result = await self._generate_one(
                session, repository, business, player_id, income_date
            )
            await session.commit()
            return result

    async def generate_all_daily_income(
        self, player_id: int, *, day: date | None = None
    ) -> list[BusinessIncomeResult]:
        """Settle every active owned business for one day."""
        income_date = self._today(day)
        async with self._session_factory() as session:
            await self._require_player(session, player_id)
            repository = BusinessRepository(session)
            businesses = await repository.list_by_owner(player_id)
            results: list[BusinessIncomeResult] = []
            for business in businesses:
                if not business.is_active:
                    continue
                results.append(
                    await self._generate_one(
                        session, repository, business, player_id, income_date
                    )
                )
            await session.commit()
            return results

    async def get_owned_businesses(
        self,
        player_id: int,
        *,
        settle_income: bool = True,
        day: date | None = None,
    ) -> list[BusinessData]:
        """Return owned businesses, lazily settling today's income first."""
        income_date = self._today(day)
        async with self._session_factory() as session:
            await self._require_player(session, player_id)
            repository = BusinessRepository(session)
            businesses = await repository.list_by_owner(player_id)
            if settle_income:
                for business in businesses:
                    if business.is_active:
                        await self._generate_one(
                            session,
                            repository,
                            business,
                            player_id,
                            income_date,
                        )
            await session.commit()
            return [self._to_business_dto(item) for item in businesses]

    async def get_business(self, player_id: int, business_id: int) -> BusinessData:
        """Read one owned business without changing its balance."""
        async with self._session_factory() as session:
            await self._require_player(session, player_id)
            business = await BusinessRepository(session).get_by_id(business_id)
            if business is None:
                raise BusinessNotFoundError(f"business_id={business_id} not found")
            if business.owner_player_id != player_id:
                raise BusinessNotOwnedError(business.name)
            return self._to_business_dto(business)
