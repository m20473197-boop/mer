"""Focused tests for the four-asset Iranian market subsystem."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.core import constants
from app.database.database import Database
from app.database.repositories.iran_market_update_state_repository import (
    IranMarketUpdateStateRepository,
)
from app.game.market.catalog import (
    COIN_CODE,
    GOLD_CODE,
    HOUSING_CODE,
    IRAN_MARKET_ASSET_CODES,
    USD_CODE,
)
from app.game.market.provider import (
    MarketDataError,
    TGJUProvider,
    TGJUProviderConfig,
)
from app.services.iran_market_service import IranMarketService


class FakeProvider:
    source_name = "test-provider"

    def __init__(self) -> None:
        self.calls = 0
        self.fail = False
        self.prices = {
            USD_CODE: 600_000,
            GOLD_CODE: 50_000_000,
            COIN_CODE: 500_000_000,
        }

    async def fetch_prices(self):
        self.calls += 1
        if self.fail:
            raise MarketDataError("test outage")
        return dict(self.prices)


class StaleResponseProvider:
    source_name = "stale-response-provider"

    def __init__(self) -> None:
        self.calls = 0
        self.first_started = asyncio.Event()
        self.release_first = asyncio.Event()
        self.old_prices = {
            USD_CODE: 601_000,
            GOLD_CODE: 50_100_000,
            COIN_CODE: 501_000_000,
        }
        self.new_prices = {
            USD_CODE: 602_000,
            GOLD_CODE: 50_200_000,
            COIN_CODE: 502_000_000,
        }

    async def fetch_prices(self):
        self.calls += 1
        if self.calls == 1:
            self.first_started.set()
            await self.release_first.wait()
            return dict(self.old_prices)
        return dict(self.new_prices)


def _service(database: Database, provider, now_fn, **kwargs) -> IranMarketService:
    settings = {
        "update_interval_seconds": 3 * 24 * 60 * 60,
        "initial_retry_seconds": 1,
        "failure_retry_seconds": 1,
        "lock_seconds": 60,
    }
    settings.update(kwargs)
    return IranMarketService(
        database.session_factory,
        provider=provider,
        now_fn=now_fn,
        **settings,
    )


async def test_provider_parses_rial_and_normalizes_to_toman():
    provider = TGJUProvider(
        TGJUProviderConfig(
            base_url="https://example.test/profile",
            timeout_seconds=1,
            retry_attempts=1,
            retry_backoff_seconds=0,
        )
    )
    html = '<span data-col="info.last_trade.PDrCotVal">۲٬۳۵۹٬۷۵۰</span>'

    assert provider._parse_toman_price(html, USD_CODE) == 235_975


async def test_provider_requires_a_complete_positive_snapshot(monkeypatch):
    provider = TGJUProvider(
        TGJUProviderConfig(
            base_url="https://example.test/profile",
            timeout_seconds=1,
            retry_attempts=1,
            retry_backoff_seconds=0,
        )
    )
    marker = '<span data-col="info.last_trade.PDrCotVal">100</span>'
    monkeypatch.setattr(
        provider,
        "_fetch_page",
        lambda symbol: marker if symbol != "sekee" else "<html>missing</html>",
    )

    with pytest.raises(MarketDataError):
        await provider.fetch_prices()


async def test_market_has_exactly_four_assets_and_opening_is_read_only(db):
    now = [datetime(2026, 9, 12, tzinfo=timezone.utc)]
    provider = FakeProvider()
    service = _service(db, provider, lambda: now[0])

    first = await service.ensure_initial_state()
    assert first is not None and first.successful
    assert provider.calls == 1

    snapshot = await service.get_snapshot()
    assert tuple(asset.code for asset in snapshot.assets) == IRAN_MARKET_ASSET_CODES
    assert len(snapshot.assets) == 4
    assert snapshot.by_code(HOUSING_CODE).current_price == 55_000_000

    provider.fail = True
    before = provider.calls
    again = await service.get_snapshot()
    assert provider.calls == before
    assert tuple(asset.code for asset in again.assets) == IRAN_MARKET_ASSET_CODES


async def test_market_updates_history_and_preserves_valid_values_on_failure(db):
    now = [datetime(2026, 9, 12, tzinfo=timezone.utc)]
    provider = FakeProvider()
    service = _service(db, provider, lambda: now[0])

    await service.ensure_initial_state()
    old_snapshot = await service.get_snapshot()
    old_usd = old_snapshot.by_code(USD_CODE).current_price

    now[0] += timedelta(days=3, seconds=1)
    provider.prices[USD_CODE] = 610_000
    provider.prices[GOLD_CODE] = 49_000_000
    provider.prices[COIN_CODE] = 499_000_000
    second = await service.update_if_due()
    assert second.successful

    updated = await service.get_asset(USD_CODE)
    assert updated.current_price == 610_000
    assert updated.previous_price == old_usd
    assert updated.direction == "up"
    assert updated.change_amount == 10_000

    history = await service.get_history(USD_CODE)
    assert len(history) == 2
    assert history[0].source == "test-provider"
    assert history[0].previous_price == old_usd
    assert history[0].cycle_id != history[1].cycle_id

    now[0] += timedelta(days=3, seconds=1)
    provider.fail = True
    failed = await service.update_if_due()
    assert failed.attempted and not failed.successful
    preserved = await service.get_asset(USD_CODE)
    assert preserved.current_price == 610_000
    assert preserved.previous_price == old_usd

    async with db.session_factory() as session:
        state = await IranMarketUpdateStateRepository(session).get()
    assert state is not None
    assert state.last_error == "external_market_data_unavailable"


async def test_restart_uses_persisted_three_day_cursor(tmp_path):
    path = tmp_path / "market-restart.db"
    t0 = datetime(2026, 9, 12, tzinfo=timezone.utc)

    first_db = Database(f"sqlite+aiosqlite:///{path.as_posix()}")
    await first_db.create_all()
    first_provider = FakeProvider()
    first_service = _service(first_db, first_provider, lambda: t0)
    await first_service.ensure_initial_state()
    assert first_provider.calls == 1
    await first_db.dispose()

    second_db = Database(f"sqlite+aiosqlite:///{path.as_posix()}")
    await second_db.create_all()
    second_provider = FakeProvider()
    second_service = _service(
        second_db,
        second_provider,
        lambda: t0 + timedelta(days=1),
    )
    result = await second_service.ensure_initial_state()
    assert result is not None and result.skipped
    assert second_provider.calls == 0

    await second_db.dispose()


async def test_atomic_claim_allows_only_one_concurrent_cycle(tmp_path):
    path = tmp_path / "market-concurrency.db"
    database = Database(f"sqlite+aiosqlite:///{path.as_posix()}")
    await database.create_all()
    t0 = datetime(2026, 9, 12, tzinfo=timezone.utc)
    initial_provider = FakeProvider()
    await _service(database, initial_provider, lambda: t0).ensure_initial_state()

    due = t0 + timedelta(days=3, seconds=1)
    provider_a = FakeProvider()
    provider_b = FakeProvider()
    service_a = _service(database, provider_a, lambda: due)
    service_b = _service(database, provider_b, lambda: due)

    results = await asyncio.gather(
        service_a.update_if_due(),
        service_b.update_if_due(),
    )
    assert sum(result.successful for result in results) == 1
    assert provider_a.calls + provider_b.calls == 1

    await database.dispose()


async def test_stale_provider_response_cannot_overwrite_newer_cycle(tmp_path):
    path = tmp_path / "market-stale-response.db"
    database = Database(f"sqlite+aiosqlite:///{path.as_posix()}")
    await database.create_all()
    t0 = datetime(2026, 9, 12, tzinfo=timezone.utc)
    initial_provider = FakeProvider()
    await _service(database, initial_provider, lambda: t0).ensure_initial_state()

    due = t0 + timedelta(days=3, seconds=1)
    later = due + timedelta(seconds=2)
    provider = StaleResponseProvider()
    first = _service(database, provider, lambda: due, lock_seconds=1)
    second = _service(database, provider, lambda: later, lock_seconds=1)

    first_task = asyncio.create_task(first.update_if_due())
    await provider.first_started.wait()
    newer_result = await second.update_if_due()
    provider.release_first.set()
    older_result = await first_task

    assert newer_result.successful
    assert not older_result.successful
    assert older_result.error == "superseded"
    assert (await first.get_asset(USD_CODE)).current_price == 602_000

    await database.dispose()


async def test_housing_reference_city_and_initial_fetch_are_configurable(
    db, monkeypatch
):
    monkeypatch.setenv(constants.IRAN_MARKET_HOUSING_CITY_ENV, "مشهد")
    monkeypatch.setenv(constants.IRAN_MARKET_INITIAL_FETCH_ENV, "false")
    now = datetime(2026, 9, 12, tzinfo=timezone.utc)
    provider = FakeProvider()
    service = IranMarketService(
        db.session_factory,
        provider=provider,
        now_fn=lambda: now,
    )

    result = await service.ensure_initial_state()
    assert result is None
    assert provider.calls == 0
    snapshot = await service.get_snapshot()
    assert snapshot.by_code(HOUSING_CODE).current_price == 25_000_000


async def test_provider_settings_are_environment_configurable(monkeypatch):
    monkeypatch.setenv("IRAN_MARKET_PROVIDER_BASE_URL", "https://feed.example/quotes")
    monkeypatch.setenv("IRAN_MARKET_API_TIMEOUT_SECONDS", "4.5")
    monkeypatch.setenv("IRAN_MARKET_API_RETRY_ATTEMPTS", "5")
    monkeypatch.setenv("IRAN_MARKET_API_RETRY_BACKOFF_SECONDS", "0.25")
    monkeypatch.setenv(constants.IRAN_MARKET_PROVIDER_API_KEY_ENV, "secret-not-for-logs")

    config = TGJUProviderConfig.from_environment()
    assert config.base_url == "https://feed.example/quotes"
    assert config.timeout_seconds == 4.5
    assert config.retry_attempts == 5
    assert config.retry_backoff_seconds == 0.25
    assert config.api_key == "secret-not-for-logs"
