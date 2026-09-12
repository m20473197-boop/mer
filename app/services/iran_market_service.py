"""Service and scheduler for the player-facing ``📈 بازار ایران`` system."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, Mapping

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import constants
from app.database.models.iran_market_asset import IranMarketAsset
from app.database.repositories.iran_market_asset_repository import (
    IranMarketAssetRepository,
)
from app.database.repositories.iran_market_price_history_repository import (
    IranMarketPriceHistoryRepository,
)
from app.database.repositories.iran_market_update_state_repository import (
    IranMarketUpdateStateRepository,
)
from app.game.housing.catalog import (
    CITY_BASE_PRICE_PER_SQM,
    get_base_price_per_sqm,
)
from app.game.market.catalog import (
    IRAN_MARKET_ASSET_CATALOG,
    IRAN_MARKET_ASSET_CODES,
    ASSET_HOUSING,
    get_asset_definition,
    is_external_asset,
)
from app.game.market.dto import (
    IranMarketAssetData,
    IranMarketHistoryData,
    IranMarketSnapshotData,
    MarketUpdateResult,
)
from app.game.market.provider import (
    MarketDataError,
    MarketDataProvider,
    TGJUProvider,
)
from app.game.shared.errors import DomainError

logger = logging.getLogger(__name__)


class IranMarketAssetNotFoundError(DomainError):
    """The requested player-facing asset is not in the four-item catalog."""


class IranMarketDataInvalidError(DomainError):
    """A provider returned an incomplete or invalid snapshot."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class IranMarketService:
    """Shared stored-price service; handlers only read its DTOs."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        provider: MarketDataProvider | None = None,
        now_fn: Callable[[], datetime] | None = None,
        update_interval_seconds: int | None = None,
        scheduler_check_seconds: int | None = None,
        initial_retry_seconds: int | None = None,
        failure_retry_seconds: int | None = None,
        lock_seconds: int | None = None,
        initial_fetch_enabled: bool | None = None,
        housing_reference_city: str | None = None,
        housing_reference_price_per_sqm: int | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._provider = provider or TGJUProvider()
        self._now_fn = now_fn or _utc_now
        self._update_interval = _positive_setting(
            update_interval_seconds,
            "IRAN_MARKET_UPDATE_INTERVAL_SECONDS",
            constants.IRAN_MARKET_UPDATE_INTERVAL_SECONDS,
        )
        self._scheduler_check = _positive_setting(
            scheduler_check_seconds,
            "IRAN_MARKET_SCHEDULER_CHECK_SECONDS",
            constants.IRAN_MARKET_SCHEDULER_CHECK_SECONDS,
        )
        self._initial_retry = _positive_setting(
            initial_retry_seconds,
            "IRAN_MARKET_INITIAL_RETRY_SECONDS",
            constants.IRAN_MARKET_INITIAL_RETRY_SECONDS,
        )
        self._failure_retry = _positive_setting(
            failure_retry_seconds,
            "IRAN_MARKET_FAILURE_RETRY_SECONDS",
            constants.IRAN_MARKET_FAILURE_RETRY_SECONDS,
        )
        self._lock_seconds = _positive_setting(
            lock_seconds,
            "IRAN_MARKET_UPDATE_LOCK_SECONDS",
            constants.IRAN_MARKET_UPDATE_LOCK_SECONDS,
        )
        self._initial_fetch_enabled = (
            initial_fetch_enabled
            if initial_fetch_enabled is not None
            else _env_bool(
                constants.IRAN_MARKET_INITIAL_FETCH_ENV,
                constants.IRAN_MARKET_INITIAL_FETCH_ENABLED,
            )
        )
        self._housing_reference_city = (
            housing_reference_city
            if housing_reference_city is not None
            else os.getenv(
                constants.IRAN_MARKET_HOUSING_CITY_ENV,
                constants.IRAN_MARKET_HOUSING_REFERENCE_CITY,
            )
        ).strip() or constants.IRAN_MARKET_HOUSING_REFERENCE_CITY
        self._housing_reference_price_override = (
            housing_reference_price_per_sqm
            if housing_reference_price_per_sqm is not None
            else _env_int_or_none(
                constants.IRAN_MARKET_HOUSING_PRICE_ENV,
                minimum=1,
            )
        )
        if (
            self._housing_reference_price_override is not None
            and self._housing_reference_price_override <= 0
        ):
            self._housing_reference_price_override = None
        self._scheduler_task: asyncio.Task[None] | None = None

    # --- Lifecycle ---------------------------------------------------------

    async def ensure_initial_state(self) -> MarketUpdateResult | None:
        """Create missing rows without resetting existing valid market data."""
        missing_external = False
        async with self._session_factory() as session:
            assets = IranMarketAssetRepository(session)
            history = IranMarketPriceHistoryRepository(session)
            for definition in IRAN_MARKET_ASSET_CATALOG:
                existing = await assets.get_by_code(definition.code)
                if existing is not None:
                    # The player-facing catalog is fixed and active. Re-enable
                    # only this catalog flag if an interrupted/manual edit
                    # left a row hidden; never reset a valid stored price.
                    if not existing.is_active:
                        existing.is_active = True
                        session.add(existing)
                    if (
                        definition.category == ASSET_HOUSING
                        and existing.current_price is None
                    ):
                        reference = self._housing_reference_price()
                        existing.base_value = reference
                        existing.current_price = reference
                        session.add(existing)
                        if not await history.list_by_asset(existing.id, limit=1):
                            await history.add(
                                asset_id=existing.id,
                                previous_price=None,
                                new_price=reference,
                                change_amount=0,
                                direction="unchanged",
                                source="existing_housing_catalog",
                                update_type="initial_housing",
                                cycle_id=f"housing-initial-{existing.id}",
                            )
                    if (
                        is_external_asset(definition.code)
                        and existing.current_price is None
                    ):
                        missing_external = True
                    continue

                initial_price = (
                    self._housing_reference_price()
                    if definition.category == ASSET_HOUSING
                    else None
                )
                created, was_created = await assets.create_if_missing(
                    code=definition.code,
                    display_name=definition.display_name,
                    category=definition.category,
                    base_value=initial_price,
                    current_price=initial_price,
                    is_active=definition.is_active,
                )
                if is_external_asset(definition.code):
                    missing_external = True
                if (
                    was_created
                    and definition.category == ASSET_HOUSING
                    and initial_price is not None
                ):
                    await history.add(
                        asset_id=created.id,
                        previous_price=None,
                        new_price=initial_price,
                        change_amount=0,
                        direction="unchanged",
                        source="existing_housing_catalog",
                        update_type="initial_housing",
                        cycle_id=f"housing-initial-{created.id}",
                    )

            state = await IranMarketUpdateStateRepository(session).ensure()
            if not self._initial_fetch_enabled and missing_external:
                # Seed-only startup mode avoids an immediate network call but
                # leaves a persisted retry window for the scheduler.
                state.last_attempted_update = _as_utc(self._now_fn())
                session.add(state)
            await session.commit()

        # First setup, or a damaged row with no external quote, gets one
        # automatic real-data attempt unless startup initialization has been
        # configured to seed rows only. A player opening the UI never calls this.
        if not self._initial_fetch_enabled:
            return None
        return await self.update_if_due(force=missing_external)

    def start_scheduler(self) -> None:
        """Start one process-local async loop; DB leasing covers extra workers."""
        if self._scheduler_task is not None and not self._scheduler_task.done():
            return
        self._scheduler_task = asyncio.create_task(
            self._scheduler_loop(), name="iran-market-scheduler"
        )
        logger.info(
            "Iran market scheduler started (interval=%ss, check=%ss)",
            self._update_interval,
            self._scheduler_check,
        )

    async def stop_scheduler(self) -> None:
        task = self._scheduler_task
        self._scheduler_task = None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info("Iran market scheduler stopped")

    async def _scheduler_loop(self) -> None:
        while True:
            try:
                await self.update_if_due()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — scheduler must survive one bad cycle
                logger.error(
                    "Iran market scheduler cycle failed (%s)", type(exc).__name__
                )
            await asyncio.sleep(self._scheduler_check)

    # --- Read API (never updates prices) -----------------------------------

    async def get_snapshot(self) -> IranMarketSnapshotData:
        """Read the stored four-asset snapshot; never calls the provider."""
        async with self._session_factory() as session:
            assets = await IranMarketAssetRepository(session).list_by_codes(
                IRAN_MARKET_ASSET_CODES
            )
            state = await IranMarketUpdateStateRepository(session).get()
            return IranMarketSnapshotData(
                assets=tuple(self._to_asset_data(asset) for asset in assets),
                last_successful_update=(
                    _as_utc(state.last_successful_update) if state else None
                ),
            )

    async def get_asset(self, code: str) -> IranMarketAssetData:
        """Read one stored asset without checking or triggering the schedule."""
        if get_asset_definition(code) is None:
            raise IranMarketAssetNotFoundError(code)
        async with self._session_factory() as session:
            asset = await IranMarketAssetRepository(session).get_by_code(code)
            if asset is None or not asset.is_active:
                raise IranMarketAssetNotFoundError(code)
            return self._to_asset_data(asset)

    async def get_history(
        self, code: str, *, limit: int = 20
    ) -> list[IranMarketHistoryData]:
        """Retrieve clean history for future charts/analysis."""
        if get_asset_definition(code) is None:
            raise IranMarketAssetNotFoundError(code)
        async with self._session_factory() as session:
            asset = await IranMarketAssetRepository(session).get_by_code(code)
            if asset is None:
                raise IranMarketAssetNotFoundError(code)
            rows = await IranMarketPriceHistoryRepository(session).list_by_asset(
                asset.id, limit=limit
            )
            return [self._to_history_data(row, asset.code) for row in rows]

    # --- Scheduled update --------------------------------------------------

    async def update_if_due(
        self,
        *,
        force: bool = False,
        now: datetime | None = None,
    ) -> MarketUpdateResult:
        """Claim and process one three-day cycle if it is due."""
        attempted_at = _as_utc(now or self._now_fn()) or _utc_now()
        token = uuid.uuid4().hex
        cycle_id = f"{int(attempted_at.timestamp())}-{token[:12]}"

        async with self._session_factory() as session:
            state_repo = IranMarketUpdateStateRepository(session)
            await state_repo.ensure()
            claimed = await state_repo.try_claim(
                now=attempted_at,
                token=token,
                due_before=attempted_at - timedelta(seconds=self._update_interval),
                initial_retry_before=attempted_at
                - timedelta(seconds=self._initial_retry),
                failure_retry_before=attempted_at
                - timedelta(seconds=self._failure_retry),
                lease_expired_before=attempted_at
                - timedelta(seconds=self._lock_seconds),
                force=force,
            )
            if not claimed:
                await session.commit()
                return MarketUpdateResult(
                    attempted=False,
                    successful=False,
                    cycle_id=None,
                    updated_assets=(),
                    attempted_at=attempted_at,
                    completed_at=None,
                )
            await IranMarketAssetRepository(session).mark_attempted(
                IRAN_MARKET_ASSET_CODES, attempted_at
            )
            await session.commit()

        try:
            raw_prices = await self._provider.fetch_prices()
            prices = self._validate_external_prices(raw_prices)
        except asyncio.CancelledError:
            # A graceful shutdown must not leave a live lease behind for the
            # next process. The token guard makes this harmless if another
            # worker already superseded the claim.
            await self._release_claim(token, "update_cancelled")
            raise
        except Exception as exc:  # noqa: BLE001 — preserve last valid state
            logger.warning(
                "Iran market update failed; keeping last valid prices (%s)",
                type(exc).__name__,
            )
            await self._release_claim(token, self._safe_error(exc))
            return MarketUpdateResult(
                attempted=True,
                successful=False,
                cycle_id=cycle_id,
                updated_assets=(),
                attempted_at=attempted_at,
                completed_at=None,
                error=type(exc).__name__,
            )

        completed_at = _as_utc(self._now_fn()) or attempted_at
        try:
            async with self._session_factory() as session:
                state_repo = IranMarketUpdateStateRepository(session)
                state = await state_repo.get()
                if state is None or state.lock_token != token:
                    # A lease expired and a newer worker won. Do not let the
                    # older, potentially stale provider response overwrite it.
                    await session.rollback()
                    return MarketUpdateResult(
                        attempted=True,
                        successful=False,
                        cycle_id=cycle_id,
                        updated_assets=(),
                        attempted_at=attempted_at,
                        completed_at=None,
                        error="superseded",
                    )

                assets_repo = IranMarketAssetRepository(session)
                history_repo = IranMarketPriceHistoryRepository(session)
                assets = {
                    asset.code: asset
                    for asset in await assets_repo.list_by_codes(IRAN_MARKET_ASSET_CODES)
                }
                required = {
                    code for code in IRAN_MARKET_ASSET_CODES if is_external_asset(code)
                }
                if not required.issubset(assets):
                    raise IranMarketDataInvalidError("market asset rows are incomplete")

                for code in sorted(required):
                    asset = assets[code]
                    previous = asset.current_price
                    new_price = prices[code]
                    await assets_repo.update_quote(
                        asset, new_price=new_price, updated_at=completed_at
                    )
                    change = 0 if previous is None else abs(new_price - previous)
                    direction = _direction(previous, new_price)
                    await history_repo.add(
                        asset_id=asset.id,
                        previous_price=previous,
                        new_price=new_price,
                        change_amount=change,
                        direction=direction,
                        source=self._provider.source_name,
                        update_type="scheduled_external",
                        cycle_id=cycle_id,
                    )

                if not await state_repo.finalize(
                    token=token, successful_at=completed_at
                ):
                    await session.rollback()
                    return MarketUpdateResult(
                        attempted=True,
                        successful=False,
                        cycle_id=cycle_id,
                        updated_assets=(),
                        attempted_at=attempted_at,
                        completed_at=None,
                        error="superseded",
                    )
                await session.commit()
        except asyncio.CancelledError:
            await self._release_claim(token, "update_cancelled")
            raise
        except Exception as exc:  # noqa: BLE001 — database/provider boundary
            logger.error(
                "Iran market update transaction failed (%s)", type(exc).__name__
            )
            await self._release_claim(token, self._safe_error(exc))
            return MarketUpdateResult(
                attempted=True,
                successful=False,
                cycle_id=cycle_id,
                updated_assets=(),
                attempted_at=attempted_at,
                completed_at=None,
                error=type(exc).__name__,
            )

        logger.info(
            "Iran market update succeeded from %s (cycle=%s)",
            self._provider.source_name,
            cycle_id,
        )
        return MarketUpdateResult(
            attempted=True,
            successful=True,
            cycle_id=cycle_id,
            updated_assets=tuple(sorted(prices)),
            attempted_at=attempted_at,
            completed_at=completed_at,
        )

    async def _release_claim(self, token: str, error: str) -> None:
        try:
            async with self._session_factory() as session:
                released = await IranMarketUpdateStateRepository(session).release(
                    token=token, error=error
                )
                await session.commit()
                if not released:
                    logger.info("Iran market claim %s was already superseded", token[:12])
        except Exception as exc:  # noqa: BLE001 — never hide the original provider error
            logger.error(
                "Could not release Iran market update claim (%s)",
                type(exc).__name__,
            )

    @staticmethod
    def _validate_external_prices(values: Mapping[str, int]) -> dict[str, int]:
        required = {
            definition.code
            for definition in IRAN_MARKET_ASSET_CATALOG
            if is_external_asset(definition.code)
        }
        missing = required - set(values)
        if missing:
            raise IranMarketDataInvalidError(
                "provider response missing: " + ", ".join(sorted(missing))
            )
        result: dict[str, int] = {}
        for code in required:
            value = values[code]
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise IranMarketDataInvalidError(f"invalid price for {code}")
            if value > 10**18:
                raise IranMarketDataInvalidError(f"price out of range for {code}")
            result[code] = value
        return result

    @staticmethod
    def _to_asset_data(asset: IranMarketAsset) -> IranMarketAssetData:
        definition = get_asset_definition(asset.code)
        if definition is None:
            raise IranMarketAssetNotFoundError(asset.code)
        return IranMarketAssetData(
            id=asset.id,
            code=asset.code,
            display_name=asset.display_name,
            category=asset.category,
            current_price=asset.current_price,
            previous_price=asset.previous_price,
            base_value=asset.base_value,
            last_successful_update=_as_utc(asset.last_successful_update),
            last_attempted_update=_as_utc(asset.last_attempted_update),
            is_active=asset.is_active,
            unit_label=definition.unit_label,
            change_amount=(
                abs(asset.current_price - asset.previous_price)
                if asset.current_price is not None and asset.previous_price is not None
                else None
            ),
            direction=(
                _direction(asset.previous_price, asset.current_price)
                if asset.current_price is not None
                else None
            ),
            created_at=_as_utc(asset.created_at) or _utc_now(),
            updated_at=_as_utc(asset.updated_at) or _utc_now(),
        )

    @staticmethod
    def _to_history_data(row, code: str) -> IranMarketHistoryData:
        return IranMarketHistoryData(
            id=row.id,
            asset_code=code,
            previous_price=row.previous_price,
            new_price=row.new_price,
            change_amount=row.change_amount,
            direction=row.direction,
            source=row.source,
            update_type=row.update_type,
            cycle_id=row.cycle_id,
            recorded_at=_as_utc(row.recorded_at) or _utc_now(),
        )

    def _housing_reference_price(self) -> int:
        configured = self._housing_reference_price_override
        if configured is None:
            configured = get_base_price_per_sqm(self._housing_reference_city)
        if configured is None:
            configured = sum(CITY_BASE_PRICE_PER_SQM.values()) // len(
                CITY_BASE_PRICE_PER_SQM
            )
        step = 100_000
        return max(step, (configured // step) * step)

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        # Store/log only a class plus a short generic label, never a URL,
        # Authorization header, token or raw provider response.
        if isinstance(exc, MarketDataError):
            return "external_market_data_unavailable"
        if isinstance(exc, IranMarketDataInvalidError):
            return "external_market_data_invalid"
        return type(exc).__name__


def _direction(previous: int | None, current: int | None) -> str:
    if previous is None or current is None or current == previous:
        return "unchanged"
    return "up" if current > previous else "down"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _positive_setting(value: int | None, env_name: str, default: int) -> int:
    if value is not None:
        return value if value >= 1 else default
    return _env_int(env_name, default, minimum=1)


def _env_int(name: str, default: int, *, minimum: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= minimum else default


def _env_int_or_none(name: str, *, minimum: int) -> int | None:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value >= minimum else None
