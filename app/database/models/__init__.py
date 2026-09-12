"""ORM models package. Importing it registers every model on ``Base.metadata``."""

from app.database.models.admin_audit_log import AdminAuditLog
from app.database.models.base import Base
from app.database.models.bot_setting import BotSetting
from app.database.models.business import Business
from app.database.models.child import Child
from app.database.models.construction_project import ConstructionProject
from app.database.models.divorce_record import DivorceRecord
from app.database.models.economic_event import EconomicEvent
from app.database.models.family_history import FamilyHistory
from app.database.models.house import House
from app.database.models.iran_market_asset import IranMarketAsset
from app.database.models.iran_market_price_history import IranMarketPriceHistory
from app.database.models.iran_market_holding import IranMarketHolding
from app.database.models.iran_market_update_state import IranMarketUpdateState
from app.database.models.house_listing import HouseListing
from app.database.models.house_sale import HouseSale
from app.database.models.house_transaction import HouseTransaction
from app.database.models.job import Job
from app.database.models.job_event import JobEvent
from app.database.models.job_history import JobHistory
from app.database.models.land import Land
from app.database.models.land_transaction import LandTransaction
from app.database.models.marriage import Marriage
from app.database.models.marriage_request import MarriageRequest
from app.database.models.relationship_event import RelationshipEvent
from app.database.models.level_up_history import LevelUpHistory
from app.database.models.market_asset import MarketAsset
from app.database.models.market_price_tick import MarketPriceTick
from app.database.models.marketplace_listing import MarketplaceListing
from app.database.models.player import Player
from app.database.models.vehicle_model import VehicleModel
from app.database.models.vehicle_ownership import VehicleOwnership
from app.database.models.player_job import PlayerJob
from app.database.models.property_upgrade import PropertyUpgrade
from app.database.models.renovation_project import RenovationProject
from app.database.models.rental_contract import RentalContract
from app.database.models.xp_transaction import XPTransaction

__all__ = [
    "Base",
    "AdminAuditLog",
    "BotSetting",
    "Business",
    "EconomicEvent",
    "MarketAsset",
    "MarketPriceTick",
    "MarketplaceListing",
    "VehicleModel",
    "VehicleOwnership",
    "Player",
    "XPTransaction",
    "LevelUpHistory",
    "Job",
    "PlayerJob",
    "JobHistory",
    "JobEvent",
    "House",
    "IranMarketAsset",
    "IranMarketPriceHistory",
    "IranMarketHolding",
    "IranMarketUpdateState",
    "HouseListing",
    "HouseSale",
    "RentalContract",
    "HouseTransaction",
    "Land",
    "LandTransaction",
    "ConstructionProject",
    "RenovationProject",
    "PropertyUpgrade",
    "Marriage",
    "MarriageRequest",
    "DivorceRecord",
    "Child",
    "RelationshipEvent",
    "FamilyHistory",
]
