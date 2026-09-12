"""Pure catalog types and DTOs for the fictional 🕳️ خلاف system."""

from app.game.crime.catalog import (
    CRIME_ACTIVITY_BANK_HACK,
    CRIME_ACTIVITY_FAKE_DOCUMENT,
    CRIME_ACTIVITY_INFORMATION_SELLING,
    CRIME_ACTIVITY_MONEY_LAUNDERING,
    CRIME_ACTIVITY_SHOTI,
    CrimeConfig,
    FakeDocumentDefinition,
    ShotiMissionTemplate,
)
from app.game.crime.dto import (
    BankHackResult,
    CrimeActivityData,
    FakeDocumentData,
    InformationSellingResult,
    MoneyLaunderingData,
    ShotiMissionData,
)

__all__ = [
    "CRIME_ACTIVITY_BANK_HACK",
    "CRIME_ACTIVITY_FAKE_DOCUMENT",
    "CRIME_ACTIVITY_INFORMATION_SELLING",
    "CRIME_ACTIVITY_MONEY_LAUNDERING",
    "CRIME_ACTIVITY_SHOTI",
    "CrimeConfig",
    "FakeDocumentDefinition",
    "ShotiMissionTemplate",
    "CrimeActivityData",
    "InformationSellingResult",
    "MoneyLaunderingData",
    "FakeDocumentData",
    "ShotiMissionData",
    "BankHackResult",
]
