"""Natural Persian search parsing for Divar listings.

This module only parses user text into typed criteria. The marketplace
repository applies those criteria in SQL, so the parser never loads all
listings into Python.
"""

from __future__ import annotations

import re
from dataclasses import replace

from app.game.admin.parsing import parse_admin_float, parse_admin_int
from app.game.housing.catalog import CITY_BASE_PRICE_PER_SQM, CITY_NEIGHBORHOODS
from app.game.marketplace.catalog import ASSET_TYPE_HOUSE, ASSET_TYPE_LAND
from app.game.marketplace.dto import MarketplaceSearchCriteria

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "0123456789" * 2)

_STOP_WORDS = {
    "و",
    "در",
    "از",
    "تا",
    "برای",
    "آگهی",
    "آگهیهای",
    "آگهی‌ها",
    "ایران",
    "دیوار",
    "قیمت",
    "تومان",
    "متر",
    "متری",
    "مترمربع",
    "مربع",
    "خانه",
    "مسکن",
    "ملک",
    "زمین",
    "قطعه",
    "عرصه",
    "خواب",
    "اتاق",
    "سال",
    "ساخت",
}


def normalize_persian(text: str) -> str:
    """Normalize common Persian/Arabic spelling and digit variants."""
    value = (text or "").translate(_DIGITS).strip().lower()
    value = value.replace("ي", "ی").replace("ى", "ی").replace("ك", "ک")
    value = value.replace("ۀ", "ه").replace("ة", "ه").replace("ـ", "")
    value = value.replace("‌", "").replace("\u200c", "")
    value = value.replace("٬", ",").replace("٫", ".")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _canonical_match(value: str, candidates: list[str]) -> str | None:
    normalized = normalize_persian(value)
    compact = normalized.replace(" ", "")
    for candidate in sorted(candidates, key=len, reverse=True):
        candidate_normalized = normalize_persian(candidate)
        # Users commonly type a ZWNJ location such as «سعادت‌آباد» as
        # «سعادت آباد». Compare both the faithful and space-free forms.
        if candidate_normalized in normalized or candidate_normalized.replace(" ", "") in compact:
            return candidate
    return None


def _known_locations() -> tuple[list[str], list[str]]:
    cities = list(CITY_BASE_PRICE_PER_SQM)
    neighborhoods = [
        neighborhood
        for city_neighborhoods in CITY_NEIGHBORHOODS.values()
        for neighborhood in city_neighborhoods
    ]
    return cities, neighborhoods


def _number(raw: str, suffix: str = "") -> int | None:
    value = parse_admin_int(normalize_persian(raw) + suffix)
    return value if value is not None and value > 0 else None


def _positive_scaled_integer(raw: str) -> int | None:
    value = parse_admin_int(raw)
    if value is not None:
        return value if value > 0 else None
    # Exact integer Toman values such as «۷.۵ میلیارد» are valid even
    # though their compact input contains a decimal scale.
    scaled = parse_admin_float(raw)
    if scaled is None or scaled <= 0 or not scaled.is_integer():
        return None
    return int(scaled)


def parse_range_input(raw: str) -> tuple[int | None, int | None]:
    """Parse ``5 میلیارد تا 10 میلیارد`` or ``100-200`` into an inclusive range."""
    text = normalize_persian(raw)
    # Prefer the Persian word «تا»; a hyphen is also convenient on keyboards.
    pieces = re.split(r"\s*(?:تا|[-–—])\s*", text, maxsplit=1)
    if len(pieces) == 1:
        value = _positive_scaled_integer(pieces[0])
        if value is None:
            return None, None
        return value, value
    first_raw, second_raw = pieces
    scales = re.findall(r"میلیارد|میلیون|هزار|b|m|k", text)
    if scales:
        scale = scales[-1]
        if not re.search(r"(?:میلیارد|میلیون|هزار|b|m|k)", first_raw):
            first_raw = f"{first_raw}{scale}"
        if not re.search(r"(?:میلیارد|میلیون|هزار|b|m|k)", second_raw):
            second_raw = f"{second_raw}{scale}"
    first = _positive_scaled_integer(first_raw)
    second = _positive_scaled_integer(second_raw)
    if first is None or second is None:
        return None, None
    return (min(first, second), max(first, second))


def parse_search_query(query: str) -> MarketplaceSearchCriteria:
    """Turn a natural Persian query into database filters.

    Recognized examples include ``زمین 100 متری یافت آباد`` and
    ``خانه تهران 2 خواب``. Unknown words remain as SQL text terms instead of
    causing an exception or being trusted as an ID.
    """
    original = normalize_persian(query)
    text = original
    asset_type: str | None = None
    if any(word in text for word in ("زمین", "قطعه", "عرصه")):
        asset_type = ASSET_TYPE_LAND
    elif any(word in text for word in ("خانه", "مسکن", "آپارتمان", "ملک")):
        asset_type = ASSET_TYPE_HOUSE

    cities, neighborhoods = _known_locations()
    city = _canonical_match(text, cities)
    neighborhood = _canonical_match(text, neighborhoods)
    if city is None and neighborhood is not None:
        for candidate_city, values in CITY_NEIGHBORHOODS.items():
            if neighborhood in values:
                city = candidate_city
                break

    area: int | None = None
    area_min: int | None = None
    area_max: int | None = None
    area_range_match = re.search(
        r"(?P<first>\d[\d,]*)\s*(?:تا|[-–—])\s*"
        r"(?P<second>\d[\d,]*)\s*(?:متر\s*مربع|مترمربع|متری|متر)",
        text,
    )
    if area_range_match:
        area_min = _number(area_range_match.group("first"))
        area_max = _number(area_range_match.group("second"))
        if area_min is not None and area_max is not None:
            area_min, area_max = min(area_min, area_max), max(area_min, area_max)
        text = text.replace(area_range_match.group(0), " ")
    else:
        area_match = re.search(
            r"(?P<value>\d[\d,]*)\s*(?:متر\s*مربع|مترمربع|متری|متر)", text
        )
        if area_match:
            area = _number(area_match.group("value"))
            text = text.replace(area_match.group(0), " ")

    bedrooms: int | None = None
    bedroom_match = re.search(r"(?P<value>\d+)\s*(?:خواب|اتاق)", text)
    if bedroom_match:
        bedrooms = _number(bedroom_match.group("value"))
        text = text.replace(bedroom_match.group(0), " ")

    construction_year: int | None = None
    year_match = re.search(r"(?:سال\s*ساخت|ساخت)\s*(?P<value>\d{4})", text)
    if year_match:
        construction_year = _number(year_match.group("value"))
        text = text.replace(year_match.group(0), " ")

    quality = _canonical_match(text, ["لوکس", "عالی", "خوب", "متوسط", "ضعیف"])

    # Price ranges are recognized only when a scale word or a «قیمت» marker
    # is present, avoiding confusion between a bare area and a price.
    min_price: int | None = None
    max_price: int | None = None
    price_match = re.search(
        r"(?P<first>\d[\d,.]*\s*(?:میلیارد|میلیون|هزار|b|m|k)?)\s*"
        r"(?:تا|[-–—])\s*"
        r"(?P<second>\d[\d,.]*\s*(?:میلیارد|میلیون|هزار|b|m|k)?)",
        text,
    )
    if price_match and any(
        unit in price_match.group(0)
        for unit in ("میلیارد", "میلیون", "هزار", "b", "m", "k")
    ):
        min_price, max_price = parse_range_input(price_match.group(0))
        text = text.replace(price_match.group(0), " ")
    else:
        single_price_match = re.search(
            r"(?P<prefix>قیمت|حداکثر|حداقل|تا|از)\s*"
            r"(?P<value>\d[\d,.]*\s*(?:میلیارد|میلیون|هزار|b|m|k)?)",
            text,
        )
        if single_price_match:
            value = _positive_scaled_integer(single_price_match.group("value"))
            if value is not None:
                prefix = single_price_match.group("prefix")
                if prefix in ("حداکثر", "تا"):
                    max_price = value
                elif prefix in ("حداقل", "از"):
                    min_price = value
                else:
                    min_price = max_price = value
                text = text.replace(single_price_match.group(0), " ")

    # Remove known values before producing free-text terms. Search fields are
    # always bounded to short tokens; a long raw query cannot become a huge SQL
    # callback or an unbounded in-memory operation.
    for known in [
        *cities,
        *neighborhoods,
        "خانه",
        "مسکن",
        "آپارتمان",
        "ملک",
        "زمین",
        "قطعه",
        "عرصه",
        "لوکس",
        "عالی",
        "خوب",
        "متوسط",
        "ضعیف",
    ]:
        text = text.replace(normalize_persian(known), " ")
    text = re.sub(r"\d[\d,]*", " ", text)
    terms = tuple(
        token
        for token in normalize_persian(text).split()
        if len(token) >= 2 and token not in _STOP_WORDS
    )[:6]

    return MarketplaceSearchCriteria(
        asset_type=asset_type,
        city=city,
        neighborhood=neighborhood,
        min_price=min_price,
        max_price=max_price,
        min_area_sqm=area_min if area_min is not None else area,
        max_area_sqm=area_max if area_max is not None else area,
        bedrooms=bedrooms,
        construction_year=construction_year,
        quality=quality,
        text_terms=terms,
    )


def merge_search_with_filters(
    base: MarketplaceSearchCriteria, parsed: MarketplaceSearchCriteria
) -> MarketplaceSearchCriteria:
    """Combine a fresh natural-language query with existing structured filters."""
    return replace(
        base,
        asset_type=parsed.asset_type or base.asset_type,
        city=parsed.city or base.city,
        neighborhood=parsed.neighborhood or base.neighborhood,
        min_price=parsed.min_price if parsed.min_price is not None else base.min_price,
        max_price=parsed.max_price if parsed.max_price is not None else base.max_price,
        min_area_sqm=parsed.min_area_sqm if parsed.min_area_sqm is not None else base.min_area_sqm,
        max_area_sqm=parsed.max_area_sqm if parsed.max_area_sqm is not None else base.max_area_sqm,
        bedrooms=parsed.bedrooms if parsed.bedrooms is not None else base.bedrooms,
        construction_year=(
            parsed.construction_year
            if parsed.construction_year is not None
            else base.construction_year
        ),
        quality=parsed.quality or base.quality,
        text_terms=parsed.text_terms,
    )
