"""Global game constants.

Starting values and tunable progression settings live here so the game design
can be adjusted in a single place without touching any logic.
"""

# --- New player starting values --------------------------------------------
STARTING_LEVEL: int = 1
STARTING_XP: int = 0
STARTING_MONEY: int = 0

# --- Money ------------------------------------------------------------------
# Money is stored as an exact integer amount of Toman. Floats are never used.
CURRENCY_NAME: str = "تومان"

# --- XP / Level progression -------------------------------------------------
# XP required to advance from level L to L+1:
#     xp_for_level_up(L) = XP_BASE_PER_LEVEL * XP_GROWTH_PER_LEVEL ** (L - 1)
# Tune these two values to reshape the whole curve — nothing else changes.
XP_BASE_PER_LEVEL: int = 100
XP_GROWTH_PER_LEVEL: float = 1.35

# --- Input limits -------------------------------------------------------------
MAX_DISPLAY_NAME_LENGTH: int = 64
MAX_USERNAME_LENGTH: int = 32
MAX_XP_REASON_LENGTH: int = 128

# --- Job system: «خر حمالی» --------------------------------------------------
# Player-facing name of the whole job/income system. Every menu, button and
# message reads it from here, so renaming the system stays a one-line change.
JOBS_SYSTEM_NAME: str = "خر حمالی"

# Text commands that open the system. The previous name («مشاغل» / «شغل من»)
# stays accepted so players who already know the bot are not stranded by the
# rename.
JOBS_TEXT_TRIGGER: str = JOBS_SYSTEM_NAME
JOBS_TEXT_TRIGGER_LEGACY: str = "مشاغل"
MY_JOB_TEXT_TRIGGER: str = "کار من"
MY_JOB_TEXT_TRIGGER_LEGACY: str = "شغل من"
LEAVE_JOB_TEXT_TRIGGER: str = "ترک کار"
APPLY_JOB_TEXT_TRIGGER: str = "استخدام"

# Jobs that used to be selectable. They are *deactivated*, never deleted, on
# the next boot — so earnings history and anyone still working there survive.
# The mapping is also what a legacy row is backfilled from: a player who was
# already working one of these jobs must keep being paid at the rate they were
# hired for, even on a database that predates ``hourly_salary``.
JOB_LEGACY_COMPAT: dict[str, tuple[int, str]] = {
    "کارگر": (60_000, "کارگاه حاج رضا"),
    "کارمند": (120_000, "شرکت بازرگانی آریا"),
    "متخصص": (240_000, "هلدینگ فناوری پارس"),
}
JOB_LEGACY_RETIRED_NAMES: tuple[str, ...] = tuple(JOB_LEGACY_COMPAT)

# Initial jobs — stored in DB, values here are used for seeding.
# ``salary`` is the legacy per-action field and simply mirrors the hourly rate,
# so the two can never disagree on screen.

JOB_MASON_NAME: str = "بنایی"
JOB_MASON_DESCRIPTION: str = "کار ساختمانی؛ آجر، سیمان و بتن"
JOB_MASON_SALARY: int = 80_000
JOB_MASON_COOLDOWN: int = 5 * 60  # 5 minutes
JOB_MASON_REQUIRED_LEVEL: int = 1
JOB_MASON_HOURLY_SALARY: int = 80_000  # Toman per hour
JOB_MASON_EMPLOYER: str = "شرکت ساختمانی البرز"

JOB_RESTAURANT_NAME: str = "رستوران"
JOB_RESTAURANT_DESCRIPTION: str = "کار در آشپزخانه و سالن رستوران"
JOB_RESTAURANT_SALARY: int = 70_000
JOB_RESTAURANT_COOLDOWN: int = 5 * 60  # 5 minutes
JOB_RESTAURANT_REQUIRED_LEVEL: int = 1
JOB_RESTAURANT_HOURLY_SALARY: int = 70_000  # Toman per hour
JOB_RESTAURANT_EMPLOYER: str = "رستوران آرمان"

JOB_SALES_NAME: str = "فروشندگی"
JOB_SALES_DESCRIPTION: str = "فروش حضوری در مغازه و پاساژ"
JOB_SALES_SALARY: int = 90_000
JOB_SALES_COOLDOWN: int = 10 * 60  # 10 minutes
JOB_SALES_REQUIRED_LEVEL: int = 2
JOB_SALES_HOURLY_SALARY: int = 90_000  # Toman per hour
JOB_SALES_EMPLOYER: str = "مجموعه فروشگاه‌های آرمان"

JOB_COURIER_NAME: str = "پیک موتوری"
JOB_COURIER_DESCRIPTION: str = "رساندن بسته‌ها با موتور در شهر"
JOB_COURIER_SALARY: int = 120_000
JOB_COURIER_COOLDOWN: int = 15 * 60  # 15 minutes
JOB_COURIER_REQUIRED_LEVEL: int = 3
JOB_COURIER_HOURLY_SALARY: int = 120_000  # Toman per hour
JOB_COURIER_EMPLOYER: str = "شرکت ارسال سریع پارس"

JOB_SNAPP_NAME: str = "اسنپ"
JOB_SNAPP_DESCRIPTION: str = "تاکسی اینترنتی؛ هر مسافر یک سرویس"
JOB_SNAPP_SALARY: int = 160_000
JOB_SNAPP_COOLDOWN: int = 20 * 60  # 20 minutes
JOB_SNAPP_REQUIRED_LEVEL: int = 5
JOB_SNAPP_HOURLY_SALARY: int = 160_000  # Toman per hour
JOB_SNAPP_EMPLOYER: str = "ناوگان اسنپ"

JOB_BANK_CLERK_NAME: str = "کارمند بانک"
JOB_BANK_CLERK_DESCRIPTION: str = "کار اداری در بانک؛ پردرآمدترین شغل شهر"
JOB_BANK_CLERK_SALARY: int = 220_000
JOB_BANK_CLERK_COOLDOWN: int = 30 * 60  # 30 minutes
JOB_BANK_CLERK_REQUIRED_LEVEL: int = 8
JOB_BANK_CLERK_HOURLY_SALARY: int = 220_000  # Toman per hour
JOB_BANK_CLERK_EMPLOYER: str = "بانک پارسیان"

# --- Business System --------------------------------------------------------
# Player-owned businesses are selected from the predefined catalog in
# ``app/game/business/catalog.py``. This cap is deliberately configurable so
# the economy can be rebalanced without changing service logic.
BUSINESS_MAX_PER_PLAYER: int = 3
BUSINESS_TEXT_TRIGGER: str = "کسب‌وکار"
BUSINESS_TEXT_TRIGGER_ALIASES: tuple[str, ...] = (
    BUSINESS_TEXT_TRIGGER,
    "کسب و کار",
)

# --- Time-based salary settlement -------------------------------------------
# A settlement is only possible after at least this many whole minutes of work.
MIN_WORK_MINUTES_FOR_SETTLEMENT: int = 1

# Employer behaviour: probability of each random event during settlement.
EMPLOYER_EVENT_DELAY_PROBABILITY: float = 0.20
EMPLOYER_EVENT_MISTAKE_PROBABILITY: float = 0.20
EMPLOYER_EVENT_BONUS_PROBABILITY: float = 0.20
# (The remaining probability — 0.40 — is a normal payment.)

# Mistake penalty: random percentage of the earned salary (inclusive range).
MISTAKE_PENALTY_MIN_PERCENT: int = 10
MISTAKE_PENALTY_MAX_PERCENT: int = 50

# Bonus payment: random percentage added on top of the earned salary.
BONUS_MIN_PERCENT: int = 10
BONUS_MAX_PERCENT: int = 30

# --- Admin ------------------------------------------------------------------
# Canonical admin Telegram user IDs. These are the fallback when the ADMIN_IDS
# environment variable is empty, so the panel owner never gets locked out.
# Real IDs can be extended via the ADMIN_IDS env var (comma-separated).
ADMIN_TELEGRAM_IDS: tuple[int, ...] = (8154313073,)

# Default admin IDs placeholder — real IDs come from env var ADMIN_IDS
DEFAULT_ADMIN_IDS: list[int] = []

# --- Housing / Real-estate system -------------------------------------------
# Rental period: one "month" of a contract, in days.
HOUSING_RENT_PERIOD_DAYS: int = 30

# Sale-listing bounds: a player's asking price must stay within these
# multiples of the dynamic market value (prevents absurd markets).
HOUSING_SALE_MIN_PER_MILLE: int = 300     # 30% of market value
HOUSING_SALE_MAX_PER_MILLE: int = 3000    # 300% of market value

# Button presets for sale prices (per-mille of the dynamic market value).
HOUSING_SALE_PRICE_PRESETS_PER_MILLE: tuple[int, ...] = (850, 1000, 1150, 1300)

# Rent-listing bounds (relative to the dynamic market value).
HOUSING_RENT_MIN_PER_MILLE: int = 1       # >= 0.1% of value per month
HOUSING_RENT_MAX_PER_MILLE: int = 20      # <= 2% of value per month
HOUSING_DEPOSIT_MAX_PER_MILLE: int = 500  # deposit <= 50% of value

# Deposit presets when renting a house out: (deposit_percent of value,).
HOUSING_DEPOSIT_PRESET_PERCENTS: tuple[int, ...] = (0, 10, 20)

# XP reward for buying a house: xp = price / divisor, clamped to [min, max].
HOUSING_PURCHASE_XP_DIVISOR: int = 20_000_000
HOUSING_PURCHASE_XP_MIN: int = 5
HOUSING_PURCHASE_XP_MAX: int = 300
HOUSING_PURCHASE_XP_REASON: str = "خرید خانه"

# Number of system-market houses seeded on first boot (spread over the
# catalog cities with varied specs).
HOUSING_SEED_COUNT: int = 30

# --- Land / Construction / Renovation ----------------------------------------
# The single economy knob for the whole real-estate market: land prices,
# construction costs and renovation costs are all multiplied by it. The future
# Economy/Inflation system just moves this value (or passes an explicit
# ``market_factor``) and every price in the game reacts — nothing is fixed.
ECONOMY_MARKET_CONDITIONS: float = 1.0

# Ownerless lands seeded on first boot (system land market).
REALESTATE_SEED_LAND_COUNT: int = 24

# XP reward for completing a construction: xp = cost / divisor, clamped to
# the same [min, max] band as house purchases.
CONSTRUCTION_XP_DIVISOR: int = 30_000_000
CONSTRUCTION_XP_REASON: str = "تکمیل ساخت ملک"

# Cancelling an in-progress construction refunds this share of the paid cost
# (the rest is wasted materials/permits).
CONSTRUCTION_CANCEL_REFUND_PERCENT: int = 70

# ============================================================================
# 🏦 بانک ایران — separate exact-integer player bank ledger
# ============================================================================
BANK_SYSTEM_NAME: str = "بانک ایران"
BANK_TEXT_TRIGGER_ALIASES: tuple[str, ...] = (
    BANK_SYSTEM_NAME,
    "بانک",
)
BANK_INTEREST_RATE_PERCENT: int = 3
BANK_INTEREST_CHECK_SECONDS: int = 60 * 60
BANK_HISTORY_PAGE_SIZE: int = 6

# ============================================================================
# 📈 بازار ایران — shared market-price system
# ============================================================================
# The player-facing market contains exactly USD, 18k gold, Emami coin and a
# housing reference. USD/gold/coin are fetched from the real Iranian source
# configured in the provider layer; no price movement is simulated here.
IRAN_MARKET_SYSTEM_NAME: str = "بازار ایران"
IRAN_MARKET_TEXT_TRIGGER_ALIASES: tuple[str, ...] = (
    IRAN_MARKET_SYSTEM_NAME,
    "بازار",
)
IRAN_MARKET_UPDATE_INTERVAL_SECONDS: int = 3 * 24 * 60 * 60
IRAN_MARKET_SCHEDULER_CHECK_SECONDS: int = 60
IRAN_MARKET_INITIAL_RETRY_SECONDS: int = 60 * 60
IRAN_MARKET_FAILURE_RETRY_SECONDS: int = 60 * 60
IRAN_MARKET_UPDATE_LOCK_SECONDS: int = 15 * 60
IRAN_MARKET_API_TIMEOUT_SECONDS: float = 12.0
IRAN_MARKET_API_RETRY_ATTEMPTS: int = 3
IRAN_MARKET_API_RETRY_BACKOFF_SECONDS: float = 1.5
IRAN_MARKET_PROVIDER_BASE_URL: str = "https://www.tgju.org/profile"
IRAN_MARKET_PROVIDER_NAME: str = "tgju.org"
IRAN_MARKET_PROVIDER_USER_AGENT: str = "LIR-Iran-Market/1.0"
IRAN_MARKET_PROVIDER_API_KEY_ENV: str = "IRAN_MARKET_API_KEY"
IRAN_MARKET_RIALS_PER_TOMAN: int = 10
# Startup and housing knobs are read by IranMarketService at runtime. Keeping
# the names here avoids scattering environment-variable strings across layers.
IRAN_MARKET_INITIAL_FETCH_ENV: str = "IRAN_MARKET_INITIAL_FETCH_ENABLED"
IRAN_MARKET_HOUSING_CITY_ENV: str = "IRAN_MARKET_HOUSING_REFERENCE_CITY"
IRAN_MARKET_HOUSING_PRICE_ENV: str = "IRAN_MARKET_HOUSING_REFERENCE_PRICE_PER_SQM"
IRAN_MARKET_INITIAL_FETCH_ENABLED: bool = True
IRAN_MARKET_HOUSING_REFERENCE_CITY: str = "تهران"

# ============================================================================
# 🧱 دیوار ایران — player-to-player marketplace
# ============================================================================
DIVAR_SYSTEM_NAME: str = "دیوار ایران"
DIVAR_TEXT_TRIGGER_ALIASES: tuple[str, ...] = (DIVAR_SYSTEM_NAME, "دیوار")
DIVAR_PAGE_SIZE: int = 5
DIVAR_MAX_SEARCH_STATE_COUNT: int = 24

# ============================================================================
# 🚗 نمایشگاه ماشین حاج ممد — predefined vehicle dealership
# ============================================================================
VEHICLE_DEALERSHIP_NAME: str = "نمایشگاه ماشین حاج ممد"
VEHICLE_TEXT_TRIGGER_ALIASES: tuple[str, ...] = (
    VEHICLE_DEALERSHIP_NAME,
    "نمایشگاه ماشین",
)
VEHICLE_PAGE_SIZE: int = 6
# None deliberately means no invented gameplay cap until the project defines one.
VEHICLE_OWNERSHIP_LIMIT: int | None = None

# ============================================================================
# 🕳️ خلاف — fictional activity menu
# ============================================================================
CRIME_TEXT_TRIGGER_ALIASES: tuple[str, ...] = ("خلاف", "🕳️ خلاف")

# ============================================================================
# Marriage and Family system
# ============================================================================
# Every family rule lives here so the whole system can be re-balanced from one
# place — exactly like the housing/real-estate sections above. The family
# system is command-driven only (no menus, no buttons): «ازدواج», «قبول»,
# «رد», «لغو», «طلاق», «خیانت», «رابطه», «خانواده», «فرزندان».

# --- Marriage prerequisites ------------------------------------------------
MARRIAGE_MIN_LEVEL: int = 3
MARRIAGE_MIN_MONEY: int = 2_000_000      # wallet needed before proposing

# A pending request waits this long before it expires (hours).
MARRIAGE_REQUEST_EXPIRY_HOURS: int = 24
# One player may only have this many *outgoing* pending requests at a time.
MARRIAGE_MAX_PENDING_REQUESTS: int = 1

# --- Mahriyeh (مهریه) -------------------------------------------------------
# Mahriyeh is stored on the marriage row at the moment of the wedding and is
# paid by whoever initiates «طلاق» to the other spouse — it is the price of
# leaving the marriage, not a wedding gift.
MARRIYEH_BASE: int = 1_000_000           # fixed floor, in Toman
MARRIYEH_PER_LEVEL: int = 250_000        # × the payer's level
MARRIYEH_WEALTH_DIVISOR: int = 10        # + payer's money / this
MARRIYEH_MAX: int = 2_000_000_000        # hard ceiling

# --- Relationship quality ---------------------------------------------------
RELATIONSHIP_QUALITY_START: int = 70
RELATIONSHIP_QUALITY_MAX: int = 100
RELATIONSHIP_QUALITY_MIN: int = 0
RELATIONSHIP_TIME_QUALITY_BOOST: int = 3     # for a successful «رابطه»
CHEATING_SUCCESS_QUALITY_PENALTY: int = 10    # cheating, not discovered
CHEATING_DISCOVERED_QUALITY_PENALTY: int = 25  # cheating, discovered

# --- Cheating (خیانت) -------------------------------------------------------
# The attempt is always rolled; being *discovered* is the only thing that
# produces consequences, and discovery never depends on the target player.
CHEATING_SUCCESS_CHANCE: float = 0.65
CHEATING_DISCOVERY_CHANCE: float = 0.35
# Escalating consequences, one entry per discovery:
#   (money fine, quality penalty, forced_divorce)
CHEATING_CONSEQUENCES: tuple[tuple[int, int, bool], ...] = (
    (1_000_000, 25, False),     # 1st discovery — shame, and it costs money
    (5_000_000, 40, False),     # 2nd discovery — a much bigger price
    (10_000_000, 100, True),    # 3rd discovery — the marriage ends, forced
)
# Divorce becomes free for the wronged spouse from this many discoveries on.
CHEATING_WAIVER_STRIKES: int = 1

# --- Pregnancy / children ---------------------------------------------------
RELATIONSHIP_PREGNANCY_BASE_CHANCE: float = 0.15
# Pregnancy odds scale with how good the relationship is:
#   chance = base × PREGNANCY_QUALITY_FACTOR_AT_100 scaled to quality/100
PREGNANCY_QUALITY_FACTOR_AT_100: float = 1.6
# A conceived child is born this many days later (settled lazily, like
# constructions and renovations).
PREGNANCY_DURATION_DAYS: int = 7
MAX_CHILDREN_PER_MARRIAGE: int = 5

# --- XP (granted explicitly through LevelService, never implicitly) ---------
MARRIAGE_XP: int = 60
MARRIAGE_XP_REASON: str = "ازدواج"
RELATIONSHIP_XP: int = 10
RELATIONSHIP_XP_REASON: str = "رابطه خانوادگی"
BIRTH_XP: int = 100
BIRTH_XP_REASON: str = "به‌دنیا آمدن فرزند"

# --- Command triggers (text only — the family system has no menu/buttons) ---
MARRIAGE_TRIGGER: str = "ازدواج"
MARRIAGE_ACCEPT_TRIGGER: str = "قبول"
MARRIAGE_REJECT_TRIGGER: str = "رد"
MARRIAGE_CANCEL_TRIGGER: str = "لغو ازدواج"
DIVORCE_TRIGGER: str = "طلاق"
CHEATING_TRIGGER: str = "خیانت"
RELATIONSHIP_TRIGGER: str = "رابطه"
FAMILY_TRIGGER: str = "خانواده"
CHILDREN_TRIGGER: str = "فرزندان"
FAMILY_HISTORY_TRIGGER: str = "تاریخچه خانواده"
FAMILY_HELP_TRIGGER: str = "راهنمای خانواده"
