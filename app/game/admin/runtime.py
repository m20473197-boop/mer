"""Admin-tunable runtime configuration (live overrides over constants).

The bot-settings table (see ``AdminService``) is the persistent store; this
module is a small in-memory cache so that *synchronous* call sites — the
pure pricing engines, the XP helpers, the menu builders — can read
admin-tuned values without any I/O or signature changes.

Resolution rule for every tunable: **explicit admin override wins, otherwise
the live ``constants`` value is used**. That keeps every existing behaviour
and test intact until an admin actually changes something, and it keeps
working when tests monkeypatch the constants.

The effective market factor combines three layers::

    effective = base_market_conditions × (1 + inflation_rate / 100) × events

* ``base_market_conditions`` — the admin's manual market knob (default 1.0).
* ``inflation_rate`` — inflation percent set by the admin (default 0).
* ``events`` — the product of all currently-active economic-event
  multipliers, recomputed by ``AdminService.settle_events()``.

``AdminService.refresh_runtime()`` (called at startup and after every admin
change) reloads this cache from the database.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core import constants

# --- bot_settings keys ---------------------------------------------------------

KEY_MARKET_CONDITIONS: str = "market_conditions"
KEY_INFLATION_RATE: str = "inflation_rate"
KEY_PURCHASE_XP_DIVISOR: str = "purchase_xp_divisor"
KEY_PURCHASE_XP_MIN: str = "purchase_xp_min"
KEY_PURCHASE_XP_MAX: str = "purchase_xp_max"
KEY_CONSTRUCTION_XP_DIVISOR: str = "construction_xp_divisor"
KEY_MIN_WORK_MINUTES: str = "min_work_minutes"

# Feature flags (``True`` = enabled). Housing covers houses, realestate covers
# lands / construction / renovation, jobs covers the job system.
FEATURE_JOBS: str = "jobs"
FEATURE_HOUSING: str = "housing"
FEATURE_REALESTATE: str = "realestate"
FEATURES: tuple[str, ...] = (FEATURE_JOBS, FEATURE_HOUSING, FEATURE_REALESTATE)


def _feature_key(feature: str) -> str:
    return f"{feature}_enabled"


# --- Process state ---------------------------------------------------------------

STARTED_AT: datetime = datetime.now(timezone.utc)

_overrides: dict[str, float | int | bool | str] = {}
_events_multiplier: float = 1.0


def reset_to_defaults() -> None:
    """Drop every override (used at startup and by tests)."""
    global _events_multiplier
    _overrides.clear()
    _events_multiplier = 1.0


def set_override(key: str, value: float | int | bool | str) -> None:
    """Install/refresh one cached override value."""
    _overrides[key] = value


def set_events_multiplier(multiplier: float) -> None:
    """Cache the product of the currently-active event multipliers."""
    global _events_multiplier
    _events_multiplier = multiplier if multiplier > 0 else 1.0


def events_multiplier() -> float:
    """The cached product of active economic-event multipliers."""
    return _events_multiplier


# --- Tunable getters (override wins, constants are the live fallback) -----------

def market_conditions_base() -> float:
    raw = _overrides.get(KEY_MARKET_CONDITIONS, constants.ECONOMY_MARKET_CONDITIONS)
    return float(raw)


def inflation_rate() -> float:
    return float(_overrides.get(KEY_INFLATION_RATE, 0.0))


def effective_market_factor() -> float:
    """The single economy multiplier applied to all real-estate prices."""
    factor = market_conditions_base() * (1.0 + inflation_rate() / 100.0) * _events_multiplier
    return factor if factor > 0 else 1.0


def purchase_xp_divisor() -> int:
    return int(_overrides.get(KEY_PURCHASE_XP_DIVISOR, constants.HOUSING_PURCHASE_XP_DIVISOR))


def purchase_xp_min() -> int:
    return int(_overrides.get(KEY_PURCHASE_XP_MIN, constants.HOUSING_PURCHASE_XP_MIN))


def purchase_xp_max() -> int:
    return int(_overrides.get(KEY_PURCHASE_XP_MAX, constants.HOUSING_PURCHASE_XP_MAX))


def construction_xp_divisor() -> int:
    return int(
        _overrides.get(KEY_CONSTRUCTION_XP_DIVISOR, constants.CONSTRUCTION_XP_DIVISOR)
    )


def min_work_minutes() -> int:
    return int(
        _overrides.get(KEY_MIN_WORK_MINUTES, constants.MIN_WORK_MINUTES_FOR_SETTLEMENT)
    )


def feature_enabled(feature: str) -> bool:
    """Whether a game system is enabled (unknown features are disabled)."""
    if feature not in FEATURES:
        return False
    raw = _overrides.get(_feature_key(feature), True)
    if isinstance(raw, str):
        return raw.strip().lower() not in ("0", "false", "no", "off", "")
    return bool(raw)


def uptime() -> timedelta:
    """How long this process has been running."""
    return datetime.now(timezone.utc) - STARTED_AT
