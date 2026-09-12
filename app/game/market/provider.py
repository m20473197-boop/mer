"""Replaceable external market-data integration for Iranian quotes.

The market service depends only on :class:`MarketDataProvider`. The default
implementation reads the current Iranian free-market pages published by
TGJU. Those pages quote Rial; this adapter validates the response and converts
it to exact whole Toman before the value reaches the service/database.

No Telegram handler or unrelated game service imports this module directly.
Tests and a future paid/API provider can implement the small protocol instead.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import Mapping, Protocol

from app.core import constants
from app.game.market.catalog import IRAN_MARKET_ASSET_CATALOG

logger = logging.getLogger(__name__)


class MarketDataError(RuntimeError):
    """Raised when the external source cannot provide a valid full snapshot."""


class MarketDataProvider(Protocol):
    """Minimal provider contract used by ``MarketService``."""

    @property
    def source_name(self) -> str:
        ...

    async def fetch_prices(self) -> Mapping[str, int]:
        """Return Toman prices for all three external market assets."""
        ...


@dataclass(frozen=True, slots=True)
class TGJUProviderConfig:
    """Runtime-configurable TGJU adapter settings."""

    base_url: str = constants.IRAN_MARKET_PROVIDER_BASE_URL
    timeout_seconds: float = constants.IRAN_MARKET_API_TIMEOUT_SECONDS
    retry_attempts: int = constants.IRAN_MARKET_API_RETRY_ATTEMPTS
    retry_backoff_seconds: float = constants.IRAN_MARKET_API_RETRY_BACKOFF_SECONDS
    user_agent: str = constants.IRAN_MARKET_PROVIDER_USER_AGENT
    api_key: str | None = None

    @classmethod
    def from_environment(cls) -> "TGJUProviderConfig":
        """Read optional provider overrides without logging credentials."""
        return cls(
            base_url=os.getenv(
                "IRAN_MARKET_PROVIDER_BASE_URL",
                constants.IRAN_MARKET_PROVIDER_BASE_URL,
            ).strip().rstrip("/"),
            timeout_seconds=_positive_float(
                os.getenv("IRAN_MARKET_API_TIMEOUT_SECONDS"),
                constants.IRAN_MARKET_API_TIMEOUT_SECONDS,
            ),
            retry_attempts=_positive_int(
                os.getenv("IRAN_MARKET_API_RETRY_ATTEMPTS"),
                constants.IRAN_MARKET_API_RETRY_ATTEMPTS,
            ),
            retry_backoff_seconds=_non_negative_float(
                os.getenv("IRAN_MARKET_API_RETRY_BACKOFF_SECONDS"),
                constants.IRAN_MARKET_API_RETRY_BACKOFF_SECONDS,
            ),
            user_agent=os.getenv(
                "IRAN_MARKET_PROVIDER_USER_AGENT",
                constants.IRAN_MARKET_PROVIDER_USER_AGENT,
            ).strip()
            or constants.IRAN_MARKET_PROVIDER_USER_AGENT,
            api_key=os.getenv(constants.IRAN_MARKET_PROVIDER_API_KEY_ENV) or None,
        )

    def validate(self) -> None:
        if not self.base_url:
            raise ValueError("IRAN_MARKET_PROVIDER_BASE_URL cannot be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("IRAN_MARKET_API_TIMEOUT_SECONDS must be positive")
        if self.retry_attempts < 1:
            raise ValueError("IRAN_MARKET_API_RETRY_ATTEMPTS must be at least one")
        if self.retry_backoff_seconds < 0:
            raise ValueError("IRAN_MARKET_API_RETRY_BACKOFF_SECONDS cannot be negative")


class TGJUProvider:
    """Fetch real USD, 18k gold and Emami-coin values from TGJU pages."""

    source_name = constants.IRAN_MARKET_PROVIDER_NAME
    _PRICE_PATTERN = re.compile(
        r'data-col=["\']info\.last_trade\.PDrCotVal["\'][^>]*>'
        r"\s*([^<]+?)\s*</span>",
        re.IGNORECASE,
    )
    _DIGIT_TRANSLATION = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٬،",
        "01234567890123456789,,",
    )

    def __init__(self, config: TGJUProviderConfig | None = None) -> None:
        self.config = config or TGJUProviderConfig.from_environment()
        self.config.validate()

    async def fetch_prices(self) -> Mapping[str, int]:
        """Fetch all required quotes; a partial response is a failed update."""
        definitions = [
            asset
            for asset in IRAN_MARKET_ASSET_CATALOG
            if asset.source_symbol is not None
        ]
        results = await asyncio.gather(
            *(
                self._fetch_with_retries(asset.code, asset.source_symbol or "")
                for asset in definitions
            ),
            return_exceptions=True,
        )
        prices: dict[str, int] = {}
        failures: list[str] = []
        for definition, result in zip(definitions, results, strict=True):
            if isinstance(result, Exception):
                failures.append(definition.code)
                logger.warning(
                    "Iran market provider failed for %s after retries (%s)",
                    definition.code,
                    type(result).__name__,
                )
                continue
            prices[definition.code] = result
        if failures:
            raise MarketDataError(
                "provider returned no complete snapshot for: " + ", ".join(failures)
            )
        return prices

    async def _fetch_with_retries(self, code: str, symbol: str) -> int:
        last_error: Exception | None = None
        for attempt in range(self.config.retry_attempts):
            try:
                html = await asyncio.to_thread(self._fetch_page, symbol)
                return self._parse_toman_price(html, code)
            except Exception as exc:  # noqa: BLE001 — normalized below
                last_error = exc
                if attempt + 1 < self.config.retry_attempts:
                    delay = self.config.retry_backoff_seconds * (2**attempt)
                    if delay:
                        await asyncio.sleep(delay)
        raise MarketDataError(f"invalid or unavailable quote for {code}") from last_error

    def _fetch_page(self, symbol: str) -> str:
        url = f"{self.config.base_url}/{symbol}"
        headers = {"User-Agent": self.config.user_agent, "Accept": "text/html"}
        if self.config.api_key:
            # Kept generic for a future configured gateway; the default TGJU
            # source does not require a key. Never include this header in logs.
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
            if response.status < 200 or response.status >= 300:
                raise MarketDataError(f"provider HTTP status {response.status}")
            return response.read().decode("utf-8", errors="replace")

    def _parse_toman_price(self, html: str, code: str) -> int:
        match = self._PRICE_PATTERN.search(html)
        if match is None:
            raise MarketDataError(f"provider price field missing for {code}")
        digits = match.group(1).translate(self._DIGIT_TRANSLATION).strip()
        digits = re.sub(r"\s+", "", digits)
        if not re.fullmatch(r"(?:\d{1,3}(?:,\d{3})+|\d+)", digits):
            raise MarketDataError(f"provider price is not numeric for {code}")
        rial_price = int(digits.replace(",", ""))
        if rial_price <= 0:
            raise MarketDataError(f"provider price is not positive for {code}")
        toman_price = rial_price // constants.IRAN_MARKET_RIALS_PER_TOMAN
        if toman_price <= 0:
            raise MarketDataError(f"provider Toman price is not positive for {code}")
        return toman_price


def _positive_float(raw: str | None, default: float) -> float:
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _non_negative_float(raw: str | None, default: float) -> float:
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


def _positive_int(raw: str | None, default: int) -> int:
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= 1 else default
