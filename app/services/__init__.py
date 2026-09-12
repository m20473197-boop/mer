"""Application services and the registry used by the Telegram layer.

Dependency flow (strict):

    Telegram handler -> Service -> Repository -> Database

Services own transactions and business rules; handlers only translate
between Telegram objects and service calls.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.repositories.bank_account_repository import BankAccountRepository
from app.services.admin_service import AdminService
from app.services.bank_service import BankService
from app.services.business_service import BusinessService
from app.services.divar_service import DivarService
from app.services.family_service import FamilyService
from app.services.housing_service import HousingService
from app.services.iran_market_service import IranMarketService
from app.services.job_service import JobService
from app.services.level_service import LevelService
from app.services.money_service import MoneyService
from app.services.player_service import PlayerService
from app.services.realestate_service import RealEstateService
from app.services.vehicle_service import VehicleService

CarService = VehicleService

__all__ = [
    "ServiceRegistry",
    "AdminService",
    "BankService",
    "BusinessService",
    "DivarService",
    "PlayerService",
    "LevelService",
    "MoneyService",
    "JobService",
    "HousingService",
    "IranMarketService",
    "RealEstateService",
    "VehicleService",
    "CarService",
    "FamilyService",
]


class ServiceRegistry:
    """Bundles every service; created once at startup and shared via bot_data."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        market_provider=None,
    ) -> None:
        self.levels = LevelService(session_factory)
        self.money = MoneyService(session_factory)
        self.bank = BankService(session_factory, money_service=self.money)
        self.iran_bank = self.bank
        self.players = PlayerService(
            session_factory, bank_account_repository=BankAccountRepository
        )
        self.jobs = JobService(session_factory, money_service=self.money)
        self.businesses = BusinessService(session_factory, money_service=self.money)
        self.market = IranMarketService(
            session_factory, provider=market_provider, money_service=self.money
        )
        # Explicit alias for code that uses the full feature name.
        self.iran_market = self.market
        # Singular alias keeps the dependency easy to discover for callers
        # that refer to the feature as ``services.business``.
        self.business = self.businesses
        self.housing = HousingService(session_factory, level_service=self.levels)
        self.divar = DivarService(
            session_factory, money_service=self.money, housing_service=self.housing
        )
        self.marketplace = self.divar
        self.vehicles = VehicleService(
            session_factory, money_service=self.money
        )
        # Car/vehicle aliases keep the service discoverable without creating
        # another implementation or wallet boundary.
        self.cars = self.vehicles
        self.vehicle = self.vehicles
        self.car_dealership = self.vehicles
        self.realestate = RealEstateService(
            session_factory, level_service=self.levels, housing_service=self.housing
        )
        # Family reuses the same wallet + level services so Mahriyeh and XP
        # go through the existing atomic primitives (no parallel money path).
        self.family = FamilyService(
            session_factory,
            level_service=self.levels,
            money_service=self.money,
        )
        self.admin = AdminService(
            session_factory,
            level_service=self.levels,
            housing_service=self.housing,
            realestate_service=self.realestate,
        )

    def attach_database(self, database) -> None:
        """Hand engine access to services that need it (admin backup/restore)."""
        self.admin.attach_database(database)
