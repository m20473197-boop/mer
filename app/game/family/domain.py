"""Marriage and Family domain rules (pure math — no I/O, no ORM, no Telegram).

Everything the family system *decides* lives here, mirroring how the housing
system isolates its pricing engine in ``app/game/housing/pricing.py``:

* Mahriyeh is **computed, never fixed** — from the payer's level, their live
  wallet and the shared economy knob, so a richer / higher-level player pays
  more and an economic shift moves the whole marriage market with it.
* Relationship quality is a bounded 0…100 accumulator.
* Pregnancy chance scales with quality, never a flat roll.
* Cheating consequences escalate per discovery.

Every function is deterministic given its inputs (the dice are rolled by the
service and passed in), which is what makes them trivially testable.
"""

from __future__ import annotations

from app.core import constants

# --- Mahriyeh ----------------------------------------------------------------


def compute_mahriyeh(level: int, money: int, market_factor: float = 1.0) -> int:
    """The Mahriyeh a player owes: ``base + level-share + wealth-share``, scaled
    by the live market factor and rounded down to a clean 100,000-Toman step.

    Money is an exact integer everywhere, so this uses integer arithmetic only
    (no floats in the money path — same rule the wallet follows).

    Args:
        level: The payer's level (>= 1).
        money: The payer's balance in Toman (>= 0).
        market_factor: Live economy multiplier (``ECONOMY_MARKET_CONDITIONS``
            / admin market knob) so the marriage market moves with the game.
    """
    level = max(1, int(level))
    money = max(0, int(money))

    amount = constants.MARRIYEH_BASE
    amount += level * constants.MARRIYEH_PER_LEVEL
    amount += money // max(1, constants.MARRIYEH_WEALTH_DIVISOR)

    if market_factor != 1.0:
        amount = int(amount * market_factor)

    amount = min(amount, constants.MARRIYEH_MAX)
    # Round down to a clean step, like the house pricing engine does.
    amount -= amount % 100_000
    return max(constants.MARRIYEH_BASE, amount)


# --- Relationship quality -----------------------------------------------------


def clamp_quality(value: int) -> int:
    """Keep quality inside ``[MIN, MAX]`` — it is a meter, not a counter."""
    return max(
        constants.RELATIONSHIP_QUALITY_MIN,
        min(constants.RELATIONSHIP_QUALITY_MAX, int(value)),
    )


def apply_quality_delta(quality: int, delta: int) -> int:
    """Return the new quality after applying ``delta`` (may be negative)."""
    return clamp_quality(quality + int(delta))


def quality_label(quality: int) -> str:
    """Human label for the profile screen (Persian, always in range)."""
    if quality >= 85:
        return "بسیار خوب"
    if quality >= 65:
        return "خوب"
    if quality >= 45:
        return "متوسط"
    if quality >= 25:
        return "سرد"
    return "بحرانی"


# --- Pregnancy ----------------------------------------------------------------


def pregnancy_chance(quality: int) -> float:
    """Chance of conception for one «رابطه» event.

    Scales linearly with relationship quality between ``1×`` and
    ``PREGNANCY_QUALITY_FACTOR_AT_100×`` the base chance, so a cold
    relationship can still (rarely) end in a child but a warm one is much more
    likely to. Always clamped into ``[0, 1]``.
    """
    base = constants.RELATIONSHIP_PREGNANCY_BASE_CHANCE
    ratio = clamp_quality(quality) / float(constants.RELATIONSHIP_QUALITY_MAX)
    low_factor = 2.0 - constants.PREGNANCY_QUALITY_FACTOR_AT_100
    factor = low_factor + (constants.PREGNANCY_QUALITY_FACTOR_AT_100 - low_factor) * ratio
    return max(0.0, min(1.0, base * factor))


# --- Cheating -----------------------------------------------------------------


def cheating_consequence(strikes_before: int) -> tuple[int, int, bool]:
    """``(money_fine, quality_penalty, forced_divorce)`` for the next discovery.

    Tiers escalate via ``constants.CHEATING_CONSEQUENCES`` and the last tier
    repeats forever, so a fourth or fifth discovery can never index out of
    range.
    """
    tiers = constants.CHEATING_CONSEQUENCES
    if not tiers:  # pragma: no cover — defensive config guard
        return (0, constants.CHEATING_DISCOVERED_QUALITY_PENALTY, False)
    index = max(0, int(strikes_before))
    return tiers[min(index, len(tiers) - 1)]


def relationship_over_index(strikes_before: int, quality_after: int) -> bool:
    """Whether a forced divorce must also happen (tier three or beyond)."""
    _, _, forced = cheating_consequence(strikes_before)
    return forced and quality_after <= constants.RELATIONSHIP_QUALITY_MIN


def can_waive_mahriyeh(strikes: int) -> bool:
    """The wronged spouse may divorce for free once the partner is caught."""
    return int(strikes) >= constants.CHEATING_WAIVER_STRIKES


__all__ = [
    "apply_quality_delta",
    "can_waive_mahriyeh",
    "cheating_consequence",
    "clamp_quality",
    "compute_mahriyeh",
    "pregnancy_chance",
    "quality_label",
    "relationship_over_index",
]
