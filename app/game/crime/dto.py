"""Immutable DTOs returned by the خلاف service."""

from __future__ import annotations

from datetime import datetime

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CrimeActivityData:
    activity_id: int
    activity_type: str
    actor_player_id: int
    target_player_id: int | None
    status: str
    success: bool | None
    reward_amount: int
    fee_amount: int
    operation_key: str
    details: str
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class InformationSellingResult:
    activity: CrimeActivityData
    target_player_id: int
    target_name: str
    success: bool
    reward_amount: int
    information: str


@dataclass(frozen=True, slots=True)
class MoneyLaunderingData:
    activity: CrimeActivityData
    operation_id: int
    player_id: int
    amount: int
    fee_amount: int
    final_amount: int
    status: str
    process_at: datetime
    completed_at: datetime | None
    wallet_balance_after: int | None


@dataclass(frozen=True, slots=True)
class FakeDocumentData:
    document_id: int
    owner_player_id: int
    document_type: str
    document_name: str
    status: str
    created_at: datetime
    expires_at: datetime | None
    activity: CrimeActivityData | None = None


@dataclass(frozen=True, slots=True)
class ShotiMissionData:
    mission_id: int
    activity: CrimeActivityData
    player_id: int
    vehicle_ownership_id: int
    vehicle_model_id: int
    vehicle_name: str
    origin: str
    destination: str
    shipment: str
    reward: int
    difficulty: int
    risk: int
    duration_seconds: int
    started_at: datetime
    completes_at: datetime
    status: str
    success: bool | None
    reward_paid: bool
    completed_at: datetime | None
    wallet_balance_after: int | None


@dataclass(frozen=True, slots=True)
class BankHackResult:
    activity: CrimeActivityData
    attempt_id: int
    attacker_player_id: int
    target_player_id: int
    target_name: str
    success: bool
    configured_amount: int
    transferred_amount: int
    reason: str
