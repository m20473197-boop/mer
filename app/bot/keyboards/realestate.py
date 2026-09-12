"""Land / Construction / Renovation keyboard builders — fully button-driven."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards import callbacks
from app.bot.keyboards.main_menu import BUTTON_BACK_TO_MAIN
from app.bot.messages.formatters import fa_int

# --- Button labels (housing menu section) ---------------------------------------

BUTTON_LANDS_MY: str = "🌍 زمین‌های من"
BUTTON_LANDS_MARKET: str = "🛒 خرید زمین"
BUTTON_BUILD: str = "🏗️ ساخت خانه"
BUTTON_BUILD_STATUS: str = "📈 وضعیت ساخت"
BUTTON_RENOVATE: str = "🛠️ بازسازی خانه"
BUTTON_BACK_TO_HOUSING: str = "🔙 منوی خانه"

BUTTON_BUY_LAND: str = "🛒 خرید"
BUTTON_CONFIRM_BUY_LAND: str = "✅ تأیید خرید زمین"
BUTTON_BUILD_HERE: str = "🏗️ ساخت خانه در این زمین"
BUTTON_CANCEL_CONSTRUCTION: str = "❌ لغو پروژه"


def _back_rows() -> list[list[InlineKeyboardButton]]:
    return [
        [
            InlineKeyboardButton(
                BUTTON_BACK_TO_HOUSING, callback_data=callbacks.HOUSING_MENU
            ),
            InlineKeyboardButton(
                BUTTON_BACK_TO_MAIN, callback_data=callbacks.BACK_TO_MAIN
            ),
        ]
    ]


def build_lands_market(entries) -> InlineKeyboardMarkup:
    """Available parcels — info + buy per row."""
    rows: list[list[InlineKeyboardButton]] = []
    for entry in entries:
        label = (
            f"{entry.land.city}، {entry.land.neighborhood} — "
            f"{fa_int(entry.land.area_sqm)} متری ({fa_int(entry.price)})"
        )
        rows.append(
            [
                InlineKeyboardButton(
                    label, callback_data=f"{callbacks.RE_LAND_INFO_PREFIX}{entry.land.id}"
                ),
                InlineKeyboardButton(
                    BUTTON_BUY_LAND,
                    callback_data=f"{callbacks.RE_LAND_BUY_PREFIX}{entry.land.id}",
                ),
            ]
        )
    if not rows:
        rows.append(
            [InlineKeyboardButton("— زمینی موجود نیست —", callback_data=callbacks.HOUSING_MENU)]
        )
    rows.extend(_back_rows())
    return InlineKeyboardMarkup(rows)


def build_my_lands(assets) -> InlineKeyboardMarkup:
    """The player's parcels — info, and contextual status buttons."""
    rows: list[list[InlineKeyboardButton]] = []
    for item in assets.lands:
        land = item.land
        label = f"{land.city}، {land.neighborhood} ({fa_int(land.area_sqm)} متری)"
        rows.append(
            [
                InlineKeyboardButton(
                    f"ℹ️ {label}",
                    callback_data=f"{callbacks.RE_LAND_INFO_PREFIX}{land.id}",
                )
            ]
        )
        actions: list[InlineKeyboardButton] = []
        if item.active_construction is not None:
            actions.append(
                InlineKeyboardButton(
                    f"📈 {fa_int(int(item.active_construction.progress_percent))}٪ "
                    "ساخت",
                    callback_data=callbacks.RE_STATUS,
                )
            )
            actions.append(
                InlineKeyboardButton(
                    BUTTON_CANCEL_CONSTRUCTION,
                    callback_data=(
                        f"{callbacks.RE_BUILD_CANCEL_PREFIX}"
                        f"{item.active_construction.id}"
                    ),
                )
            )
        elif land.built_house_id is not None:
            actions.append(
                InlineKeyboardButton(
                    "🏠 خانه ساخته‌شده",
                    callback_data=f"{callbacks.HOUSE_INFO_PREFIX}{land.built_house_id}",
                )
            )
        else:
            actions.append(
                InlineKeyboardButton(
                    BUTTON_BUILD_HERE,
                    callback_data=f"{callbacks.RE_BUILD_LAND_PREFIX}{land.id}",
                )
            )
        rows.append(actions)
    if not rows:
        rows.append(
            [
                InlineKeyboardButton(
                    "— هنوز زمینی نداری —", callback_data=callbacks.RE_LANDS_MARKET
                )
            ]
        )
    rows.extend(_back_rows())
    return InlineKeyboardMarkup(rows)


def build_land_info(info, viewer_player_id: int | None) -> InlineKeyboardMarkup:
    """Context-aware buttons under a parcel information screen."""
    rows: list[list[InlineKeyboardButton]] = []
    land = info.land
    is_owner = viewer_player_id is not None and land.owner_player_id == viewer_player_id

    if land.owner_player_id is None:
        rows.append(
            [
                InlineKeyboardButton(
                    BUTTON_CONFIRM_BUY_LAND,
                    callback_data=f"{callbacks.RE_LAND_BUY_OK_PREFIX}{land.id}",
                )
            ]
        )
    elif is_owner and info.active_construction is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    BUTTON_CANCEL_CONSTRUCTION,
                    callback_data=(
                        f"{callbacks.RE_BUILD_CANCEL_PREFIX}"
                        f"{info.active_construction.id}"
                    ),
                ),
                InlineKeyboardButton(
                    "📈 وضعیت ساخت", callback_data=callbacks.RE_STATUS
                ),
            ]
        )
    elif is_owner and land.built_house_id is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    "ℹ️ اطلاعات خانه ساخته‌شده",
                    callback_data=f"{callbacks.HOUSE_INFO_PREFIX}{land.built_house_id}",
                )
            ]
        )
    elif is_owner:
        rows.append(
            [
                InlineKeyboardButton(
                    BUTTON_BUILD_HERE,
                    callback_data=f"{callbacks.RE_BUILD_LAND_PREFIX}{land.id}",
                )
            ]
        )
    rows.extend(_back_rows())
    return InlineKeyboardMarkup(rows)


def build_land_buy_confirmation(land_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    BUTTON_CONFIRM_BUY_LAND,
                    callback_data=f"{callbacks.RE_LAND_BUY_OK_PREFIX}{land_id}",
                )
            ],
            *_back_rows(),
        ]
    )


def build_vacant_lands(entries) -> InlineKeyboardMarkup:
    """Pick one of your vacant parcels to build on (ساخت خانه)."""
    rows: list[list[InlineKeyboardButton]] = []
    for item in entries:
        land = item.land
        label = f"{land.city}، {land.neighborhood} ({fa_int(land.area_sqm)} متری)"
        rows.append(
            [
                InlineKeyboardButton(
                    f"🏗️ {label}",
                    callback_data=f"{callbacks.RE_BUILD_LAND_PREFIX}{land.id}",
                )
            ]
        )
    if not rows:
        rows.append(
            [
                InlineKeyboardButton(
                    "— زمین خالی نداری —", callback_data=callbacks.RE_LANDS_MARKET
                )
            ]
        )
    rows.extend(_back_rows())
    return InlineKeyboardMarkup(rows)


def build_option_grid(
    options: list[tuple[str, str]],
    *,
    back_callback: str,
) -> InlineKeyboardMarkup:
    """A generic grid of (label, callback) options plus a back row."""
    rows = [
        [InlineKeyboardButton(label, callback_data=cb)] for label, cb in options
    ]
    rows.append([InlineKeyboardButton("🔙 مرحله قبل", callback_data=back_callback)])
    rows.extend(_back_rows())
    return InlineKeyboardMarkup(rows)


def build_construction_confirmation(
    land_id: int,
    blueprint: str,
) -> InlineKeyboardMarkup:
    """Start/no buttons under the blueprint confirmation sheet."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ شروع ساخت",
                    callback_data=f"{callbacks.RE_BUILD_EXEC_PREFIX}{blueprint}",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 تغییر امکانات",
                    callback_data=(
                        f"{callbacks.RE_BUILD_SPEC_PREFIX}{blueprint_spec_part(blueprint)}"
                    ),
                )
            ],
            *_back_rows(),
        ]
    )


def blueprint_spec_part(full: str) -> str:
    """The ``re_bs_…`` spec payload of a full ``land_t_fl_sz_br_q_PES`` string."""
    # full is like "5_a_3_180_2_g_P1E1S1"; the spec steps stop before _P…S…
    parts = full.split("_")
    for index, part in enumerate(parts):
        if part.startswith("P") and "E" in part:
            return "_".join(parts[:index])
    return full


def build_status_screen(status) -> InlineKeyboardMarkup:
    """Project status rows with cancel buttons for active constructions."""
    rows: list[list[InlineKeyboardButton]] = []
    for project in status.constructions:
        if project.status == "in_progress":
            rows.append(
                [
                    InlineKeyboardButton(
                        f"❌ لغو ساخت #{fa_int(project.id)}",
                        callback_data=f"{callbacks.RE_BUILD_CANCEL_PREFIX}{project.id}",
                    )
                ]
            )
        elif project.house_id is not None:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"🏠 خانه آماده #{fa_int(project.house_id)}",
                        callback_data=(
                            f"{callbacks.HOUSE_INFO_PREFIX}{project.house_id}"
                        ),
                    )
                ]
            )
    for project in status.renovations:
        if project.status == "in_progress":
            rows.append(
                [
                    InlineKeyboardButton(
                        f"🛠️ {project.title} ({fa_int(int(project.progress_percent))}٪)",
                        callback_data=callbacks.RE_STATUS,
                    )
                ]
            )
    rows.extend(_back_rows())
    return InlineKeyboardMarkup(rows)


def build_renovatable_houses(houses) -> InlineKeyboardMarkup:
    """Pick one of your houses to renovate (بازسازی خانه)."""
    rows: list[list[InlineKeyboardButton]] = []
    for house in houses:
        label = f"{house.city}، {house.neighborhood} ({fa_int(house.area_sqm)} متری)"
        rows.append(
            [
                InlineKeyboardButton(
                    f"🛠️ {label}",
                    callback_data=f"{callbacks.RE_RENOV_OPTS_PREFIX}{house.id}",
                )
            ]
        )
    if not rows:
        rows.append(
            [
                InlineKeyboardButton(
                    "— خانه‌ای برای بازسازی نداری —",
                    callback_data=callbacks.HOUSES_MY,
                )
            ]
        )
    rows.extend(_back_rows())
    return InlineKeyboardMarkup(rows)


def build_renovation_options(house_id: int, options) -> InlineKeyboardMarkup:
    """Applicable renovation quotes for one house."""
    rows: list[list[InlineKeyboardButton]] = []
    for option in options:
        if not option.applicable:
            continue
        label = (
            f"{option.title} — {option.description} "
            f"({fa_int(option.cost)} · {fa_int(max(1, option.duration_seconds // 86400))} روز)"
        )
        rows.append(
            [
                InlineKeyboardButton(
                    label,
                    callback_data=(
                        f"{callbacks.RE_RENOV_CONFIRM_PREFIX}"
                        f"{house_id}_{option.renovation_type}"
                    ),
                )
            ]
        )
    if not rows:
        rows.append(
            [
                InlineKeyboardButton(
                    "— چیزی برای بازسازی نیست —",
                    callback_data=callbacks.HOUSES_MY,
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                "🔙 انتخاب خانه دیگر", callback_data=callbacks.RE_RENOV_MENU
            )
        ]
    )
    rows.extend(_back_rows())
    return InlineKeyboardMarkup(rows)


def build_renovation_confirmation(house_id: int, renovation_type: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ شروع بازسازی",
                    callback_data=(
                        f"{callbacks.RE_RENOV_OK_PREFIX}"
                        f"{house_id}_{renovation_type}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 گزینه‌های دیگر",
                    callback_data=f"{callbacks.RE_RENOV_OPTS_PREFIX}{house_id}",
                )
            ],
            *_back_rows(),
        ]
    )
