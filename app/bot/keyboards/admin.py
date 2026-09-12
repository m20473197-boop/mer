"""Admin-panel keyboard builders — the whole panel is button-driven."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards import callbacks
from app.game.admin import dto as admin_dto

BUTTON_BACK_TO_ADMIN: str = "🔙 پنل مدیریت"
BUTTON_CANCEL: str = "✖️ انصراف"


def build_admin_menu() -> InlineKeyboardMarkup:
    """The 🛡️ admin dashboard menu."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📊 داشبورد", callback_data=callbacks.ADM_DASH
                ),
                InlineKeyboardButton(
                    "👥 کاربران", callback_data=f"{callbacks.ADM_UL_PREFIX}0"
                ),
            ],
            [
                InlineKeyboardButton(
                    "💰 اقتصاد", callback_data=callbacks.ADM_ECON
                ),
                InlineKeyboardButton(
                    "🏠 املاک", callback_data=callbacks.ADM_ESTATE
                ),
            ],
            [
                InlineKeyboardButton(
                    "💼 شغل‌ها", callback_data=callbacks.ADM_JOBS
                ),
                InlineKeyboardButton(
                    "📈 معاملات", callback_data=callbacks.ADM_TRADE
                ),
            ],
            [
                InlineKeyboardButton(
                    "⚙️ تنظیمات", callback_data=callbacks.ADM_SETTINGS
                ),
                InlineKeyboardButton(
                    "🗄️ دیتابیس", callback_data=callbacks.ADM_DB
                ),
            ],
            [
                InlineKeyboardButton(
                    "📋 لاگ‌ها", callback_data=callbacks.ADM_LOGS
                ),
            ],
        ]
    )


def build_back_to_admin() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    BUTTON_BACK_TO_ADMIN, callback_data=callbacks.ADM_MENU
                )
            ]
        ]
    )


def build_input_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    BUTTON_CANCEL, callback_data=callbacks.ADM_IN_CANCEL
                )
            ]
        ]
    )


def _pager_row(
    prefix: str, page: admin_dto.Page, back_callback: str
) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    nav: list[InlineKeyboardButton] = []
    if page.has_prev:
        nav.append(
            InlineKeyboardButton("◀️ قبلی", callback_data=f"{prefix}{page.page - 1}")
        )
    if page.has_next:
        nav.append(
            InlineKeyboardButton("بعدی ▶️", callback_data=f"{prefix}{page.page + 1}")
        )
    if nav:
        rows.append(nav)
    rows.append(
        [InlineKeyboardButton(BUTTON_BACK_TO_ADMIN, callback_data=back_callback)]
    )
    return rows


# --- Dashboard / users ------------------------------------------------------------

def build_dashboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "👥 کاربران", callback_data=f"{callbacks.ADM_UL_PREFIX}0"
                ),
                InlineKeyboardButton(
                    "💰 اقتصاد", callback_data=callbacks.ADM_ECON
                ),
            ],
            [
                InlineKeyboardButton(
                    BUTTON_BACK_TO_ADMIN, callback_data=callbacks.ADM_MENU
                )
            ],
        ]
    )


def build_users_list(page: admin_dto.Page[admin_dto.AdminPlayerSummary]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for user in page.items:
        flag = " 🚫" if user.is_banned else ""
        rows.append(
            [
                InlineKeyboardButton(
                    f"👤 {user.display_name} (#{user.player_id}){flag}",
                    callback_data=f"{callbacks.ADM_U_PREFIX}{user.player_id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                "🔍 جست‌وجو", callback_data=f"{callbacks.ADM_IN_PREFIX}q"
            )
        ]
    )
    rows.extend(_pager_row(callbacks.ADM_UL_PREFIX, page, callbacks.ADM_MENU))
    return InlineKeyboardMarkup(rows)


def build_user_detail(user: admin_dto.AdminPlayerSummary) -> InlineKeyboardMarkup:
    pid = user.player_id
    ban_button = (
        InlineKeyboardButton(
            "✅ رفع مسدودیت", callback_data=f"{callbacks.ADM_UNBAN_PREFIX}{pid}"
        )
        if user.is_banned
        else InlineKeyboardButton(
            "🚫 مسدودسازی", callback_data=f"{callbacks.ADM_BAN_PREFIX}{pid}"
        )
    )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📜 تراکنش‌ها", callback_data=f"{callbacks.ADM_UTX_PREFIX}{pid}"
                ),
                InlineKeyboardButton(
                    "🏠 املاک", callback_data=f"{callbacks.ADM_UPROP_PREFIX}{pid}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "➕ پول", callback_data=f"{callbacks.ADM_IN_PREFIX}m+_{pid}"
                ),
                InlineKeyboardButton(
                    "➖ پول", callback_data=f"{callbacks.ADM_IN_PREFIX}m-_{pid}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "➕ XP", callback_data=f"{callbacks.ADM_IN_PREFIX}x+_{pid}"
                ),
                InlineKeyboardButton(
                    "➖ XP", callback_data=f"{callbacks.ADM_IN_PREFIX}x-_{pid}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "⭐ تغییر لول", callback_data=f"{callbacks.ADM_IN_PREFIX}lvl_{pid}"
                ),
                ban_button,
            ],
            [
                InlineKeyboardButton(
                    "👥 لیست کاربران",
                    callback_data=f"{callbacks.ADM_UL_PREFIX}0",
                ),
                InlineKeyboardButton(
                    BUTTON_BACK_TO_ADMIN, callback_data=callbacks.ADM_MENU
                ),
            ],
        ]
    )


def build_user_back(pid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "👤 بازگشت به پروفایل",
                    callback_data=f"{callbacks.ADM_U_PREFIX}{pid}",
                )
            ],
            [
                InlineKeyboardButton(
                    BUTTON_BACK_TO_ADMIN, callback_data=callbacks.ADM_MENU
                )
            ],
        ]
    )


def build_ban_confirm(pid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🚫 بله، مسدودش کن",
                    callback_data=f"{callbacks.ADM_BANOK_PREFIX}{pid}",
                )
            ],
            [
                InlineKeyboardButton(
                    "👤 بازگشت به پروفایل",
                    callback_data=f"{callbacks.ADM_U_PREFIX}{pid}",
                )
            ],
        ]
    )


# --- Economy ----------------------------------------------------------------------

def build_econ(overview: admin_dto.EconomyOverview) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for asset in overview.assets:
        rows.append(
            [
                InlineKeyboardButton(
                    f"💱 {asset.name}",
                    callback_data=f"{callbacks.ADM_ASSET_PREFIX}{asset.code}",
                )
            ]
        )
    for event in overview.live_events:
        rows.append(
            [
                InlineKeyboardButton(
                    f"⚡ {event.name} (×{event.multiplier:g})",
                    callback_data=f"{callbacks.ADM_EVENT_PREFIX}{event.id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                "🧭 شرایط بازار", callback_data=f"{callbacks.ADM_IN_PREFIX}mkt"
            ),
            InlineKeyboardButton(
                "📉 تورم", callback_data=f"{callbacks.ADM_IN_PREFIX}infl"
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                "⚡ رویداد جدید", callback_data=f"{callbacks.ADM_IN_PREFIX}ev"
            ),
            InlineKeyboardButton(
                "🚨 بحران!", callback_data=callbacks.ADM_CRISIS
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                BUTTON_BACK_TO_ADMIN, callback_data=callbacks.ADM_MENU
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_asset_detail(code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✏️ تغییر قیمت",
                    callback_data=f"{callbacks.ADM_IN_PREFIX}ap_{code}",
                )
            ],
            [
                InlineKeyboardButton(
                    "💰 بازگشت به اقتصاد", callback_data=callbacks.ADM_ECON
                )
            ],
        ]
    )


def build_event_detail(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⏹ پایان‌دادن",
                    callback_data=f"{callbacks.ADM_EVENT_END_PREFIX}{event_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    "💰 بازگشت به اقتصاد", callback_data=callbacks.ADM_ECON
                )
            ],
        ]
    )


def build_crisis_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🚨 بله، بحران رو فعال کن", callback_data=callbacks.ADM_CRISIS_OK
                )
            ],
            [
                InlineKeyboardButton(
                    "💰 بازگشت به اقتصاد", callback_data=callbacks.ADM_ECON
                )
            ],
        ]
    )


# --- Real estate ------------------------------------------------------------------

def build_estate() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🏠 همه خانه‌ها", callback_data=f"{callbacks.ADM_HL_PREFIX}0"
                ),
                InlineKeyboardButton(
                    "🌍 همه زمین‌ها", callback_data=f"{callbacks.ADM_NL_PREFIX}0"
                ),
            ],
            [
                InlineKeyboardButton(
                    "🏷️ آگهی‌های فعال", callback_data=f"{callbacks.ADM_LI_PREFIX}0"
                ),
                InlineKeyboardButton(
                    "📜 قراردادها", callback_data=f"{callbacks.ADM_C_PREFIX}0"
                ),
            ],
            [
                InlineKeyboardButton(
                    BUTTON_BACK_TO_ADMIN, callback_data=callbacks.ADM_MENU
                )
            ],
        ]
    )


def build_houses_list(page: admin_dto.Page[admin_dto.HouseAdminEntry]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for house in page.items:
        rows.append(
            [
                InlineKeyboardButton(
                    f"🏠 #{house.id} {house.city}، {house.neighborhood}",
                    callback_data=f"{callbacks.ADM_HD_PREFIX}{house.id}",
                )
            ]
        )
    rows.extend(_pager_row(callbacks.ADM_HL_PREFIX, page, callbacks.ADM_ESTATE))
    return InlineKeyboardMarkup(rows)


def build_house_detail(detail: admin_dto.HouseDetailAdmin) -> InlineKeyboardMarkup:
    hid = detail.house.id
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✏️ ویرایش مشخصات",
                    callback_data=f"{callbacks.ADM_HE_PREFIX}{hid}",
                )
            ],
            [
                InlineKeyboardButton(
                    "💹 ضریب قیمت",
                    callback_data=f"{callbacks.ADM_IN_PREFIX}ha_{hid}_ovr",
                )
            ],
            [
                InlineKeyboardButton(
                    "🏠 لیست خانه‌ها", callback_data=f"{callbacks.ADM_HL_PREFIX}0"
                ),
                InlineKeyboardButton(
                    BUTTON_BACK_TO_ADMIN, callback_data=callbacks.ADM_ESTATE
                ),
            ],
        ]
    )


_KITCHEN_OPTIONS = ("مدرن", "معمولی", "قدیمی")
_QUALITY_OPTIONS = ("عالی", "خوب", "متوسط", "ضعیف")


def build_house_edit(detail: admin_dto.HouseDetailAdmin) -> InlineKeyboardMarkup:
    hid = detail.house.id
    house = detail.house
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                "📐 متراژ", callback_data=f"{callbacks.ADM_IN_PREFIX}ha_{hid}_area"
            ),
            InlineKeyboardButton(
                "🛏️ خواب", callback_data=f"{callbacks.ADM_IN_PREFIX}ha_{hid}_bed"
            ),
            InlineKeyboardButton(
                "🛁 حمام", callback_data=f"{callbacks.ADM_IN_PREFIX}ha_{hid}_bath"
            ),
        ],
        [
            InlineKeyboardButton(
                "🛋️ نشیمن", callback_data=f"{callbacks.ADM_IN_PREFIX}ha_{hid}_liv"
            ),
            InlineKeyboardButton(
                "📅 سال ساخت", callback_data=f"{callbacks.ADM_IN_PREFIX}ha_{hid}_year"
            ),
            InlineKeyboardButton(
                "📍 لوکیشن", callback_data=f"{callbacks.ADM_IN_PREFIX}ha_{hid}_loc"
            ),
        ],
        [
            InlineKeyboardButton(
                f"🅿️ پارکینگ: {'✅' if house.parking else '❌'}",
                callback_data=f"{callbacks.ADM_HT_PREFIX}{hid}_p",
            ),
            InlineKeyboardButton(
                f"🛗 آسانسور: {'✅' if house.elevator else '❌'}",
                callback_data=f"{callbacks.ADM_HT_PREFIX}{hid}_e",
            ),
            InlineKeyboardButton(
                f"📦 انباری: {'✅' if house.storage else '❌'}",
                callback_data=f"{callbacks.ADM_HT_PREFIX}{hid}_s",
            ),
        ],
    ]
    kitchen_row = [
        InlineKeyboardButton(
            f"{'✅' if house.kitchen_type == option else ''}🍽️ {option}",
            callback_data=f"{callbacks.ADM_HK_PREFIX}{hid}_{index}",
        )
        for index, option in enumerate(_KITCHEN_OPTIONS)
    ]
    rows.append(kitchen_row)
    quality_row = [
        InlineKeyboardButton(
            f"{'✅' if house.quality == option else ''}{option}",
            callback_data=f"{callbacks.ADM_HQ_PREFIX}{hid}_{index}",
        )
        for index, option in enumerate(_QUALITY_OPTIONS)
    ]
    rows.append(quality_row)
    rows.append(
        [
            InlineKeyboardButton(
                "🏠 بازگشت به خانه",
                callback_data=f"{callbacks.ADM_HD_PREFIX}{hid}",
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_lands_list(page: admin_dto.Page[admin_dto.LandAdminEntry]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for land in page.items:
        rows.append(
            [
                InlineKeyboardButton(
                    f"🌍 #{land.id} {land.city}، {land.neighborhood}",
                    callback_data=f"{callbacks.ADM_ND_PREFIX}{land.id}",
                )
            ]
        )
    rows.extend(_pager_row(callbacks.ADM_NL_PREFIX, page, callbacks.ADM_ESTATE))
    return InlineKeyboardMarkup(rows)


def build_land_detail(detail: admin_dto.LandDetailAdmin) -> InlineKeyboardMarkup:
    lid = detail.land.id
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✏️ ویرایش مشخصات",
                    callback_data=f"{callbacks.ADM_NE_PREFIX}{lid}",
                )
            ],
            [
                InlineKeyboardButton(
                    "💹 ضریب قیمت",
                    callback_data=f"{callbacks.ADM_IN_PREFIX}la_{lid}_ovr",
                )
            ],
            [
                InlineKeyboardButton(
                    "🌍 لیست زمین‌ها", callback_data=f"{callbacks.ADM_NL_PREFIX}0"
                ),
                InlineKeyboardButton(
                    BUTTON_BACK_TO_ADMIN, callback_data=callbacks.ADM_ESTATE
                ),
            ],
        ]
    )


def build_land_edit(detail: admin_dto.LandDetailAdmin) -> InlineKeyboardMarkup:
    lid = detail.land.id
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📐 متراژ", callback_data=f"{callbacks.ADM_IN_PREFIX}la_{lid}_area"
                ),
                InlineKeyboardButton(
                    "📍 لوکیشن", callback_data=f"{callbacks.ADM_IN_PREFIX}la_{lid}_loc"
                ),
            ],
            [
                InlineKeyboardButton(
                    "🌍 بازگشت به زمین",
                    callback_data=f"{callbacks.ADM_ND_PREFIX}{lid}",
                )
            ],
        ]
    )


def build_listings(page: admin_dto.Page[admin_dto.ListingAdminEntry]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for listing in page.items:
        kind = "🏷️" if listing.listing_type == "sale" else "🔑"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{kind} #{listing.listing_id} {listing.house_label}",
                    callback_data=f"{callbacks.ADM_HD_PREFIX}{listing.house_id}",
                ),
                InlineKeyboardButton(
                    "❌ حذف",
                    callback_data=f"{callbacks.ADM_LICLOSE_PREFIX}{listing.listing_id}",
                ),
            ]
        )
    rows.extend(_pager_row(callbacks.ADM_LI_PREFIX, page, callbacks.ADM_ESTATE))
    return InlineKeyboardMarkup(rows)


def build_contracts(page: admin_dto.Page[admin_dto.ContractAdminEntry]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for contract in page.items:
        rows.append(
            [
                InlineKeyboardButton(
                    f"📜 #{contract.contract_id} {contract.house_label}",
                    callback_data=f"{callbacks.ADM_CD_PREFIX}{contract.contract_id}",
                )
            ]
        )
    rows.extend(_pager_row(callbacks.ADM_C_PREFIX, page, callbacks.ADM_ESTATE))
    return InlineKeyboardMarkup(rows)


def build_contract_detail(contract_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⏹ فسخ قرارداد",
                    callback_data=f"{callbacks.ADM_CTERM_PREFIX}{contract_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    "📜 لیست قراردادها", callback_data=f"{callbacks.ADM_C_PREFIX}0"
                )
            ],
        ]
    )


# --- Jobs -------------------------------------------------------------------------

def build_jobs(entries: list[admin_dto.JobAdminEntry]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for job in entries:
        state = "✅" if job.is_active else "❌"
        rows.append(
            [
                InlineKeyboardButton(
                    f"💼 {job.name} {state}",
                    callback_data=f"{callbacks.ADM_JOB_PREFIX}{job.id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                "➕ شغل جدید", callback_data=f"{callbacks.ADM_IN_PREFIX}ja"
            ),
            InlineKeyboardButton(
                "👷 کارگران", callback_data=f"{callbacks.ADM_W_PREFIX}0"
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                BUTTON_BACK_TO_ADMIN, callback_data=callbacks.ADM_MENU
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_job_detail(job: admin_dto.JobAdminEntry) -> InlineKeyboardMarkup:
    jid = job.id
    toggle = "❌ غیرفعال‌سازی" if job.is_active else "✅ فعال‌سازی"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "💰 حقوق", callback_data=f"{callbacks.ADM_IN_PREFIX}js_{jid}"
                ),
                InlineKeyboardButton(
                    "⭐ لول", callback_data=f"{callbacks.ADM_IN_PREFIX}jl_{jid}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "⏳ کول‌داون", callback_data=f"{callbacks.ADM_IN_PREFIX}jc_{jid}"
                ),
                InlineKeyboardButton(
                    "🏢 صاحبکار", callback_data=f"{callbacks.ADM_IN_PREFIX}je_{jid}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "📝 توضیح", callback_data=f"{callbacks.ADM_IN_PREFIX}jd_{jid}"
                ),
                InlineKeyboardButton(
                    toggle, callback_data=f"{callbacks.ADM_JOB_TOGGLE_PREFIX}{jid}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "💼 لیست شغل‌ها", callback_data=callbacks.ADM_JOBS
                )
            ],
        ]
    )


def build_workers(page: admin_dto.Page[admin_dto.WorkerEntry]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for worker in page.items:
        rows.append(
            [
                InlineKeyboardButton(
                    f"👷 {worker.display_name}",
                    callback_data=f"{callbacks.ADM_U_PREFIX}{worker.player_id}",
                )
            ]
        )
    rows.extend(_pager_row(callbacks.ADM_W_PREFIX, page, callbacks.ADM_JOBS))
    return InlineKeyboardMarkup(rows)


# --- Trading ----------------------------------------------------------------------

def build_trade() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ فروش‌ها", callback_data=f"{callbacks.ADM_TS_PREFIX}0"
                ),
                InlineKeyboardButton(
                    "⚡ فعالیت بازار", callback_data=callbacks.ADM_TA
                ),
            ],
            [
                InlineKeyboardButton(
                    "🏷️ آگهی‌های فعال", callback_data=f"{callbacks.ADM_LI_PREFIX}0"
                ),
                InlineKeyboardButton(
                    "🧭 پارامترهای بازار", callback_data=callbacks.ADM_ECON
                ),
            ],
            [
                InlineKeyboardButton(
                    BUTTON_BACK_TO_ADMIN, callback_data=callbacks.ADM_MENU
                )
            ],
        ]
    )


def build_sales(page: admin_dto.Page[admin_dto.SaleAdminEntry]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        _pager_row(callbacks.ADM_TS_PREFIX, page, callbacks.ADM_TRADE)
    )


# --- Settings ---------------------------------------------------------------------

def build_settings(overview: admin_dto.SettingsOverview) -> InlineKeyboardMarkup:
    def flag_button(name: str, label: str, on: bool) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            f"{label}: {'✅' if on else '❌'}",
            callback_data=f"{callbacks.ADM_TG_PREFIX}{name}",
        )

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🧭 شرایط بازار", callback_data=f"{callbacks.ADM_IN_PREFIX}mkt"
                ),
                InlineKeyboardButton(
                    "📉 تورم", callback_data=f"{callbacks.ADM_IN_PREFIX}infl"
                ),
            ],
            [
                InlineKeyboardButton(
                    "🎁 مقسوم خرید", callback_data=f"{callbacks.ADM_IN_PREFIX}rw_pxd"
                ),
                InlineKeyboardButton(
                    "🎁 مقسوم ساخت", callback_data=f"{callbacks.ADM_IN_PREFIX}rw_cxd"
                ),
            ],
            [
                InlineKeyboardButton(
                    "🎁 کف XP", callback_data=f"{callbacks.ADM_IN_PREFIX}rw_pxn"
                ),
                InlineKeyboardButton(
                    "🎁 سقف XP", callback_data=f"{callbacks.ADM_IN_PREFIX}rw_pxx"
                ),
            ],
            [
                InlineKeyboardButton(
                    "⏳ حداقل کار", callback_data=f"{callbacks.ADM_IN_PREFIX}mwm"
                ),
            ],
            [
                flag_button("jobs", "شغل‌ها", overview.jobs_enabled),
                flag_button("housing", "مسکن", overview.housing_enabled),
            ],
            [
                flag_button("realestate", "زمین و ساخت", overview.realestate_enabled),
            ],
            [
                InlineKeyboardButton(
                    BUTTON_BACK_TO_ADMIN, callback_data=callbacks.ADM_MENU
                )
            ],
        ]
    )


# --- Database ---------------------------------------------------------------------

def build_db() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📊 آمار", callback_data=callbacks.ADM_DB_STATS
                ),
                InlineKeyboardButton(
                    "💾 بکاپ‌گیری", callback_data=callbacks.ADM_DB_BACKUP
                ),
            ],
            [
                InlineKeyboardButton(
                    "♻️ بازیابی", callback_data=callbacks.ADM_DB_BACKUPS
                ),
                InlineKeyboardButton(
                    "🧹 پاک‌سازی", callback_data=callbacks.ADM_DB_CLEAN
                ),
            ],
            [
                InlineKeyboardButton(
                    BUTTON_BACK_TO_ADMIN, callback_data=callbacks.ADM_MENU
                )
            ],
        ]
    )


def build_db_back(back: str = ...) -> InlineKeyboardMarkup:
    target = back if back is not ... else callbacks.ADM_DB
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🗄️ ابزارهای دیتابیس", callback_data=target
                )
            ]
        ]
    )


def build_backups(backups: list[admin_dto.BackupInfo]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for info in backups[:10]:
        rows.append(
            [
                InlineKeyboardButton(
                    f"♻️ {info.filename}",
                    callback_data=f"{callbacks.ADM_DB_RESTORE_PREFIX}{info.filename}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                "🗄️ ابزارهای دیتابیس", callback_data=callbacks.ADM_DB
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_restore_confirm(filename: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⚠️ بله، بازیابی کن",
                    callback_data=f"{callbacks.ADM_DB_RESTORE_OK_PREFIX}{filename}",
                )
            ],
            [
                InlineKeyboardButton(
                    "💾 لیست بکاپ‌ها", callback_data=callbacks.ADM_DB_BACKUPS
                )
            ],
        ]
    )


def build_clean() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🏷️ آگهی‌های بسته",
                    callback_data=f"{callbacks.ADM_IN_PREFIX}purge_listings",
                )
            ],
            [
                InlineKeyboardButton(
                    "📋 لاگ‌های قدیمی",
                    callback_data=f"{callbacks.ADM_IN_PREFIX}purge_audit",
                )
            ],
            [
                InlineKeyboardButton(
                    "💱 تاریخچه قیمت‌ها",
                    callback_data=f"{callbacks.ADM_IN_PREFIX}purge_ticks",
                )
            ],
            [
                InlineKeyboardButton(
                    "🗄️ ابزارهای دیتابیس", callback_data=callbacks.ADM_DB
                )
            ],
        ]
    )


# --- Logs -------------------------------------------------------------------------

_LOG_CATEGORIES = (
    ("admin", "🛡️ همه اقدامات"),
    ("user_", "👥 کاربران"),
    ("econ", "💰 اقتصاد"),
    ("house", "🏠 ملک"),
    ("job", "💼 شغل‌ها"),
)


def build_logs() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for code, label in _LOG_CATEGORIES:
        rows.append(
            [
                InlineKeyboardButton(
                    label,
                    callback_data=f"{callbacks.ADM_LOG_PREFIX}{code}_0",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                "\U0001f30d زمین", callback_data=f"{callbacks.ADM_LOG_PREFIX}land_0"
            ),
            InlineKeyboardButton(
                "\U0001f5c4️ دیتابیس", callback_data=f"{callbacks.ADM_LOG_PREFIX}db__0"
            ),
        ]
    )
    # Economy changes span several prefixes — one dedicated view each.
    rows.append(
        [
            InlineKeyboardButton(
                "⚡ رویدادها", callback_data=f"{callbacks.ADM_LOG_PREFIX}event_0"
            ),
            InlineKeyboardButton(
                "💱 دارایی‌ها", callback_data=f"{callbacks.ADM_LOG_PREFIX}asset_0"
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                "💸 تراکنش‌های کاربران", callback_data=callbacks.ADM_TA
            ),
            InlineKeyboardButton(
                "⚠️ خطاها", callback_data=f"{callbacks.ADM_LOG_PREFIX}errors_0"
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                BUTTON_BACK_TO_ADMIN, callback_data=callbacks.ADM_MENU
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_audit_list(
    prefix: str, page: admin_dto.Page[admin_dto.AdminAuditEntry]
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        _pager_row(prefix, page, callbacks.ADM_LOGS)
    )


LOG_TITLES: dict[str, str] = {
    "admin": "🛡️ همه اقدامات ادمین",
    "user_": "👥 اقدامات کاربران",
    "econ": "💰 تغییرات اقتصاد",
    "house": "🏠 تغییرات ملک",
    "land": "🌍 تغییرات زمین",
    "job": "💼 تغییرات شغل‌ها",
    "event": "⚡ رویدادها",
    "asset": "💱 دارایی‌ها",
    "db_": "🗄️ دیتابیس",
}
