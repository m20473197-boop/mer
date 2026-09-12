"""The renovation domain (pure math — no I/O).

Every renovation type targets one aspect of a house and, when completed,
**permanently changes the house's attributes**. Because house value is always
recomputed dynamically from the attributes (``app/game/housing/pricing.py``),
every completed renovation automatically raises the property value — nothing
about value is stored or patched.

Options (each costs money and takes time):

* ``quality``   — one quality level up (ارتقای کیفیت / تعمیر اساسی)
* ``kitchen``   — kitchen one grade up (بازسازی آشپزخانه)
* ``bathroom``  — add a bathroom (بازسازی سرویس بهداشتی)
* ``add_room``  — add a bedroom (اتاق اضافه)
* ``parking``   — add parking (پارکینگ)
* ``elevator``  — add an elevator (آسانسور)
* ``storage``   — add storage (انباری)
* ``modernize`` — modernize an old building (نوسازی): shaves years off

Costs depend on the house's area, the work required and the live market
conditions (material prices) — never fixed numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.game.housing.construction_year import (
    age_from_construction_year,
)
from app.game.realestate.market import current_market_factor

# Renovation type codes (ASCII for compact callback data).
R_QUALITY: str = "q"
R_KITCHEN: str = "k"
R_BATHROOM: str = "ba"
R_ADD_ROOM: str = "r"
R_PARKING: str = "p"
R_ELEVATOR: str = "e"
R_STORAGE: str = "s"
R_MODERNIZE: str = "m"

RENOVATION_TYPE_LABELS: dict[str, str] = {
    R_QUALITY: "ارتقای کیفیت",
    R_KITCHEN: "بازسازی آشپزخانه",
    R_BATHROOM: "بازسازی سرویس بهداشتی",
    R_ADD_ROOM: "اتاق اضافه",
    R_PARKING: "افزودن پارکینگ",
    R_ELEVATOR: "نصب آسانسور",
    R_STORAGE: "افزودن انباری",
    R_MODERNIZE: "نوسازی ساختمان",
}

# Quality ladder used by the quality upgrade.
QUALITY_LADDER: tuple[str, ...] = ("ضعیف", "متوسط", "خوب", "عالی")

# Cost per square meter of each quality transition (Toman/sqm).
QUALITY_UPGRADE_COST_PER_SQM: dict[str, int] = {
    # from-quality → cost per sqm to reach the next level
    "ضعیف": 1_500_000,
    "متوسط": 2_000_000,
    "خوب": 3_000_000,
}

# Kitchen renovation: cost per sqm by current kitchen grade.
KITCHEN_UPGRADE_COST_PER_SQM: dict[str, int] = {
    "معمولی": 800_000,   # → مدرن
    "قدیمی": 500_000,    # → معمولی
}
KITCHEN_UPGRADE_TARGET: dict[str, str] = {
    "معمولی": "مدرن",
    "قدیمی": "معمولی",
}

BATHROOM_BASE_COST: int = 100_000_000
BATHROOM_COST_PER_SQM: int = 200_000
ADD_ROOM_COST: int = 400_000_000
PARKING_COST: int = 200_000_000
ELEVATOR_COST: int = 600_000_000
STORAGE_COST: int = 80_000_000
MODERNIZE_COST_PER_SQM: int = 2_000_000

# Duration of each renovation, in days.
DURATION_DAYS: dict[str, float] = {
    R_QUALITY: 7.0,
    R_KITCHEN: 3.0,
    R_BATHROOM: 2.0,
    R_ADD_ROOM: 4.0,
    R_PARKING: 1.0,
    R_ELEVATOR: 7.0,
    R_STORAGE: 1.0,
    R_MODERNIZE: 10.0,
}
SECONDS_PER_DAY: int = 86_400

# Modernizing shaves this many years off the building's age.
MODERNIZE_AGE_REDUCTION: int = 15
# Modernize is only meaningful from this age upwards.
MODERNIZE_MIN_AGE: int = 5

# A house can hold at most this many bathrooms.
MAX_BATHROOMS: int = 4

# Persian digit rendering for year descriptions (kept local so the domain
# layer never depends on the Telegram/bot layer).
_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _fa_year(year: int) -> str:
    return str(year).translate(_FA_DIGITS)

COST_ROUNDING_STEP: int = 100_000


@dataclass(frozen=True, slots=True)
class RenovationOption:
    """One renovatable aspect of a specific house, with its live quote."""

    renovation_type: str
    title: str
    description: str        # what changes, e.g. «کیفیت: خوب → عالی»
    cost: int
    duration_seconds: int
    applicable: bool
    reason: str = ""        # why not applicable (shown when relevant)


def _round_cost(amount: float) -> int:
    return max(COST_ROUNDING_STEP, int(amount // COST_ROUNDING_STEP) * COST_ROUNDING_STEP)


def _next_quality(quality: str) -> str | None:
    try:
        index = QUALITY_LADDER.index(quality)
    except ValueError:
        return None
    return QUALITY_LADDER[index + 1] if index + 1 < len(QUALITY_LADDER) else None


def quality_upgrade_description(quality: str) -> str | None:
    target = _next_quality(quality)
    return f"کیفیت: {quality} → {target}" if target else None


def available_renovations(house) -> list[RenovationOption]:
    """Quote every renovation for this house (applicable ones first).

    ``house`` is any object exposing the House attributes (ORM model or DTO):
    ``area_sqm, quality, kitchen_type, bathrooms, bedrooms, parking, elevator,
    storage, construction_year``.
    """
    factor = current_market_factor()
    area = house.area_sqm
    options: list[RenovationOption] = []

    def option(
        rtype: str,
        description: str,
        cost: float,
        applicable: bool,
        reason: str = "",
    ) -> RenovationOption:
        return RenovationOption(
            renovation_type=rtype,
            title=RENOVATION_TYPE_LABELS[rtype],
            description=description,
            cost=_round_cost(cost * factor),
            duration_seconds=int(DURATION_DAYS[rtype] * SECONDS_PER_DAY),
            applicable=applicable,
            reason=reason,
        )

    # Quality upgrade
    target_quality = _next_quality(house.quality)
    if target_quality is None:
        options.append(option(R_QUALITY, "کیفیت از قبل عالی است", 0, False, "قابل ارتقا نیست"))
    else:
        cost = area * QUALITY_UPGRADE_COST_PER_SQM[house.quality]
        options.append(
            option(R_QUALITY, f"کیفیت: {house.quality} → {target_quality}", cost, True)
        )

    # Kitchen renovation
    kitchen_target = KITCHEN_UPGRADE_TARGET.get(house.kitchen_type)
    if kitchen_target is None:
        options.append(option(R_KITCHEN, "آشپزخانه از قبل مدرن است", 0, False, "قابل ارتقا نیست"))
    else:
        cost = area * KITCHEN_UPGRADE_COST_PER_SQM[house.kitchen_type]
        options.append(
            option(R_KITCHEN, f"آشپزخانه: {house.kitchen_type} → {kitchen_target}", cost, True)
        )

    # Bathroom
    if house.bathrooms >= MAX_BATHROOMS:
        options.append(option(R_BATHROOM, f"سرویس‌ها از قبل {MAX_BATHROOMS} تا است", 0, False, "امکان افزایش نیست"))
    else:
        cost = BATHROOM_BASE_COST + area * BATHROOM_COST_PER_SQM
        options.append(
            option(R_BATHROOM, f"سرویس بهداشتی: {house.bathrooms} → {house.bathrooms + 1}", cost, True)
        )

    # Extra bedroom (bounded by livable area)
    room_capacity = max(1, area // 35)
    if house.bedrooms >= room_capacity:
        options.append(
            option(R_ADD_ROOM, f"ظرفیت اتاق‌ها در این متراژ پر است ({room_capacity} اتاق)", 0, False, "متراژ اجازه نمی‌دهد")
        )
    else:
        options.append(
            option(R_ADD_ROOM, f"اتاق: {house.bedrooms} → {house.bedrooms + 1}", ADD_ROOM_COST, True)
        )

    # Facilities
    options.append(
        option(R_PARKING, "پارکینگ: ندارد → دارد", PARKING_COST, not house.parking,
               "از قبل دارد" if house.parking else "")
    )
    options.append(
        option(R_ELEVATOR, "آسانسور: ندارد → دارد", ELEVATOR_COST, not house.elevator,
               "از قبل دارد" if house.elevator else "")
    )
    options.append(
        option(R_STORAGE, "انباری: ندارد → دارد", STORAGE_COST, not house.storage,
               "از قبل دارد" if house.storage else "")
    )

    # Modernize old buildings (age derived from the construction year)
    building_age = age_from_construction_year(house.construction_year)
    if building_age < MODERNIZE_MIN_AGE:
        options.append(
            option(R_MODERNIZE, "بنا از قبل نو است", 0, False, "نیازی به نوسازی نیست")
        )
    else:
        new_year = house.construction_year + MODERNIZE_AGE_REDUCTION
        cost = area * MODERNIZE_COST_PER_SQM
        options.append(
            option(
                R_MODERNIZE,
                f"سال ساخت: {_fa_year(house.construction_year)} → {_fa_year(new_year)}",
                cost,
                True,
            )
        )

    options.sort(key=lambda o: (not o.applicable, o.cost))
    return options


def is_applicable(house, renovation_type: str) -> bool:
    """Whether ``renovation_type`` can be applied to this house right now."""
    for option in available_renovations(house):
        if option.renovation_type == renovation_type:
            return option.applicable
    return False


def renovation_quote(house, renovation_type: str) -> RenovationOption:
    """The live quote for one renovation type.

    Raises:
        ValueError: If the type is unknown or not applicable.
    """
    for option in available_renovations(house):
        if option.renovation_type == renovation_type:
            if not option.applicable:
                raise ValueError(option.reason or "این بازسازی برای این خانه امکان‌پذیر نیست")
            return option
    raise ValueError(f"unknown renovation type: {renovation_type!r}")


def apply_renovation(house, renovation_type: str) -> dict[str, object]:
    """Compute the attribute changes for one completed renovation.

    Returns a ``{field: new_value}`` dict to apply to the House — the value
    increase is implicit, because pricing always derives from attributes.

    Raises:
        ValueError: If the type is unknown or not applicable.
    """
    quote = renovation_quote(house, renovation_type)  # validates applicability
    del quote  # only used for validation

    if renovation_type == R_QUALITY:
        return {"quality": _next_quality(house.quality)}
    if renovation_type == R_KITCHEN:
        return {"kitchen_type": KITCHEN_UPGRADE_TARGET[house.kitchen_type]}
    if renovation_type == R_BATHROOM:
        return {"bathrooms": house.bathrooms + 1}
    if renovation_type == R_ADD_ROOM:
        return {"bedrooms": house.bedrooms + 1}
    if renovation_type == R_PARKING:
        return {"parking": True}
    if renovation_type == R_ELEVATOR:
        return {"elevator": True}
    if renovation_type == R_STORAGE:
        return {"storage": True}
    if renovation_type == R_MODERNIZE:
        from app.game.housing.construction_year import current_iranian_year

        current = current_iranian_year()
        return {
            "construction_year": min(
                current, house.construction_year + MODERNIZE_AGE_REDUCTION
            )
        }
    raise ValueError(f"unknown renovation type: {renovation_type!r}")
