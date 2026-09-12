"""Configurable catalog and balancing values for the fictional خلاف system."""

from __future__ import annotations

from dataclasses import dataclass, field

CRIME_ACTIVITY_INFORMATION_SELLING: str = "information_selling"
CRIME_ACTIVITY_MONEY_LAUNDERING: str = "money_laundering"
CRIME_ACTIVITY_FAKE_DOCUMENT: str = "fake_document"
CRIME_ACTIVITY_SHOTI: str = "shoti"
CRIME_ACTIVITY_BANK_HACK: str = "bank_hack"

CRIME_STATUS_PENDING: str = "pending"
CRIME_STATUS_PROCESSING: str = "processing"
CRIME_STATUS_COMPLETED: str = "completed"
CRIME_STATUS_FAILED: str = "failed"
CRIME_STATUS_CANCELLED: str = "cancelled"


@dataclass(frozen=True, slots=True)
class FakeDocumentDefinition:
    """One document type that can be issued as a fictional game item."""

    code: str
    name: str
    validity_seconds: int | None


@dataclass(frozen=True, slots=True)
class ShotiMissionTemplate:
    """Configurable route/shipment values used to generate a mission."""

    origin: str
    destination: str
    shipment: str
    reward: int
    difficulty: int
    risk: int
    duration_seconds: int


@dataclass(frozen=True, slots=True)
class CrimeConfig:
    """All balancing knobs used by ``CrimeService``.

    Probabilities are integer percentages and all money values are exact
    Toman integers. A deployment or test can inject a new ``CrimeConfig``
    without changing handlers or persistence code.
    """

    information_success_percent: int = 70
    information_reward: int = 75_000
    information_cooldown_seconds: int = 5 * 60

    laundering_fee_percent: int = 10
    laundering_processing_seconds: int = 5 * 60
    laundering_cooldown_seconds: int = 0
    laundering_min_amount: int = 1_000
    laundering_max_amount: int = 100_000_000

    fake_documents: tuple[FakeDocumentDefinition, ...] = (
        FakeDocumentDefinition("identity", "🪪 مدرک هویتی جعلی", 7 * 86400),
        FakeDocumentDefinition("deed", "📄 سند جعلی", 7 * 86400),
        FakeDocumentDefinition("business", "🏢 مدرک کسب‌وکار جعلی", 7 * 86400),
    )

    shoti_success_base_percent: int = 55
    shoti_cooldown_seconds: int = 0
    shoti_vehicle_modifiers: dict[str, int] = field(
        default_factory=lambda: {
            "peugeot_405": 15,
            "peugeot_pars": 12,
            "zantia": 8,
            "samand": 10,
        }
    )
    shoti_templates: tuple[ShotiMissionTemplate, ...] = (
        ShotiMissionTemplate("تهران", "قم", "قطعات یدکی", 300_000, 30, 20, 3 * 60),
        ShotiMissionTemplate("کرج", "قزوین", "لوازم الکترونیکی", 420_000, 45, 30, 5 * 60),
        ShotiMissionTemplate("اصفهان", "شیراز", "کالای مصرفی", 650_000, 60, 40, 8 * 60),
        ShotiMissionTemplate("تبریز", "رشت", "بار ویژه", 900_000, 75, 50, 12 * 60),
    )

    bank_hack_success_percent: int = 35
    bank_hack_amount: int = 100_000
    bank_hack_cooldown_seconds: int = 60 * 60

    scheduler_interval_seconds: int = 30


DEFAULT_CRIME_CONFIG = CrimeConfig()


def get_fake_document_definition(
    definitions: tuple[FakeDocumentDefinition, ...], code: str
) -> FakeDocumentDefinition | None:
    return next((definition for definition in definitions if definition.code == code), None)
