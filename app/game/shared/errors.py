"""Domain-level exceptions shared by every game service.

Services raise these; Telegram handlers translate them into friendly Persian
messages. They never leak implementation details to players.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all game domain errors."""


class PlayerNotFoundError(DomainError):
    """Raised when an operation targets a player that does not exist."""


class InsufficientFundsError(DomainError):
    """Raised when a player tries to spend money they do not have."""


class InvalidAmountError(DomainError):
    """Raised when an amount (money, XP, ...) is not a valid positive value."""
