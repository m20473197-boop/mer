"""Domain errors for the fictional خلاف system."""

from __future__ import annotations

from app.game.shared.errors import DomainError


class CrimeError(DomainError):
    """Base class for crime-specific business errors."""


class CrimeInvalidTargetError(CrimeError):
    """The target does not exist or is the actor themselves."""


class CrimeTargetBankAccountError(CrimeError):
    """The hacking target has no usable in-game bank account."""


class CrimeCooldownError(CrimeError):
    """The actor must wait before trying this activity again."""

    def __init__(self, remaining_seconds: int) -> None:
        self.remaining_seconds = max(0, int(remaining_seconds))
        super().__init__(f"crime activity cooldown: {self.remaining_seconds}s")


class CrimeInvalidAmountError(CrimeError):
    """An amount is outside the configured exact-integer range."""


class CrimeInsufficientFundsError(CrimeError):
    """The actor cannot pay an activity's wallet amount."""


class CrimeOperationNotFoundError(CrimeError):
    """A requested crime operation does not belong to the player."""


class CrimeDuplicateDocumentError(CrimeError):
    """The player already owns an active document of that type."""


class CrimeInvalidDocumentTypeError(CrimeError):
    """The document type is not in the configured catalog."""


class CrimeNoEligibleVehicleError(CrimeError):
    """The player owns no required شوتی vehicle."""


class CrimeVehicleNotOwnedError(CrimeError):
    """The selected vehicle is not owned or is not شوتی-compatible."""


class CrimeActiveMissionError(CrimeError):
    """The player already has an active شوتی mission."""


class CrimeOperationConflictError(CrimeError):
    """An operation key was reused for a different operation."""
