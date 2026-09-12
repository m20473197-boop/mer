"""The exact four assets shown by ``📈 بازار ایران``.

This catalog intentionally has no cryptocurrency, goods, investment or
player-trading entries. The older admin-economy asset table is a separate
internal/admin feature and is not used by the player-facing Iranian market.
"""

from __future__ import annotations

from dataclasses import dataclass


ASSET_CURRENCY: str = "currency"
ASSET_GOLD: str = "gold"
ASSET_COIN: str = "coin"
ASSET_HOUSING: str = "housing"

USD_CODE: str = "USD"
GOLD_CODE: str = "GOLD18"
COIN_CODE: str = "COIN_EMAMI"
HOUSING_CODE: str = "HOUSING_REFERENCE"


@dataclass(frozen=True, slots=True)
class IranMarketAssetDefinition:
    """One fixed, player-facing Iranian market asset."""

    code: str
    display_name: str
    category: str
    source_symbol: str | None
    unit_label: str
    is_active: bool = True


# USD, 18-karat gold per gram and Emami coin are the three real Iranian
# market quotes fetched from the provider. Housing is a deterministic
# reference per square metre derived from the existing Iranian housing catalog.
IRAN_MARKET_ASSET_CATALOG: tuple[IranMarketAssetDefinition, ...] = (
    IranMarketAssetDefinition(
        code=USD_CODE,
        display_name="دلار",
        category=ASSET_CURRENCY,
        source_symbol="price_dollar_rl",
        unit_label="تومان",
    ),
    IranMarketAssetDefinition(
        code=GOLD_CODE,
        display_name="طلا",
        category=ASSET_GOLD,
        source_symbol="geram18",
        unit_label="تومان/گرم",
    ),
    IranMarketAssetDefinition(
        code=COIN_CODE,
        display_name="سکه",
        category=ASSET_COIN,
        source_symbol="sekee",
        unit_label="تومان",
    ),
    IranMarketAssetDefinition(
        code=HOUSING_CODE,
        display_name="مسکن",
        category=ASSET_HOUSING,
        source_symbol=None,
        unit_label="تومان/متر",
    ),
)

IRAN_MARKET_ASSET_CODES: tuple[str, ...] = tuple(
    asset.code for asset in IRAN_MARKET_ASSET_CATALOG
)
_EXTERNAL_ASSET_CODES: frozenset[str] = frozenset(
    asset.code for asset in IRAN_MARKET_ASSET_CATALOG if asset.source_symbol is not None
)


def get_asset_definition(code: str) -> IranMarketAssetDefinition | None:
    """Find one of the four configured assets by stable code."""
    return next(
        (asset for asset in IRAN_MARKET_ASSET_CATALOG if asset.code == code),
        None,
    )


def is_external_asset(code: str) -> bool:
    """Whether the asset must come from real external Iranian market data."""
    return code in _EXTERNAL_ASSET_CODES
