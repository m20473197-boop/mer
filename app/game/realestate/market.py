"""Market conditions — the shared economy factor of the whole real-estate market.

Land prices, construction costs and renovation costs are all multiplied by
this factor, so a single economic change (inflation, recession, a boom) moves
every price in the game at once. Nothing anywhere is a fixed price.

The admin-panel Economy system integrates by writing overrides into
``app.game.admin.runtime`` (backed by the ``bot_settings`` table plus the
currently-active economic events); an explicit ``market_factor`` passed into
the pricing functions still wins over everything.

The housing pricing engine (``app/game/housing/pricing.py``) accepts the same
``market_factor`` argument, so one knob drives both markets.
"""

from __future__ import annotations

from app.game.admin import runtime


def current_market_factor() -> float:
    """The live market/economy multiplier applied to all real-estate prices.

    With no admin changes this is exactly
    ``constants.ECONOMY_MARKET_CONDITIONS`` (default 1.0); the admin panel can
    then move it via market conditions, inflation and economic events.
    """
    return runtime.effective_market_factor()
