"""Admin-panel service — the transaction boundary of the management system.

Every admin-panel operation (dashboard, users, economy, real estate, jobs,
trading, bot settings, database tools, logs) runs through this service:

* Reads compose repository queries into admin DTOs.
* Mutations validate their input, apply the change and append an
  ``AdminAuditLog`` row — inside the *same* transaction whenever possible,
  so the audit trail can never drift from reality.
* Economy / settings mutations additionally refresh the in-memory runtime
  cache (``app.game.admin.runtime``), so synchronous call sites (pricing,
  XP, menus) follow admin changes immediately.

Money stays an exact integer (Toman) everywhere; floats are only used for
multipliers, exactly like the rest of the codebase.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import PROJECT_ROOT
from app.core.logging import LOG_FILE
from app.database.models.base import Base
from app.database.models.house import House
from app.database.models.land import Land
from app.database.models.player import Player
from app.database.repositories.admin_audit_log_repository import (
    AdminAuditLogRepository,
)
from app.database.repositories.bot_setting_repository import BotSettingRepository
from app.database.repositories.construction_project_repository import (
    ConstructionProjectRepository,
)
from app.database.repositories.economic_event_repository import (
    EconomicEventRepository,
)
from app.database.repositories.house_listing_repository import (
    HouseListingRepository,
)
from app.database.repositories.house_repository import HouseRepository
from app.database.repositories.house_sale_repository import HouseSaleRepository
from app.database.repositories.house_transaction_repository import (
    HouseTransactionRepository,
)
from app.database.repositories.job_repository import JobRepository
from app.database.repositories.land_repository import LandRepository
from app.database.repositories.land_transaction_repository import (
    LandTransactionRepository,
)
from app.database.repositories.market_asset_repository import MarketAssetRepository
from app.database.repositories.market_price_tick_repository import (
    MarketPriceTickRepository,
)
from app.database.repositories.player_job_repository import PlayerJobRepository
from app.database.repositories.player_repository import PlayerRepository
from app.database.repositories.renovation_project_repository import (
    RenovationProjectRepository,
)
from app.database.repositories.rental_contract_repository import (
    RentalContractRepository,
)
from app.database.repositories.xp_transaction_repository import (
    XPTransactionRepository,
)
from app.game.admin import dto as admin_dto
from app.game.admin import runtime as admin_runtime
from app.game.housing import pricing as house_pricing
from app.game.housing.catalog import get_neighborhood_multiplier
from app.game.housing.construction_year import validate_construction_year
from app.game.player.dto import MoneyChangeResult
from app.game.realestate import land_pricing
from app.game.realestate.land_pricing import quality_label_for
from app.game.shared.errors import (
    DomainError,
    InsufficientFundsError,
    InvalidAmountError,
    PlayerNotFoundError,
)

if TYPE_CHECKING:  # pragma: no cover — typing only, avoids import cycles
    from app.database.database import Database
    from app.services.housing_service import HousingService
    from app.services.level_service import LevelService
    from app.services.realestate_service import RealEstateService

logger = logging.getLogger(__name__)


class AdminError(DomainError):
    """Raised when an admin operation cannot be performed."""


T = TypeVar("T")

# --- Validation bounds ----------------------------------------------------------

MAX_MONEY_AMOUNT: int = 10**14
MAX_XP_AMOUNT: int = 10**9
MAX_LEVEL: int = 100

MARKET_CONDITIONS_MIN: float = 0.1
MARKET_CONDITIONS_MAX: float = 10.0
INFLATION_MIN: float = -90.0
INFLATION_MAX: float = 1000.0
EVENT_MULTIPLIER_MIN: float = 0.1
EVENT_MULTIPLIER_MAX: float = 10.0
EVENT_MAX_HOURS: int = 24 * 90

OVERRIDE_MIN_PER_MILLE: int = 10
OVERRIDE_MAX_PER_MILLE: int = 100_000
MAX_ASSET_PRICE: int = 10**18

XP_DIVISOR_MIN: int = 1
XP_DIVISOR_MAX: int = 10**12
XP_BAND_MIN: int = 0
XP_BAND_MAX: int = 100_000
MIN_WORK_MINUTES_MAX: int = 1440

# One-tap crisis preset: +35% on every real-estate price for 24 hours.
CRISIS_NAME: str = "بحران اقتصادی"
CRISIS_DESCRIPTION: str = "افزایش شدید قیمت‌ها در بازار ملک (فعال‌سازی دستی توسط ادمین)"
CRISIS_MULTIPLIER: float = 1.35
CRISIS_HOURS: int = 24

# Starter economy catalog: (code, Persian name, category, price in Toman).
DEFAULT_ASSETS: tuple[tuple[str, str, str, int], ...] = (
    ("USD", "دلار آمریکا", "currency", 1_050_000),
    ("EUR", "یورو", "currency", 1_230_000),
    ("USDT", "تتر", "crypto", 1_060_000),
    ("BTC", "بیت‌کوین", "crypto", 115_000_000_000_000),
    ("ETH", "اتریوم", "crypto", 3_800_000_000_000),
    ("GOLD18", "طلای ۱۸ عیار (گرم)", "gold", 9_800_000),
    ("COIN", "سکه بهار آزادی", "gold", 98_000_000),
)

BACKUP_PREFIX: str = "iran_backup_"
_BACKUP_NAME_RE = re.compile(r"^iran_backup_\d{8}_\d{6}(?:_\d+)?\.db$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _page(
    items: list[T], total: int, page: int, per_page: int
) -> admin_dto.Page[T]:
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    return admin_dto.Page(
        items=tuple(items), page=page, per_page=per_page,
        total=total, total_pages=total_pages,
    )


class AdminService:
    """All admin-panel use cases."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        level_service: LevelService | None = None,
        housing_service: HousingService | None = None,
        realestate_service: RealEstateService | None = None,
        admin_ids: tuple[int, ...] = (),
    ) -> None:
        self._session_factory = session_factory
        self._levels = level_service
        self._housing = housing_service
        self._realestate = realestate_service
        self._admin_ids = tuple(admin_ids)
        self._database: Database | None = None

    # --- Wiring ------------------------------------------------------------

    def set_admin_ids(self, admin_ids: tuple[int, ...]) -> None:
        """Protect these Telegram IDs from bans (called once at startup)."""
        self._admin_ids = tuple(admin_ids)

    def attach_database(self, database: Database) -> None:
        """Give the service engine access (needed for backup/restore)."""
        self._database = database

    # === Dashboard ============================================================

    async def get_dashboard(self) -> admin_dto.DashboardStats:
        """Aggregate every number the 📊 dashboard shows."""
        async with self._session_factory() as session:
            players = PlayerRepository(session)
            total_users = await players.count()
            active_24h = await players.count_active_since(
                _utc_now() - timedelta(hours=24)
            )
            banned = await players.count_banned()
            total_money = await players.sum_money()

            houses = await HouseRepository(session).count()
            lands = await LandRepository(session).count()
            jobs = len(await JobRepository(session).list_active())

            listings = HouseListingRepository(session)
            active_sales = await listings.count_active("sale")
            active_rents = await listings.count_active("rent")
            contracts = await RentalContractRepository(session).count_active()
            constructions = await ConstructionProjectRepository(
                session
            ).count_in_progress()
            renovations = await RenovationProjectRepository(
                session
            ).count_in_progress()
            events = await EconomicEventRepository(session).count_live(_utc_now())

            ping_ms = await self._ping_ms(session)
            dialect = session.bind.dialect.name if session.bind is not None else "?"

        db_size = self._sqlite_file_size()
        return admin_dto.DashboardStats(
            total_users=total_users,
            active_users_24h=active_24h,
            banned_users=banned,
            total_money=total_money,
            houses_count=houses,
            lands_count=lands,
            jobs_count=jobs,
            active_sale_listings=active_sales,
            active_rent_listings=active_rents,
            active_contracts=contracts,
            active_constructions=constructions,
            active_renovations=renovations,
            active_events=events,
            market_factor=admin_runtime.effective_market_factor(),
            db_dialect=str(dialect),
            db_size_bytes=db_size,
            db_ping_ms=ping_ms,
            db_tables=len(Base.metadata.tables),
            uptime_seconds=int(admin_runtime.uptime().total_seconds()),
            python_version=sys.version.split()[0],
        )

    @staticmethod
    async def _ping_ms(session: AsyncSession) -> float:
        started = time.perf_counter()
        await session.execute(text("SELECT 1"))
        return (time.perf_counter() - started) * 1000.0

    # === Users ================================================================

    @staticmethod
    def _to_summary(player: Player) -> admin_dto.AdminPlayerSummary:
        return admin_dto.AdminPlayerSummary(
            player_id=player.id,
            telegram_user_id=player.telegram_user_id,
            username=player.username,
            display_name=player.display_name,
            level=player.level,
            xp=player.xp,
            money=player.money,
            is_banned=player.is_banned,
        )

    async def list_users(
        self, page: int = 0, per_page: int = 8
    ) -> admin_dto.Page[admin_dto.AdminPlayerSummary]:
        async with self._session_factory() as session:
            repo = PlayerRepository(session)
            total = await repo.count()
            total_pages = max(1, (total + per_page - 1) // per_page)
            page = max(0, min(page, total_pages - 1))
            players = await repo.list_page(page * per_page, per_page)
            items = [self._to_summary(p) for p in players]
        return _page(items, total, page, per_page)

    async def search_users(self, query: str, limit: int = 10) -> list[admin_dto.AdminPlayerSummary]:
        async with self._session_factory() as session:
            players = await PlayerRepository(session).search(query, limit)
            return [self._to_summary(p) for p in players]

    async def get_user_detail(self, player_id: int) -> admin_dto.AdminPlayerDetail:
        async with self._session_factory() as session:
            player = await PlayerRepository(session).get_by_id(player_id)
            if player is None:
                raise PlayerNotFoundError(f"player_id={player_id} not found")
            houses = await HouseRepository(session).count_owned_by(player_id)
            lands = len(await LandRepository(session).list_by_owner(player_id))
            job_name: str | None = None
            employer: str | None = None
            player_job = await PlayerJobRepository(session).get_by_player_id(player_id)
            if player_job is not None:
                job = await JobRepository(session).get_by_id(player_job.job_id)
                if job is not None:
                    job_name, employer = job.name, job.employer
            return admin_dto.AdminPlayerDetail(
                summary=self._to_summary(player),
                houses_count=houses,
                lands_count=lands,
                job_name=job_name,
                employer=employer,
                created_at=player.created_at,
            )

    async def is_user_banned(self, telegram_user_id: int) -> bool:
        """Ban-guard lookup — unregistered users count as not banned."""
        async with self._session_factory() as session:
            player = await PlayerRepository(session).get_by_telegram_user_id(
                telegram_user_id
            )
            return bool(player is not None and player.is_banned)

    async def add_money(
        self, admin_telegram_id: int, player_id: int, amount: int
    ) -> MoneyChangeResult:
        self._require_money_amount(amount)
        async with self._session_factory() as session:
            players = PlayerRepository(session)
            player = await players.get_by_id(player_id)
            if player is None:
                raise PlayerNotFoundError(f"player_id={player_id} not found")
            await players.add_money(player_id, amount)
            balance = await players.get_money(player_id)
            assert balance is not None
            await self._audit(
                session, admin_telegram_id, "user_add_money",
                target_type="player", target_id=player_id,
                details=f"amount={amount} balance_after={balance}",
            )
            await session.commit()
        logger.info("Admin %s added %s to player %s", admin_telegram_id, amount, player_id)
        return MoneyChangeResult(player_id=player_id, amount=amount, balance_after=balance)

    async def remove_money(
        self, admin_telegram_id: int, player_id: int, amount: int
    ) -> MoneyChangeResult:
        self._require_money_amount(amount)
        async with self._session_factory() as session:
            players = PlayerRepository(session)
            player = await players.get_by_id(player_id)
            if player is None:
                raise PlayerNotFoundError(f"player_id={player_id} not found")
            # The wallet invariant holds for admins too: never below zero.
            if not await players.remove_money_if_enough(player_id, amount):
                raise InsufficientFundsError(
                    f"player_id={player_id} cannot afford {amount}"
                )
            balance = await players.get_money(player_id)
            assert balance is not None
            await self._audit(
                session, admin_telegram_id, "user_remove_money",
                target_type="player", target_id=player_id,
                details=f"amount={amount} balance_after={balance}",
            )
            await session.commit()
        logger.info(
            "Admin %s removed %s from player %s", admin_telegram_id, amount, player_id
        )
        return MoneyChangeResult(player_id=player_id, amount=amount, balance_after=balance)

    async def add_xp(self, admin_telegram_id: int, player_id: int, amount: int):
        self._require_xp_amount(amount)
        levels = self._require_levels()
        result = await levels.add_xp(player_id, amount, reason="admin_add")
        await self._audit_detached(
            admin_telegram_id, "user_add_xp",
            target_type="player", target_id=player_id,
            details=f"amount={amount} xp_after={result.xp_after} level={result.new_level}",
        )
        return result

    async def remove_xp(self, admin_telegram_id: int, player_id: int, amount: int):
        self._require_xp_amount(amount)
        levels = self._require_levels()
        result = await levels.remove_xp(player_id, amount, reason="admin_remove")
        await self._audit_detached(
            admin_telegram_id, "user_remove_xp",
            target_type="player", target_id=player_id,
            details=f"amount={amount} xp_after={result.xp_after} level={result.new_level}",
        )
        return result

    async def set_level(self, admin_telegram_id: int, player_id: int, level: int):
        if level < 1 or level > MAX_LEVEL:
            raise InvalidAmountError(f"level must be within 1..{MAX_LEVEL}")
        levels = self._require_levels()
        result = await levels.set_level(player_id, level, reason="admin_set_level")
        await self._audit_detached(
            admin_telegram_id, "user_set_level",
            target_type="player", target_id=player_id,
            details=f"level={level} xp_after={result.xp_after}",
        )
        return result

    async def ban_user(
        self, admin_telegram_id: int, player_id: int
    ) -> admin_dto.AdminPlayerSummary:
        async with self._session_factory() as session:
            players = PlayerRepository(session)
            player = await players.get_by_id(player_id)
            if player is None:
                raise PlayerNotFoundError(f"player_id={player_id} not found")
            if player.telegram_user_id in self._admin_ids:
                raise AdminError("admins cannot be banned")
            # Capture everything before the UPDATE expires the instance.
            summary = self._to_summary(player)
            await players.set_banned(player_id, True)
            await self._audit(
                session, admin_telegram_id, "user_ban",
                target_type="player", target_id=player_id,
                details=f"tg={summary.telegram_user_id} name={summary.display_name}",
            )
            await session.commit()
            return admin_dto.AdminPlayerSummary(
                player_id=summary.player_id,
                telegram_user_id=summary.telegram_user_id,
                username=summary.username,
                display_name=summary.display_name,
                level=summary.level,
                xp=summary.xp,
                money=summary.money,
                is_banned=True,
            )

    async def unban_user(
        self, admin_telegram_id: int, player_id: int
    ) -> admin_dto.AdminPlayerSummary:
        async with self._session_factory() as session:
            players = PlayerRepository(session)
            player = await players.get_by_id(player_id)
            if player is None:
                raise PlayerNotFoundError(f"player_id={player_id} not found")
            summary = self._to_summary(player)
            await players.set_banned(player_id, False)
            await self._audit(
                session, admin_telegram_id, "user_unban",
                target_type="player", target_id=player_id,
                details=f"tg={summary.telegram_user_id} name={summary.display_name}",
            )
            await session.commit()
            return admin_dto.AdminPlayerSummary(
                player_id=summary.player_id,
                telegram_user_id=summary.telegram_user_id,
                username=summary.username,
                display_name=summary.display_name,
                level=summary.level,
                xp=summary.xp,
                money=summary.money,
                is_banned=False,
            )

    async def get_user_transactions(
        self, player_id: int, limit: int = 20
    ) -> list[admin_dto.UserTxEntry]:
        """Merged money history of one player, newest first."""
        async with self._session_factory() as session:
            if not await PlayerRepository(session).exists(player_id):
                raise PlayerNotFoundError(f"player_id={player_id} not found")
            sales_repo = HouseSaleRepository(session)
            bought = await sales_repo.list_by_buyer(player_id, limit)
            sold = await sales_repo.list_by_seller(player_id, limit)
            house_tx_repo = HouseTransactionRepository(session)
            paid = await house_tx_repo.list_by_payer(player_id, limit)
            received = await house_tx_repo.list_by_payee(player_id, limit)
            land_paid = await LandTransactionRepository(session).list_by_payer(
                player_id, limit
            )

        entries: list[admin_dto.UserTxEntry] = []
        for sale in bought:
            entries.append(admin_dto.UserTxEntry(
                kind="sale_buy", label=f"خرید خانه #{sale.house_id}",
                amount=sale.price, incoming=False, created_at=sale.created_at,
            ))
        for sale in sold:
            entries.append(admin_dto.UserTxEntry(
                kind="sale_sell", label=f"فروش خانه #{sale.house_id}",
                amount=sale.price, incoming=True, created_at=sale.created_at,
            ))
        for tx in paid:
            entries.append(admin_dto.UserTxEntry(
                kind="house_tx", label=tx.note or _house_tx_label(tx.transaction_type, tx.house_id),
                amount=tx.amount, incoming=False, created_at=tx.created_at,
            ))
        for tx in received:
            entries.append(admin_dto.UserTxEntry(
                kind="house_tx", label=tx.note or _house_tx_label(tx.transaction_type, tx.house_id),
                amount=tx.amount, incoming=True, created_at=tx.created_at,
            ))
        for tx in land_paid:
            entries.append(admin_dto.UserTxEntry(
                kind="land_tx", label=tx.note or f"خرید زمین #{tx.land_id}",
                amount=tx.amount, incoming=False, created_at=tx.created_at,
            ))
        entries.sort(key=lambda e: e.created_at, reverse=True)
        return entries[:limit]

    async def get_user_properties(
        self, player_id: int
    ) -> tuple[list[admin_dto.HouseAdminEntry], list[admin_dto.LandAdminEntry]]:
        """Houses + lands owned by one player (for the profile screen)."""
        housing = self._require_housing()
        realestate = self._require_realestate()
        async with self._session_factory() as session:
            player = await PlayerRepository(session).get_by_id(player_id)
            if player is None:
                raise PlayerNotFoundError(f"player_id={player_id} not found")
            houses = await HouseRepository(session).list_by_owner(player_id)
            lands = await LandRepository(session).list_by_owner(player_id)
            house_entries = [
                admin_dto.HouseAdminEntry(
                    id=h.id, city=h.city, neighborhood=h.neighborhood,
                    area_sqm=h.area_sqm, owner_player_id=player_id,
                    owner_name=player.display_name,
                    market_value=housing.estimate_value(h),
                    has_override=h.price_override_per_mille is not None,
                )
                for h in houses
            ]
            land_entries = [
                admin_dto.LandAdminEntry(
                    id=l.id, city=l.city, neighborhood=l.neighborhood,
                    area_sqm=l.area_sqm, owner_player_id=player_id,
                    owner_name=player.display_name,
                    market_value=realestate.estimate_land_value(l),
                    built_house_id=l.built_house_id,
                    has_override=l.price_override_per_mille is not None,
                )
                for l in lands
            ]
        return house_entries, land_entries

    # === Economy ==============================================================

    async def ensure_economy_seeded(self) -> None:
        """Seed the starter assets + default settings once (idempotent)."""
        async with self._session_factory() as session:
            assets = MarketAssetRepository(session)
            ticks = MarketPriceTickRepository(session)
            for code, name, category, price in DEFAULT_ASSETS:
                existing = await assets.get_by_code(code)
                if existing is None:
                    created = await assets.create(
                        code=code, name=name, category=category, price=price
                    )
                    await ticks.add(created.id, price)
            settings = BotSettingRepository(session)
            current = await settings.get_all()
            defaults = {
                admin_runtime.KEY_MARKET_CONDITIONS: "1.0",
                admin_runtime.KEY_INFLATION_RATE: "0",
                admin_runtime.KEY_PURCHASE_XP_DIVISOR: "20000000",
                admin_runtime.KEY_PURCHASE_XP_MIN: "5",
                admin_runtime.KEY_PURCHASE_XP_MAX: "300",
                admin_runtime.KEY_CONSTRUCTION_XP_DIVISOR: "30000000",
                admin_runtime.KEY_MIN_WORK_MINUTES: "1",
                "jobs_enabled": "1",
                "housing_enabled": "1",
                "realestate_enabled": "1",
            }
            for key, value in defaults.items():
                if key not in current:
                    await settings.set(key, value)
            await session.commit()
        logger.info("Economy catalog ensured (%s assets)", len(DEFAULT_ASSETS))

    async def refresh_runtime(self) -> float:
        """Reload the runtime cache from the DB; returns the effective factor."""
        async with self._session_factory() as session:
            stored = await BotSettingRepository(session).get_all()
            await EconomicEventRepository(session).deactivate_expired(_utc_now())
            live = await EconomicEventRepository(session).list_live(_utc_now())
            await session.commit()
        self._apply_settings_to_runtime(stored)
        multiplier = 1.0
        for event in live:
            multiplier *= event.multiplier
        admin_runtime.set_events_multiplier(multiplier)
        return admin_runtime.effective_market_factor()

    @staticmethod
    def _apply_settings_to_runtime(stored: dict[str, str]) -> None:
        def _float(key: str) -> float | None:
            try:
                return float(stored[key])
            except (KeyError, ValueError):
                return None

        def _int(key: str) -> int | None:
            try:
                return int(float(stored[key]))
            except (KeyError, ValueError):
                return None

        for key, parser in (
            (admin_runtime.KEY_MARKET_CONDITIONS, _float),
            (admin_runtime.KEY_INFLATION_RATE, _float),
            (admin_runtime.KEY_PURCHASE_XP_DIVISOR, _int),
            (admin_runtime.KEY_PURCHASE_XP_MIN, _int),
            (admin_runtime.KEY_PURCHASE_XP_MAX, _int),
            (admin_runtime.KEY_CONSTRUCTION_XP_DIVISOR, _int),
            (admin_runtime.KEY_MIN_WORK_MINUTES, _int),
        ):
            parsed = parser(key)
            if parsed is not None:
                admin_runtime.set_override(key, parsed)
        for feature in admin_runtime.FEATURES:
            key = f"{feature}_enabled"
            if key in stored:
                admin_runtime.set_override(key, stored[key].strip() == "1")

    async def get_economy_overview(self) -> admin_dto.EconomyOverview:
        # Settle first so the screen (and the cached factor) is never stale.
        await self.settle_events()
        async with self._session_factory() as session:
            assets = await MarketAssetRepository(session).list_all()
            live = await EconomicEventRepository(session).list_live(_utc_now())
        now = _utc_now()
        return admin_dto.EconomyOverview(
            base_market_conditions=admin_runtime.market_conditions_base(),
            inflation_rate=admin_runtime.inflation_rate(),
            events_multiplier=admin_runtime.events_multiplier(),
            effective_factor=admin_runtime.effective_market_factor(),
            assets=tuple(self._to_asset(a) for a in assets),
            live_events=tuple(self._to_event(e, now) for e in live),
        )

    @staticmethod
    def _to_asset(asset) -> admin_dto.MarketAssetData:
        return admin_dto.MarketAssetData(
            id=asset.id, code=asset.code, name=asset.name,
            category=asset.category, price=asset.price,
            updated_at=asset.updated_at,
        )

    @staticmethod
    def _to_event(event, now: datetime) -> admin_dto.EconomicEventData:
        starts = _as_utc(event.starts_at)
        ends = _as_utc(event.ends_at)
        return admin_dto.EconomicEventData(
            id=event.id, name=event.name, description=event.description,
            multiplier=event.multiplier, starts_at=starts, ends_at=ends,
            is_active=event.is_active,
            is_live=bool(event.is_active and starts <= now <= ends),
            created_by=event.created_by,
        )

    async def set_market_conditions(
        self, admin_telegram_id: int, value: float
    ) -> float:
        if not (MARKET_CONDITIONS_MIN <= value <= MARKET_CONDITIONS_MAX):
            raise InvalidAmountError(
                f"market conditions must be within "
                f"{MARKET_CONDITIONS_MIN}..{MARKET_CONDITIONS_MAX}"
            )
        async with self._session_factory() as session:
            await BotSettingRepository(session).set(
                admin_runtime.KEY_MARKET_CONDITIONS, repr(value)
            )
            await self._audit(
                session, admin_telegram_id, "econ_market",
                details=f"market_conditions={value} "
                f"effective={admin_runtime.effective_market_factor():.4f}",
            )
            await session.commit()
        admin_runtime.set_override(admin_runtime.KEY_MARKET_CONDITIONS, value)
        return admin_runtime.effective_market_factor()

    async def set_inflation(self, admin_telegram_id: int, percent: float) -> float:
        if not (INFLATION_MIN <= percent <= INFLATION_MAX):
            raise InvalidAmountError(
                f"inflation must be within {INFLATION_MIN}..{INFLATION_MAX} percent"
            )
        async with self._session_factory() as session:
            await BotSettingRepository(session).set(
                admin_runtime.KEY_INFLATION_RATE, repr(percent)
            )
            await self._audit(
                session, admin_telegram_id, "econ_inflation",
                details=f"inflation={percent}% "
                f"effective={admin_runtime.effective_market_factor():.4f}",
            )
            await session.commit()
        admin_runtime.set_override(admin_runtime.KEY_INFLATION_RATE, percent)
        return admin_runtime.effective_market_factor()

    async def list_assets(self) -> list[admin_dto.MarketAssetData]:
        async with self._session_factory() as session:
            assets = await MarketAssetRepository(session).list_all()
            return [self._to_asset(a) for a in assets]

    async def set_asset_price(
        self, admin_telegram_id: int, code: str, price: int
    ) -> admin_dto.MarketAssetData:
        if price <= 0 or price > MAX_ASSET_PRICE:
            raise InvalidAmountError("asset price out of range")
        async with self._session_factory() as session:
            assets = MarketAssetRepository(session)
            asset = await assets.get_by_code(code)
            if asset is None:
                raise AdminError(f"unknown asset: {code}")
            before = asset.price
            await assets.update_price(code, price)
            await MarketPriceTickRepository(session).add(asset.id, price)
            await self._audit(
                session, admin_telegram_id, "asset_price",
                target_type="asset", target_id=asset.id,
                details=f"code={code} {before}->{price}",
            )
            await session.commit()
            updated = await assets.get_by_code(code)
            assert updated is not None
            return self._to_asset(updated)

    async def get_asset_history(
        self, code: str, limit: int = 15
    ) -> tuple[admin_dto.MarketAssetData, list[admin_dto.AssetPriceTickData]]:
        async with self._session_factory() as session:
            asset = await MarketAssetRepository(session).get_by_code(code)
            if asset is None:
                raise AdminError(f"unknown asset: {code}")
            ticks = await MarketPriceTickRepository(session).list_by_asset(
                asset.id, limit
            )
            return self._to_asset(asset), [
                admin_dto.AssetPriceTickData(price=t.price, created_at=t.created_at)
                for t in ticks
            ]

    async def create_event(
        self,
        admin_telegram_id: int,
        *,
        name: str,
        description: str,
        multiplier: float,
        duration_hours: int,
    ) -> admin_dto.EconomicEventData:
        clean_name = " ".join(name.split())[:64]
        if not clean_name:
            raise InvalidAmountError("event name must not be empty")
        if not (EVENT_MULTIPLIER_MIN <= multiplier <= EVENT_MULTIPLIER_MAX):
            raise InvalidAmountError(
                f"multiplier must be within "
                f"{EVENT_MULTIPLIER_MIN}..{EVENT_MULTIPLIER_MAX}"
            )
        if duration_hours <= 0 or duration_hours > EVENT_MAX_HOURS:
            raise InvalidAmountError(
                f"duration must be within 1..{EVENT_MAX_HOURS} hours"
            )
        now = _utc_now()
        async with self._session_factory() as session:
            events = EconomicEventRepository(session)
            event = await events.create(
                name=clean_name,
                description=" ".join(description.split())[:256],
                multiplier=multiplier,
                starts_at=now,
                ends_at=now + timedelta(hours=duration_hours),
                created_by=admin_telegram_id,
            )
            await self._audit(
                session, admin_telegram_id, "event_create",
                target_type="event", target_id=event.id,
                details=f"name={clean_name} x{multiplier} hours={duration_hours}",
            )
            await session.commit()
            live = await EconomicEventRepository(session).list_live(_utc_now())
        self._recache_events(live)
        return self._to_event(event, now)

    async def end_event(
        self, admin_telegram_id: int, event_id: int
    ) -> admin_dto.EconomicEventData:
        async with self._session_factory() as session:
            events = EconomicEventRepository(session)
            event = await events.get_by_id(event_id)
            if event is None:
                raise AdminError(f"event {event_id} not found")
            if not event.is_active:
                raise AdminError(f"event {event_id} is already over")
            await events.deactivate(event_id)
            await self._audit(
                session, admin_telegram_id, "event_end",
                target_type="event", target_id=event_id,
                details=f"name={event.name}",
            )
            await session.commit()
            live = await EconomicEventRepository(session).list_live(_utc_now())
        self._recache_events(live)
        event = await self._get_event(event_id)
        return self._to_event(event, _utc_now())

    async def trigger_crisis(self, admin_telegram_id: int) -> admin_dto.EconomicEventData:
        """One-tap manual crisis: +35% on every real-estate price for 24h."""
        event = await self.create_event(
            admin_telegram_id,
            name=CRISIS_NAME,
            description=CRISIS_DESCRIPTION,
            multiplier=CRISIS_MULTIPLIER,
            duration_hours=CRISIS_HOURS,
        )
        await self._audit_detached(
            admin_telegram_id, "event_crisis",
            target_type="event", target_id=event.id,
            details=f"x{CRISIS_MULTIPLIER} for {CRISIS_HOURS}h",
        )
        return event

    async def settle_events(self) -> int:
        """Switch off expired events and refresh the cached event factor."""
        async with self._session_factory() as session:
            events = EconomicEventRepository(session)
            ended = await events.deactivate_expired(_utc_now())
            live = await events.list_live(_utc_now())
            await session.commit()
        self._recache_events(live)
        return ended

    @staticmethod
    def _recache_events(live) -> None:
        multiplier = 1.0
        for event in live:
            multiplier *= event.multiplier
        admin_runtime.set_events_multiplier(multiplier)

    async def _get_event(self, event_id: int):
        async with self._session_factory() as session:
            event = await EconomicEventRepository(session).get_by_id(event_id)
            if event is None:  # pragma: no cover — guarded upstream
                raise AdminError(f"event {event_id} not found")
            return event

    # === Real estate ============================================================

    async def list_houses(
        self, page: int = 0, per_page: int = 6
    ) -> admin_dto.Page[admin_dto.HouseAdminEntry]:
        housing = self._require_housing()
        async with self._session_factory() as session:
            houses = HouseRepository(session)
            total = await houses.count()
            total_pages = max(1, (total + per_page - 1) // per_page)
            page = max(0, min(page, total_pages - 1))
            rows = await houses.list_page(page * per_page, per_page)
            players = PlayerRepository(session)
            items: list[admin_dto.HouseAdminEntry] = []
            for house in rows:
                owner_name = await self._display_name(players, house.owner_player_id)
                items.append(admin_dto.HouseAdminEntry(
                    id=house.id, city=house.city, neighborhood=house.neighborhood,
                    area_sqm=house.area_sqm, owner_player_id=house.owner_player_id,
                    owner_name=owner_name,
                    market_value=housing.estimate_value(house),
                    has_override=house.price_override_per_mille is not None,
                ))
        return _page(items, total, page, per_page)

    async def get_house_detail(self, house_id: int) -> admin_dto.HouseDetailAdmin:
        housing = self._require_housing()
        async with self._session_factory() as session:
            house = await HouseRepository(session).get_by_id(house_id)
            if house is None:
                raise AdminError(f"house {house_id} not found")
            players = PlayerRepository(session)
            owner_name = await self._display_name(players, house.owner_player_id)
            listings = HouseListingRepository(session)
            sale = await listings.get_active_sale_by_house(house_id)
            rent = await listings.get_active_rent_by_house(house_id)
            contract = await RentalContractRepository(session).get_active_by_house(
                house_id
            )
            tenant_name = None
            if contract is not None:
                tenant_name = await self._display_name(
                    players, contract.tenant_player_id
                )
            return admin_dto.HouseDetailAdmin(
                house=housing._to_house_dto(house),  # noqa: SLF001 — same layer
                market_value=housing.estimate_value(house),
                owner_name=owner_name,
                active_sale_price=sale.price if sale else None,
                active_rent=(rent.deposit, rent.price) if rent else None,
                active_contract_id=contract.id if contract else None,
                tenant_name=tenant_name,
            )

    async def update_house(
        self, admin_telegram_id: int, house_id: int, field: str, value: object
    ) -> admin_dto.HouseDetailAdmin:
        """Edit one validated house attribute (admin panel)."""
        async with self._session_factory() as session:
            houses = HouseRepository(session)
            house = await houses.get_by_id(house_id)
            if house is None:
                raise AdminError(f"house {house_id} not found")
            clean = self._clean_house_field(field, value, house)
            before = getattr(house, field)
            await houses.update_attributes(house_id, **{field: clean})
            await self._audit(
                session, admin_telegram_id, "house_update",
                target_type="house", target_id=house_id,
                details=f"{field}: {before}->{clean}",
            )
            await session.commit()
        return await self.get_house_detail(house_id)

    @staticmethod
    def _clean_house_field(field: str, value: object, house: House) -> object:
        if field == "area_sqm":
            area = int(value)  # type: ignore[arg-type]
            if not 10 <= area <= 5000:
                raise InvalidAmountError("area must be within 10..5000 sqm")
            return area
        if field in ("bedrooms", "living_rooms"):
            rooms = int(value)  # type: ignore[arg-type]
            if not 0 <= rooms <= 20:
                raise InvalidAmountError("room count must be within 0..20")
            return rooms
        if field == "bathrooms":
            rooms = int(value)  # type: ignore[arg-type]
            if not 1 <= rooms <= 10:
                raise InvalidAmountError("bathrooms must be within 1..10")
            return rooms
        if field == "kitchen_type":
            if value not in house_pricing.KITCHEN_FACTORS:
                raise InvalidAmountError("unknown kitchen type")
            return value
        if field == "quality":
            if value not in house_pricing.QUALITY_FACTORS:
                raise InvalidAmountError("unknown quality level")
            return value
        if field == "construction_year":
            year = int(value)  # type: ignore[arg-type]
            validate_construction_year(year)
            return year
        if field in ("city", "neighborhood"):
            city = value if field == "city" else house.city
            neighborhood = value if field == "neighborhood" else house.neighborhood
            if get_neighborhood_multiplier(str(city), str(neighborhood)) is None:
                raise InvalidAmountError("unknown city/neighborhood pair")
            return str(value)
        if field in ("parking", "elevator", "storage"):
            return bool(value)
        raise AdminError(f"field {field} is not editable")

    async def update_house_location(
        self, admin_telegram_id: int, house_id: int, city: str, neighborhood: str
    ) -> admin_dto.HouseDetailAdmin:
        """Move a house to a new validated city/neighborhood pair."""
        if get_neighborhood_multiplier(city, neighborhood) is None:
            raise InvalidAmountError("unknown city/neighborhood pair")
        async with self._session_factory() as session:
            houses = HouseRepository(session)
            house = await houses.get_by_id(house_id)
            if house is None:
                raise AdminError(f"house {house_id} not found")
            before = f"{house.city}/{house.neighborhood}"
            await houses.update_attributes(
                house_id, city=city, neighborhood=neighborhood
            )
            await self._audit(
                session, admin_telegram_id, "house_update",
                target_type="house", target_id=house_id,
                details=f"location: {before}->{city}/{neighborhood}",
            )
            await session.commit()
        return await self.get_house_detail(house_id)

    async def set_house_override(
        self, admin_telegram_id: int, house_id: int, per_mille: int | None
    ) -> admin_dto.HouseDetailAdmin:
        if per_mille is not None and not (
            OVERRIDE_MIN_PER_MILLE <= per_mille <= OVERRIDE_MAX_PER_MILLE
        ):
            raise InvalidAmountError(
                f"override must be within "
                f"{OVERRIDE_MIN_PER_MILLE}..{OVERRIDE_MAX_PER_MILLE} per-mille"
            )
        async with self._session_factory() as session:
            houses = HouseRepository(session)
            if await houses.get_by_id(house_id) is None:
                raise AdminError(f"house {house_id} not found")
            await houses.update_attributes(
                house_id, price_override_per_mille=per_mille
            )
            await self._audit(
                session, admin_telegram_id, "house_override",
                target_type="house", target_id=house_id,
                details=f"per_mille={per_mille}",
            )
            await session.commit()
        return await self.get_house_detail(house_id)

    async def list_lands(
        self, page: int = 0, per_page: int = 6
    ) -> admin_dto.Page[admin_dto.LandAdminEntry]:
        realestate = self._require_realestate()
        async with self._session_factory() as session:
            lands = LandRepository(session)
            total = await lands.count()
            total_pages = max(1, (total + per_page - 1) // per_page)
            page = max(0, min(page, total_pages - 1))
            rows = await lands.list_page(page * per_page, per_page)
            players = PlayerRepository(session)
            items: list[admin_dto.LandAdminEntry] = []
            for land in rows:
                owner_name = await self._display_name(players, land.owner_player_id)
                items.append(admin_dto.LandAdminEntry(
                    id=land.id, city=land.city, neighborhood=land.neighborhood,
                    area_sqm=land.area_sqm, owner_player_id=land.owner_player_id,
                    owner_name=owner_name,
                    market_value=realestate.estimate_land_value(land),
                    built_house_id=land.built_house_id,
                    has_override=land.price_override_per_mille is not None,
                ))
        return _page(items, total, page, per_page)

    async def get_land_detail(self, land_id: int) -> admin_dto.LandDetailAdmin:
        realestate = self._require_realestate()
        async with self._session_factory() as session:
            land = await LandRepository(session).get_by_id(land_id)
            if land is None:
                raise AdminError(f"land {land_id} not found")
            owner_name = await self._display_name(
                PlayerRepository(session), land.owner_player_id
            )
            value = realestate.estimate_land_value(land)
            per_sqm = land_pricing.estimate_land_price_per_sqm(
                realestate._land_pricing_input(land)  # noqa: SLF001 — same layer
            )
            return admin_dto.LandDetailAdmin(
                land=realestate._to_land_dto(land),  # noqa: SLF001 — same layer
                market_value=value,
                price_per_sqm=per_sqm,
                owner_name=owner_name,
            )

    async def update_land(
        self, admin_telegram_id: int, land_id: int, field: str, value: object
    ) -> admin_dto.LandDetailAdmin:
        async with self._session_factory() as session:
            lands = LandRepository(session)
            land = await lands.get_by_id(land_id)
            if land is None:
                raise AdminError(f"land {land_id} not found")
            updates = self._clean_land_fields(field, value, land)
            before = {key: getattr(land, key) for key in updates}
            await lands.update_attributes(land_id, **updates)
            await self._audit(
                session, admin_telegram_id, "land_update",
                target_type="land", target_id=land_id,
                details=", ".join(
                    f"{key}: {before[key]}->{val}"
                    for key, val in updates.items()
                ),
            )
            await session.commit()
        return await self.get_land_detail(land_id)

    @staticmethod
    def _clean_land_fields(field: str, value: object, land: Land) -> dict[str, object]:
        if field == "area_sqm":
            area = int(value)  # type: ignore[arg-type]
            if not 30 <= area <= 100_000:
                raise InvalidAmountError("area must be within 30..100000 sqm")
            return {"area_sqm": area}
        if field in ("city", "neighborhood"):
            city = str(value) if field == "city" else land.city
            neighborhood = str(value) if field == "neighborhood" else land.neighborhood
            if get_neighborhood_multiplier(city, neighborhood) is None:
                raise InvalidAmountError("unknown city/neighborhood pair")
            # Keep the display label consistent with the live multiplier.
            updates: dict[str, object] = {field: str(value)}
            label = quality_label_for(city, neighborhood)
            if label is not None:
                updates["location_quality"] = label
            return updates
        raise AdminError(f"field {field} is not editable")

    async def update_land_location(
        self, admin_telegram_id: int, land_id: int, city: str, neighborhood: str
    ) -> admin_dto.LandDetailAdmin:
        """Move a parcel to a new validated city/neighborhood pair."""
        if get_neighborhood_multiplier(city, neighborhood) is None:
            raise InvalidAmountError("unknown city/neighborhood pair")
        async with self._session_factory() as session:
            lands = LandRepository(session)
            land = await lands.get_by_id(land_id)
            if land is None:
                raise AdminError(f"land {land_id} not found")
            updates: dict[str, object] = {"city": city, "neighborhood": neighborhood}
            label = quality_label_for(city, neighborhood)
            if label is not None:
                updates["location_quality"] = label
            before = f"{land.city}/{land.neighborhood}"
            await lands.update_attributes(land_id, **updates)
            await self._audit(
                session, admin_telegram_id, "land_update",
                target_type="land", target_id=land_id,
                details=f"location: {before}->{city}/{neighborhood}",
            )
            await session.commit()
        return await self.get_land_detail(land_id)

    async def set_land_override(
        self, admin_telegram_id: int, land_id: int, per_mille: int | None
    ) -> admin_dto.LandDetailAdmin:
        if per_mille is not None and not (
            OVERRIDE_MIN_PER_MILLE <= per_mille <= OVERRIDE_MAX_PER_MILLE
        ):
            raise InvalidAmountError(
                f"override must be within "
                f"{OVERRIDE_MIN_PER_MILLE}..{OVERRIDE_MAX_PER_MILLE} per-mille"
            )
        async with self._session_factory() as session:
            lands = LandRepository(session)
            if await lands.get_by_id(land_id) is None:
                raise AdminError(f"land {land_id} not found")
            await lands.update_attributes(land_id, price_override_per_mille=per_mille)
            await self._audit(
                session, admin_telegram_id, "land_override",
                target_type="land", target_id=land_id,
                details=f"per_mille={per_mille}",
            )
            await session.commit()
        return await self.get_land_detail(land_id)

    async def list_active_listings(
        self, page: int = 0, per_page: int = 6, listing_type: str | None = None
    ) -> admin_dto.Page[admin_dto.ListingAdminEntry]:
        housing = self._require_housing()
        async with self._session_factory() as session:
            listings = HouseListingRepository(session)
            total = await listings.count_active(listing_type)
            total_pages = max(1, (total + per_page - 1) // per_page)
            page = max(0, min(page, total_pages - 1))
            rows = await listings.list_active_page(
                listing_type, page * per_page, per_page
            )
            houses = HouseRepository(session)
            players = PlayerRepository(session)
            items: list[admin_dto.ListingAdminEntry] = []
            for listing in rows:
                house = await houses.get_by_id(listing.house_id)
                label = (
                    housing.house_label(house)
                    if house is not None
                    else f"#{listing.house_id}"
                )
                items.append(admin_dto.ListingAdminEntry(
                    listing_id=listing.id, house_id=listing.house_id,
                    house_label=label, listing_type=listing.listing_type,
                    price=listing.price, deposit=listing.deposit,
                    owner_player_id=listing.owner_player_id,
                    owner_name=await self._display_name(
                        players, listing.owner_player_id
                    ),
                ))
        return _page(items, total, page, per_page)

    async def close_listing(
        self, admin_telegram_id: int, listing_id: int
    ) -> None:
        """Remove an illegal/problematic listing from the market."""
        async with self._session_factory() as session:
            listings = HouseListingRepository(session)
            listing = await listings.get_by_id(listing_id)
            if listing is None or listing.status != "active":
                raise AdminError(f"listing {listing_id} is not active")
            await listings.close(listing_id, _utc_now())
            await self._audit(
                session, admin_telegram_id, "listing_close",
                target_type="listing", target_id=listing_id,
                details=f"house={listing.house_id} type={listing.listing_type} "
                f"price={listing.price}",
            )
            await session.commit()
        logger.info("Admin %s closed listing %s", admin_telegram_id, listing_id)

    async def list_contracts(
        self, page: int = 0, per_page: int = 6, *, active_only: bool = True
    ) -> admin_dto.Page[admin_dto.ContractAdminEntry]:
        housing = self._require_housing()
        async with self._session_factory() as session:
            contracts = RentalContractRepository(session)
            if active_only:
                # Active count + active page.
                total = await contracts.count_active()
            else:  # pragma: no cover — admin UI only lists active ones
                total = await contracts.count_active()
            total_pages = max(1, (total + per_page - 1) // per_page)
            page = max(0, min(page, total_pages - 1))
            rows = await contracts.list_page(
                page * per_page, per_page, active_only=active_only
            )
            houses = HouseRepository(session)
            players = PlayerRepository(session)
            items: list[admin_dto.ContractAdminEntry] = []
            for contract in rows:
                house = await houses.get_by_id(contract.house_id)
                label = (
                    housing.house_label(house)
                    if house is not None
                    else f"#{contract.house_id}"
                )
                owner = await self._display_name(players, contract.owner_player_id)
                tenant = await self._display_name(players, contract.tenant_player_id)
                items.append(admin_dto.ContractAdminEntry(
                    contract_id=contract.id, house_id=contract.house_id,
                    house_label=label, owner_name=owner or "؟",
                    tenant_name=tenant or "؟", monthly_rent=contract.monthly_rent,
                    deposit=contract.deposit, is_active=contract.is_active,
                    next_due_at=_as_utc(contract.next_due_at),
                ))
        return _page(items, total, page, per_page)

    async def terminate_contract(
        self, admin_telegram_id: int, contract_id: int
    ) -> None:
        """Force-end a problematic rental contract (same semantics as a
        normal end: the tenancy stops, no money moves at end-time)."""
        async with self._session_factory() as session:
            contracts = RentalContractRepository(session)
            contract = await contracts.get_by_id(contract_id)
            if contract is None or not contract.is_active:
                raise AdminError(f"contract {contract_id} is not active")
            await contracts.end(contract_id, _utc_now())
            await self._audit(
                session, admin_telegram_id, "contract_terminate",
                target_type="contract", target_id=contract_id,
                details=f"house={contract.house_id} owner={contract.owner_player_id} "
                f"tenant={contract.tenant_player_id}",
            )
            await session.commit()
        logger.info("Admin %s terminated contract %s", admin_telegram_id, contract_id)

    # === Jobs ===================================================================

    async def list_jobs(self) -> list[admin_dto.JobAdminEntry]:
        async with self._session_factory() as session:
            jobs = await JobRepository(session).list_all()
            workers = PlayerJobRepository(session)
            return [
                admin_dto.JobAdminEntry(
                    id=j.id, name=j.name, description=j.description,
                    hourly_salary=j.hourly_salary, employer=j.employer,
                    cooldown=j.cooldown, required_level=j.required_level,
                    is_active=j.is_active,
                    workers_count=await workers.count_by_job(j.id),
                )
                for j in jobs
            ]

    async def get_job(self, job_id: int) -> admin_dto.JobAdminEntry:
        async with self._session_factory() as session:
            job = await JobRepository(session).get_by_id(job_id)
            if job is None:
                raise AdminError(f"job {job_id} not found")
            workers = await PlayerJobRepository(session).count_by_job(job_id)
            return admin_dto.JobAdminEntry(
                id=job.id, name=job.name, description=job.description,
                hourly_salary=job.hourly_salary, employer=job.employer,
                cooldown=job.cooldown, required_level=job.required_level,
                is_active=job.is_active, workers_count=workers,
            )

    async def create_job(
        self,
        admin_telegram_id: int,
        *,
        name: str,
        description: str,
        hourly_salary: int,
        required_level: int,
        employer: str,
        cooldown: int = 300,
    ) -> admin_dto.JobAdminEntry:
        clean_name = " ".join(name.split())[:64]
        if len(clean_name) < 2:
            raise InvalidAmountError("job name is too short")
        if not 1_000 <= hourly_salary <= 10**12:
            raise InvalidAmountError("hourly salary out of range")
        if not 1 <= required_level <= MAX_LEVEL:
            raise InvalidAmountError(f"level must be within 1..{MAX_LEVEL}")
        if not 0 <= cooldown <= 7 * 86400:
            raise InvalidAmountError("cooldown out of range")
        async with self._session_factory() as session:
            jobs = JobRepository(session)
            if await jobs.get_by_name(clean_name) is not None:
                raise AdminError(f"job {clean_name!r} already exists")
            job = await jobs.create_job(
                name=clean_name,
                description=" ".join(description.split())[:256],
                salary=hourly_salary,
                cooldown=cooldown,
                required_level=required_level,
                hourly_salary=hourly_salary,
                employer=" ".join(employer.split())[:64],
            )
            await self._audit(
                session, admin_telegram_id, "job_create",
                target_type="job", target_id=job.id,
                details=f"name={clean_name} hourly={hourly_salary} "
                f"level={required_level}",
            )
            await session.commit()
            job_id = job.id
        return await self.get_job(job_id)

    async def update_job(
        self, admin_telegram_id: int, job_id: int, field: str, value: object
    ) -> admin_dto.JobAdminEntry:
        async with self._session_factory() as session:
            jobs = JobRepository(session)
            job = await jobs.get_by_id(job_id)
            if job is None:
                raise AdminError(f"job {job_id} not found")
            updates = self._clean_job_fields(field, value)
            before = {key: getattr(job, key) for key in updates}
            await jobs.update_fields(job_id, **updates)
            await self._audit(
                session, admin_telegram_id, "job_update",
                target_type="job", target_id=job_id,
                details=", ".join(
                    f"{key}: {before[key]}->{val}" for key, val in updates.items()
                ),
            )
            await session.commit()
        return await self.get_job(job_id)

    @staticmethod
    def _clean_job_fields(field: str, value: object) -> dict[str, object]:
        if field == "description":
            text_value = " ".join(str(value).split())[:256]
            if not text_value:
                raise InvalidAmountError("description must not be empty")
            return {"description": text_value}
        if field == "hourly_salary":
            salary = int(value)  # type: ignore[arg-type]
            if not 1_000 <= salary <= 10**12:
                raise InvalidAmountError("hourly salary out of range")
            # Keep the legacy per-action salary in step with the hourly one.
            return {"hourly_salary": salary, "salary": salary}
        if field == "employer":
            employer = " ".join(str(value).split())[:64]
            if not employer:
                raise InvalidAmountError("employer must not be empty")
            return {"employer": employer}
        if field == "cooldown":
            cooldown = int(value)  # type: ignore[arg-type]
            if not 0 <= cooldown <= 7 * 86400:
                raise InvalidAmountError("cooldown out of range")
            return {"cooldown": cooldown}
        if field == "required_level":
            level = int(value)  # type: ignore[arg-type]
            if not 1 <= level <= MAX_LEVEL:
                raise InvalidAmountError(f"level must be within 1..{MAX_LEVEL}")
            return {"required_level": level}
        raise AdminError(f"field {field} is not editable")

    async def set_job_active(
        self, admin_telegram_id: int, job_id: int, active: bool
    ) -> admin_dto.JobAdminEntry:
        async with self._session_factory() as session:
            jobs = JobRepository(session)
            job = await jobs.get_by_id(job_id)
            if job is None:
                raise AdminError(f"job {job_id} not found")
            await jobs.update_fields(job_id, is_active=active)
            await self._audit(
                session, admin_telegram_id, "job_toggle",
                target_type="job", target_id=job_id,
                details=f"active={active}",
            )
            await session.commit()
        return await self.get_job(job_id)

    async def list_workers(
        self, page: int = 0, per_page: int = 8
    ) -> admin_dto.Page[admin_dto.WorkerEntry]:
        async with self._session_factory() as session:
            workers = PlayerJobRepository(session)
            total = await workers.count()
            total_pages = max(1, (total + per_page - 1) // per_page)
            page = max(0, min(page, total_pages - 1))
            rows = await workers.list_page(page * per_page, per_page)
            players = PlayerRepository(session)
            jobs = JobRepository(session)
            items: list[admin_dto.WorkerEntry] = []
            for row in rows:
                player = await players.get_by_id(row.player_id)
                job = await jobs.get_by_id(row.job_id)
                if player is None or job is None:
                    continue
                items.append(admin_dto.WorkerEntry(
                    player_id=player.id, telegram_user_id=player.telegram_user_id,
                    display_name=player.display_name, job_id=job.id,
                    job_name=job.name, total_earnings=row.total_earnings,
                    started_at=row.started_at,
                ))
        return _page(items, total, page, per_page)

    # === Trading ================================================================

    async def get_trading_overview(self) -> dict[str, object]:
        """Counts + recent sales/activity for the 📈 trading screen."""
        async with self._session_factory() as session:
            listings = HouseListingRepository(session)
            active_sales = await listings.count_active("sale")
            active_rents = await listings.count_active("rent")
            total_sales = await HouseSaleRepository(session).count()
        recent_sales = await self.list_recent_sales(0, per_page=5)
        activity = await self.get_market_activity(limit=8)
        return {
            "active_sales": active_sales,
            "active_rents": active_rents,
            "total_sales": total_sales,
            "recent_sales": recent_sales.items,
            "activity": activity,
        }

    async def list_recent_sales(
        self, page: int = 0, per_page: int = 8
    ) -> admin_dto.Page[admin_dto.SaleAdminEntry]:
        housing = self._require_housing()
        async with self._session_factory() as session:
            sales = HouseSaleRepository(session)
            total = await sales.count()
            total_pages = max(1, (total + per_page - 1) // per_page)
            page = max(0, min(page, total_pages - 1))
            rows = await sales.list_recent(page * per_page, per_page)
            houses = HouseRepository(session)
            players = PlayerRepository(session)
            items: list[admin_dto.SaleAdminEntry] = []
            for sale in rows:
                house = await houses.get_by_id(sale.house_id)
                label = (
                    housing.house_label(house)
                    if house is not None
                    else f"#{sale.house_id}"
                )
                buyer = await self._display_name(players, sale.buyer_player_id)
                seller = await self._display_name(players, sale.seller_player_id)
                items.append(admin_dto.SaleAdminEntry(
                    sale_id=sale.id, house_id=sale.house_id, house_label=label,
                    seller_name=seller, buyer_name=buyer or "؟",
                    price=sale.price, created_at=sale.created_at,
                ))
        return _page(items, total, page, per_page)

    async def get_market_activity(
        self, limit: int = 15
    ) -> list[admin_dto.UserTxEntry]:
        """Newest money movements across all markets (global activity feed)."""
        async with self._session_factory() as session:
            house_tx = await HouseTransactionRepository(session).list_recent(limit)
            land_tx = await LandTransactionRepository(session).list_recent(limit)
            players = PlayerRepository(session)
            entries: list[admin_dto.UserTxEntry] = []
            for tx in house_tx:
                payer = await self._display_name(players, tx.payer_player_id)
                payee = await self._display_name(players, tx.payee_player_id)
                entries.append(admin_dto.UserTxEntry(
                    kind="house_tx",
                    label=f"{tx.note or _house_tx_label(tx.transaction_type, tx.house_id)} "
                    f"({payer or '؟'} ← {payee or 'بازار'})",
                    amount=tx.amount, incoming=True, created_at=tx.created_at,
                ))
            for tx in land_tx:
                payer = await self._display_name(players, tx.payer_player_id)
                entries.append(admin_dto.UserTxEntry(
                    kind="land_tx",
                    label=f"{tx.note or f'خرید زمین #{tx.land_id}'} ({payer or '؟'})",
                    amount=tx.amount, incoming=True, created_at=tx.created_at,
                ))
        entries.sort(key=lambda e: e.created_at, reverse=True)
        return entries[:limit]

    # === Bot settings =============================================================

    async def get_settings_overview(self) -> admin_dto.SettingsOverview:
        # Refresh first so the screen always reflects the stored settings.
        await self.refresh_runtime()
        return admin_dto.SettingsOverview(
            market_conditions=admin_runtime.market_conditions_base(),
            inflation_rate=admin_runtime.inflation_rate(),
            purchase_xp_divisor=admin_runtime.purchase_xp_divisor(),
            purchase_xp_min=admin_runtime.purchase_xp_min(),
            purchase_xp_max=admin_runtime.purchase_xp_max(),
            construction_xp_divisor=admin_runtime.construction_xp_divisor(),
            min_work_minutes=admin_runtime.min_work_minutes(),
            jobs_enabled=admin_runtime.feature_enabled("jobs"),
            housing_enabled=admin_runtime.feature_enabled("housing"),
            realestate_enabled=admin_runtime.feature_enabled("realestate"),
        )

    async def set_reward_setting(
        self, admin_telegram_id: int, key: str, value: int
    ) -> None:
        """Change one XP-reward tunable (``pxd``/``pxn``/``pxx``/``cxd``)."""
        mapping = {
            "pxd": (admin_runtime.KEY_PURCHASE_XP_DIVISOR, XP_DIVISOR_MIN, XP_DIVISOR_MAX),
            "pxn": (admin_runtime.KEY_PURCHASE_XP_MIN, XP_BAND_MIN, XP_BAND_MAX),
            "pxx": (admin_runtime.KEY_PURCHASE_XP_MAX, XP_BAND_MIN, XP_BAND_MAX),
            "cxd": (admin_runtime.KEY_CONSTRUCTION_XP_DIVISOR, XP_DIVISOR_MIN, XP_DIVISOR_MAX),
        }
        if key not in mapping:
            raise AdminError(f"unknown reward setting: {key}")
        setting_key, low, high = mapping[key]
        if not low <= value <= high:
            raise InvalidAmountError(f"value must be within {low}..{high}")
        if key == "pxn" and value > admin_runtime.purchase_xp_max():
            raise InvalidAmountError("min cannot exceed the current max")
        if key == "pxx" and value < admin_runtime.purchase_xp_min():
            raise InvalidAmountError("max cannot go below the current min")
        async with self._session_factory() as session:
            await BotSettingRepository(session).set(setting_key, str(value))
            await self._audit(
                session, admin_telegram_id, "settings_reward",
                details=f"{setting_key}={value}",
            )
            await session.commit()
        admin_runtime.set_override(setting_key, value)

    async def set_min_work_minutes(
        self, admin_telegram_id: int, minutes: int
    ) -> None:
        if not 0 <= minutes <= MIN_WORK_MINUTES_MAX:
            raise InvalidAmountError(
                f"minutes must be within 0..{MIN_WORK_MINUTES_MAX}"
            )
        async with self._session_factory() as session:
            await BotSettingRepository(session).set(
                admin_runtime.KEY_MIN_WORK_MINUTES, str(minutes)
            )
            await self._audit(
                session, admin_telegram_id, "settings_cooldown",
                details=f"min_work_minutes={minutes}",
            )
            await session.commit()
        admin_runtime.set_override(admin_runtime.KEY_MIN_WORK_MINUTES, minutes)

    async def set_feature(
        self, admin_telegram_id: int, feature: str, enabled: bool
    ) -> None:
        if feature not in admin_runtime.FEATURES:
            raise AdminError(f"unknown feature: {feature}")
        key = f"{feature}_enabled"
        async with self._session_factory() as session:
            await BotSettingRepository(session).set(key, "1" if enabled else "0")
            await self._audit(
                session, admin_telegram_id, "feature_toggle",
                details=f"{key}={enabled}",
            )
            await session.commit()
        admin_runtime.set_override(key, enabled)

    # === Database tools =============================================================

    def _sqlite_file_path(self) -> Path | None:
        """Live DB file path, or ``None`` when backup/restore is unsupported."""
        if self._database is None:
            return None
        url = self._database.engine.url
        if url.get_backend_name() != "sqlite":
            return None
        name = url.database
        if not name or name == ":memory:":
            return None
        return Path(name)

    def _sqlite_file_size(self) -> int | None:
        path = self._sqlite_file_path()
        if path is None or not path.exists():
            return None
        return path.stat().st_size

    async def get_db_stats(self) -> admin_dto.DBStats:
        async with self._session_factory() as session:
            bind = session.bind
            dialect = bind.dialect.name if bind is not None else "?"
            ping_ms = await self._ping_ms(session)
            counts: list[tuple[str, int]] = []
            for table in Base.metadata.sorted_tables:
                result = await session.execute(
                    text(f'SELECT COUNT(*) FROM "{table.name}"')
                )
                counts.append((table.name, int(result.scalar_one())))
        total_rows = sum(count for _, count in counts)
        return admin_dto.DBStats(
            dialect=str(dialect),
            file_size_bytes=self._sqlite_file_size(),
            tables=len(counts),
            total_rows=total_rows,
            counts=tuple(counts),
        )

    def _backup_dir(self) -> Path:
        directory = PROJECT_ROOT / "data" / "backups"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    async def backup_database(self, admin_telegram_id: int) -> admin_dto.BackupInfo:
        """Snapshot the live SQLite file (safe on a running bot)."""
        live = self._sqlite_file_path()
        if live is None:
            raise AdminError("backup is only supported for file-based SQLite")
        stamp = _utc_now().strftime("%Y%m%d_%H%M%S")
        target = self._backup_dir() / f"{BACKUP_PREFIX}{stamp}.db"
        suffix = 1
        while target.exists():
            suffix += 1
            target = self._backup_dir() / f"{BACKUP_PREFIX}{stamp}_{suffix}.db"
        await asyncio.to_thread(_sqlite_backup_file, live, target)
        info = self._backup_info(target)
        await self._audit_detached(
            admin_telegram_id, "db_backup",
            details=f"file={info.filename} bytes={info.size_bytes}",
        )
        logger.info("Admin %s backed up the database to %s", admin_telegram_id, target)
        return info

    def backup_file_path(self, filename: str) -> Path:
        """Resolve a listed backup filename to its path (traversal-safe)."""
        if not _BACKUP_NAME_RE.match(filename):
            raise AdminError("unknown backup file")
        path = self._backup_dir() / filename
        if not path.exists() or not path.is_file():
            raise AdminError("backup file not found")
        return path

    async def list_backups(self) -> list[admin_dto.BackupInfo]:
        directory = self._backup_dir()
        infos = [
            self._backup_info(path)
            for path in directory.glob(f"{BACKUP_PREFIX}*.db")
            if _BACKUP_NAME_RE.match(path.name)
        ]
        infos.sort(key=lambda i: i.created_at, reverse=True)
        return infos

    @staticmethod
    def _backup_info(path: Path) -> admin_dto.BackupInfo:
        stat = path.stat()
        return admin_dto.BackupInfo(
            filename=path.name,
            size_bytes=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        )

    async def restore_database(self, admin_telegram_id: int, filename: str) -> str:
        """Replace the live DB file with a backup (bot keeps running)."""
        live = self._sqlite_file_path()
        if live is None or self._database is None:
            raise AdminError("restore is only supported for file-based SQLite")
        source = self.backup_file_path(filename)
        # Close every pooled connection, swap the file, then reconnect lazily.
        await self._database.dispose()
        await asyncio.to_thread(shutil.copyfile, source, live)
        await self.refresh_runtime()
        await self._audit_detached(
            admin_telegram_id, "db_restore", details=f"file={filename}",
        )
        logger.warning("Admin %s restored the database from %s", admin_telegram_id, filename)
        return filename

    async def purge_closed_listings(
        self, admin_telegram_id: int, older_than_days: int
    ) -> int:
        if not 1 <= older_than_days <= 3650:
            raise InvalidAmountError("days must be within 1..3650")
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            days=older_than_days
        )
        async with self._session_factory() as session:
            removed = await HouseListingRepository(session).purge_closed_older_than(
                cutoff
            )
            await self._audit(
                session, admin_telegram_id, "db_purge",
                details=f"closed_listings older_than_days={older_than_days} "
                f"removed={removed}",
            )
            await session.commit()
        return removed

    async def purge_audit_logs(
        self, admin_telegram_id: int, keep_days: int
    ) -> int:
        if not 1 <= keep_days <= 3650:
            raise InvalidAmountError("days must be within 1..3650")
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            days=keep_days
        )
        async with self._session_factory() as session:
            removed = await AdminAuditLogRepository(session).prune_older_than(cutoff)
            # The audit row for the purge itself is brand new, so it survives.
            await self._audit(
                session, admin_telegram_id, "db_purge",
                details=f"audit_logs keep_days={keep_days} removed={removed}",
            )
            await session.commit()
        return removed

    async def purge_price_ticks(
        self, admin_telegram_id: int, keep_days: int
    ) -> int:
        if not 1 <= keep_days <= 3650:
            raise InvalidAmountError("days must be within 1..3650")
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            days=keep_days
        )
        async with self._session_factory() as session:
            removed = await MarketPriceTickRepository(session).prune_older_than(cutoff)
            await self._audit(
                session, admin_telegram_id, "db_purge",
                details=f"price_ticks keep_days={keep_days} removed={removed}",
            )
            await session.commit()
        return removed

    # === Logs ===================================================================

    async def list_audit_logs(
        self, page: int = 0, per_page: int = 8, action_prefix: str | None = None
    ) -> admin_dto.Page[admin_dto.AdminAuditEntry]:
        async with self._session_factory() as session:
            logs = AdminAuditLogRepository(session)
            total = await logs.count(action_prefix=action_prefix)
            total_pages = max(1, (total + per_page - 1) // per_page)
            page = max(0, min(page, total_pages - 1))
            rows = await logs.list_page(
                page * per_page, per_page, action_prefix=action_prefix
            )
            items = [
                admin_dto.AdminAuditEntry(
                    id=row.id, admin_telegram_id=row.admin_telegram_id,
                    action=row.action, target_type=row.target_type,
                    target_id=row.target_id, details=row.details,
                    created_at=row.created_at,
                )
                for row in rows
            ]
        return _page(items, total, page, per_page)

    async def get_error_logs(self, limit: int = 10) -> list[str]:
        """Last ERROR lines of the bot log file (already secret-redacted)."""
        lines = await asyncio.to_thread(_tail_lines, LOG_FILE, 65_536)
        errors = [line for line in lines if "ERROR" in line]
        return [line[:300] for line in errors[-limit:]]

    # === Helpers ================================================================

    @staticmethod
    async def _display_name(
        players: PlayerRepository, player_id: int | None
    ) -> str | None:
        if player_id is None:
            return None
        player = await players.get_by_id(player_id)
        return player.display_name if player is not None else None

    @staticmethod
    async def _audit(
        session: AsyncSession,
        admin_telegram_id: int,
        action: str,
        *,
        target_type: str | None = None,
        target_id: int | None = None,
        details: str = "",
    ) -> None:
        await AdminAuditLogRepository(session).add(
            admin_telegram_id=admin_telegram_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details,
        )

    async def _audit_detached(
        self,
        admin_telegram_id: int,
        action: str,
        *,
        target_type: str | None = None,
        target_id: int | None = None,
        details: str = "",
    ) -> None:
        """Audit a change that committed in another session (XP/backup/...)."""
        async with self._session_factory() as session:
            await self._audit(
                session, admin_telegram_id, action,
                target_type=target_type, target_id=target_id, details=details,
            )
            await session.commit()

    @staticmethod
    def _require_money_amount(amount: int) -> None:
        if amount <= 0 or amount > MAX_MONEY_AMOUNT:
            raise InvalidAmountError(
                f"amount must be within 1..{MAX_MONEY_AMOUNT}"
            )

    @staticmethod
    def _require_xp_amount(amount: int) -> None:
        if amount <= 0 or amount > MAX_XP_AMOUNT:
            raise InvalidAmountError(f"amount must be within 1..{MAX_XP_AMOUNT}")

    def _require_levels(self) -> LevelService:
        if self._levels is None:  # pragma: no cover — always wired in practice
            raise AdminError("level service is unavailable")
        return self._levels

    def _require_housing(self) -> HousingService:
        if self._housing is None:  # pragma: no cover — always wired in practice
            raise AdminError("housing service is unavailable")
        return self._housing

    def _require_realestate(self) -> RealEstateService:
        if self._realestate is None:  # pragma: no cover — always wired
            raise AdminError("real-estate service is unavailable")
        return self._realestate


def _house_tx_label(transaction_type: str, house_id: int | None) -> str:
    labels = {
        "market_purchase": f"خرید خانه #{house_id} از بازار",
        "player_purchase": f"خرید خانه #{house_id}",
        "rent_deposit": f"رهن خانه #{house_id}",
        "rent_payment": f"اجاره خانه #{house_id}",
    }
    return labels.get(transaction_type, f"تراکنش خانه #{house_id}")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _sqlite_backup_file(source: Path, target: Path) -> None:
    """Copy a (possibly live) SQLite file via the online backup API."""
    src = sqlite3.connect(str(source))
    try:
        dst = sqlite3.connect(str(target))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _tail_lines(path: Path, max_bytes: int) -> list[str]:
    """Last lines of a text file (reads at most ``max_bytes`` from the end)."""
    try:
        with open(path, "rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            chunk = handle.read().decode("utf-8", errors="replace")
    except FileNotFoundError:
        return []
    return [line for line in chunk.splitlines() if line.strip()]
