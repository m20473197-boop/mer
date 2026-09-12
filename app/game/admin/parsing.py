"""Parsing of admin-typed values (pure — no I/O).

Admins type numbers on a Persian keyboard, so Persian/Arabic digits, Persian
thousands separators and short scale suffixes are all accepted::

    "۱٬۵۰۰٬۰۰۰"  → 1500000
    "10m" / "۱۰ میلیون" → 10000000
    "2.5" / "۲/۵" → 2.5
"""

from __future__ import annotations

import re

_FA_AR_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "0123456789" * 2
)

# Short scale suffixes (Latin + Persian words).
_SUFFIX_MULTIPLIERS: tuple[tuple[str, int], ...] = (
    ("میلیارد", 1_000_000_000),
    ("b", 1_000_000_000),
    ("میلیون", 1_000_000),
    ("m", 1_000_000),
    ("هزار", 1_000),
    ("k", 1_000),
)

_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")


def _normalize(raw: str) -> str:
    text = (raw or "").translate(_FA_AR_DIGITS).strip()
    # Decimal separators used on Persian keyboards.
    text = text.replace("٫", ".").replace("/", ".")
    # Thousands separators and invisible spacing.
    for sep in ("٬", ",", "_", " ", " ", "‌"):
        text = text.replace(sep, "")
    return text.lower()


def _split_suffix(text: str) -> tuple[str, int]:
    for suffix, multiplier in _SUFFIX_MULTIPLIERS:
        if text.endswith(suffix):
            return text[: -len(suffix)], multiplier
    return text, 1


def parse_admin_int(raw: str) -> int | None:
    """Parse an admin-typed integer (``None`` when invalid)."""
    text, multiplier = _split_suffix(_normalize(raw))
    if not text or not _INT_RE.match(text):
        return None
    try:
        return int(text) * multiplier
    except ValueError:
        return None


def parse_admin_float(raw: str) -> float | None:
    """Parse an admin-typed float (``None`` when invalid).

    A leading or trailing ``%``/``٪`` is accepted and ignored (the caller
    decides what the number means).
    """
    text = (
        _normalize(raw)
        .removesuffix("%")
        .removesuffix("٪")
        .removeprefix("%")
        .removeprefix("٪")
    )
    text, multiplier = _split_suffix(text)
    if not text or not _FLOAT_RE.match(text):
        return None
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def parse_admin_percent(raw: str) -> float | None:
    """Parse a percent value such as ``٪۱۲`` / ``12%`` / ``12``."""
    return parse_admin_float(raw)
