"""Construction year (سال ساخت) — the Solar-Hijri calendar domain.

Houses store the year they were built in the Iranian (Solar Hijri) calendar —
e.g. ``1395`` — instead of an age. Anywhere the system needs the building's
age (depreciation, modernize eligibility) it is **derived internally**:

    building_age = current_iranian_year() − construction_year   (floored at 0)

and the player-facing UI only ever shows the construction year.

The Iranian year starts at Nowruz (the vernal equinox, around March 20–21).
A fixed cutoff of March 21 is used here — precise to within a day or two,
which is far beyond what a life-simulation game needs. Tests can inject a
reference ``now`` for determinism.
"""

from __future__ import annotations

from datetime import datetime, timezone

# Gregorian → Solar Hijri offset (after Nowruz of that Gregorian year).
GREGORIAN_TO_HIJRI_OFFSET: int = 621

# Nowruz approximation: the year flips on March 21.
NOWRUZ_MONTH: int = 3
NOWRUZ_DAY: int = 21

# The oldest plausible construction year accepted in the game
# (~95 years before 1405) — also the migration threshold that tells stale
# stored ages apart from real construction years.
MIN_CONSTRUCTION_YEAR: int = 1330


def current_iranian_year(now: datetime | None = None) -> int:
    """The ongoing Iranian (Solar Hijri) year for ``now`` (UTC by default)."""
    moment = now if now is not None else datetime.now(timezone.utc)
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    hijri_year = moment.year - GREGORIAN_TO_HIJRI_OFFSET
    if (moment.month, moment.day) < (NOWRUZ_MONTH, NOWRUZ_DAY):
        hijri_year -= 1
    return hijri_year


def age_from_construction_year(
    construction_year: int, now: datetime | None = None
) -> int:
    """Building age in whole years, derived internally (never negative)."""
    return max(0, current_iranian_year(now) - construction_year)


def validate_construction_year(
    construction_year: int, now: datetime | None = None
) -> None:
    """Reject implausible construction years.

    Raises:
        ValueError: If the year is below ``MIN_CONSTRUCTION_YEAR`` or in the
            future.
    """
    current = current_iranian_year(now)
    if construction_year < MIN_CONSTRUCTION_YEAR:
        raise ValueError(
            f"construction_year must be >= {MIN_CONSTRUCTION_YEAR}, "
            f"got {construction_year}"
        )
    if construction_year > current:
        raise ValueError(
            f"construction_year cannot be in the future "
            f"(> {current}), got {construction_year}"
        )
