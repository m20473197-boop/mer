"""Pure level/XP progression math.

Kept free of any I/O so it can be unit-tested in isolation and safely reused
by future systems (jobs, education, businesses, ...) without touching the
database or Telegram layers. The curve is driven by the tunable constants in
``app.core.constants`` — changing those reshapes the whole progression.

Example progression (with default constants BASE=100, GROWTH=1.35):
    Level 1: 0 XP total
    Level 2: 100 XP total (100 required from L1)
    Level 3: 235 XP total (135 required from L2)
    Level 4: 417 XP total (182 required from L3)
    ...
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core import constants


def xp_for_level_up(level: int) -> int:
    """XP required to advance *from* ``level`` to ``level + 1``."""
    if level < 1:
        raise ValueError("level must be >= 1")
    return int(round(constants.XP_BASE_PER_LEVEL * constants.XP_GROWTH_PER_LEVEL ** (level - 1)))


def total_xp_for_level(level: int) -> int:
    """Total XP a player must have collected to *reach* ``level``."""
    if level < 1:
        raise ValueError("level must be >= 1")
    return sum(xp_for_level_up(lvl) for lvl in range(1, level))


def level_from_total_xp(total_xp: int) -> int:
    """Resolve the level a player is on, given their total collected XP."""
    if total_xp < 0:
        raise ValueError("total_xp must be >= 0")
    level = 1
    remaining = total_xp
    while remaining >= xp_for_level_up(level):
        remaining -= xp_for_level_up(level)
        level += 1
    return level


def xp_in_current_level(total_xp: int) -> int:
    """XP accumulated inside the current level (0 <= result < needed)."""
    if total_xp < 0:
        raise ValueError("total_xp must be >= 0")
    lvl = level_from_total_xp(total_xp)
    return total_xp - total_xp_for_level(lvl)


def xp_needed_for_next_level(level: int) -> int:
    """XP needed to go from ``level`` to ``level+1`` (alias for xp_for_level_up)."""
    return xp_for_level_up(level)


def total_xp_for_next_level(level: int) -> int:
    """Total XP required to reach ``level+1``."""
    return total_xp_for_level(level + 1)


def progress_percent(total_xp: int) -> float:
    """Progress inside current level as 0.0–100.0."""
    if total_xp < 0:
        raise ValueError("total_xp must be >= 0")
    lvl = level_from_total_xp(total_xp)
    into = xp_in_current_level(total_xp)
    needed = xp_for_level_up(lvl)
    if needed <= 0:
        return 100.0
    return (into / needed) * 100.0


@dataclass(frozen=True, slots=True)
class LevelProgress:
    """Complete snapshot of a player's progression state."""

    level: int
    total_xp: int
    xp_in_current_level: int
    xp_needed_for_next: int
    total_xp_for_current_level: int
    total_xp_for_next_level: int
    progress_percent: float


def get_level_progress(total_xp: int) -> LevelProgress:
    """Build a full progress snapshot for ``total_xp``."""
    if total_xp < 0:
        raise ValueError("total_xp must be >= 0")
    lvl = level_from_total_xp(total_xp)
    return LevelProgress(
        level=lvl,
        total_xp=total_xp,
        xp_in_current_level=xp_in_current_level(total_xp),
        xp_needed_for_next=xp_needed_for_next_level(lvl),
        total_xp_for_current_level=total_xp_for_level(lvl),
        total_xp_for_next_level=total_xp_for_next_level(lvl),
        progress_percent=progress_percent(total_xp),
    )
