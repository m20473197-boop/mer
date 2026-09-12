"""DTOs for the Marriage and Family system (service → Telegram layer).

Same rule as every other domain here: handlers receive frozen dataclasses and
never see an ORM object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class MarriageData:
    """The live state of one marriage."""

    marriage_id: int
    husband_player_id: int
    wife_player_id: int
    started_at: datetime
    relationship_quality: int
    quality_label: str
    mahriyeh_amount: int
    mahriyeh_paid: bool
    cheating_strikes: int
    social_penalties: int
    children_count: int
    pregnant: bool = False
    pregnancy_due_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class FamilyInfoData:
    """Everything the profile / «خانواده» output needs."""

    married: bool
    spouse_player_id: int | None = None
    spouse_name: str | None = None
    spouse_telegram_user_id: int | None = None
    marriage_date: datetime | None = None
    marriage_years: int = 0
    children_count: int = 0
    relationship_quality: int = 0
    quality_label: str = ""
    mahriyeh_amount: int = 0
    mahriyeh_paid: bool = True
    cheating_strikes: int = 0
    pregnant: bool = False
    marriage_id: int | None = None


@dataclass(frozen=True, slots=True)
class MarriageRequestData:
    """A pending proposal, as shown to the target and to the proposer."""

    request_id: int
    proposer_player_id: int
    proposer_name: str
    target_player_id: int
    mahriyeh_amount: int
    created_at: datetime
    expires_at: datetime
    message: str = ""


@dataclass(frozen=True, slots=True)
class MarriageResult:
    """Outcome of an accepted proposal."""

    marriage_id: int
    husband_player_id: int
    wife_player_id: int
    husband_name: str
    wife_name: str
    mahriyeh_amount: int
    started_at: datetime
    relationship_quality: int
    xp_granted_husband: int = 0
    xp_granted_wife: int = 0


@dataclass(frozen=True, slots=True)
class DivorceResult:
    """Outcome of «طلاق» (or of a system-forced divorce)."""

    marriage_id: int
    initiator_player_id: int
    mahriyeh_amount: int
    mahriyeh_paid: bool
    mahriyeh_waived: bool
    payer_player_id: int | None
    payee_player_id: int | None
    balance_after: int
    children_count: int
    reason: str
    forced: bool = False


@dataclass(frozen=True, slots=True)
class CheatingResult:
    """Outcome of «خیانت» — the attempt, and whether it was found out."""

    success: bool
    discovered: bool
    quality_before: int
    quality_after: int
    social_penalty: int
    strikes: int
    fine_amount: int
    fine_paid: bool
    forced_divorce: bool
    spouse_notified: bool
    spouse_player_id: int | None = None
    balance_after: int = 0


@dataclass(frozen=True, slots=True)
class RelationshipResult:
    """Outcome of «رابطه» — the quality move and the conception roll."""

    quality_before: int
    quality_after: int
    success: bool
    pregnancy: bool
    pregnancy_chance: float
    pregnancy_due_at: datetime | None = None
    xp_granted: int = 0
    blocked_max_children: bool = False


@dataclass(frozen=True, slots=True)
class ChildData:
    """One child of a family."""

    child_id: int
    marriage_id: int
    father_player_id: int
    mother_player_id: int
    name: str
    birth_date: datetime
    birth_year: int
    age_years: int
    growth_stage: str


@dataclass(frozen=True, slots=True)
class FamilyHistoryEntryData:
    """One row of the family timeline."""

    id: int
    event_type: str
    marriage_id: int | None
    other_player_id: int | None
    amount: int
    quality_delta: int
    social_penalty: int
    note: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class FamilySettlement:
    """What one lazy settle pass changed (used by services and tests)."""

    children_born: int = 0
    requests_expired: int = 0
    births: list[ChildData] = field(default_factory=list)


__all__ = [
    "CheatingResult",
    "ChildData",
    "DivorceResult",
    "FamilyHistoryEntryData",
    "FamilyInfoData",
    "FamilySettlement",
    "MarriageData",
    "MarriageRequestData",
    "MarriageResult",
    "RelationshipResult",
]
