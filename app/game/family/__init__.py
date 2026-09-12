"""Family domain package: pure rules + DTOs (no I/O).

Mirrors ``app/game/housing`` — the Telegram and service layers import from
here and never touch ORM objects.
"""

from app.game.family import domain, dto  # noqa: F401  (re-export for convenience)

__all__ = ["domain", "dto"]
