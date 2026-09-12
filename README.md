# Iran Life Bot 🇮🇷

A multiplayer **life-simulation game** running as a **Telegram Bot**, inspired
by real life in Iran — casual, humorous and friendly. This repository contains
the clean, scalable foundation plus the **Job and Income System**, the
**Business System**, the **Housing and Real-Estate System**, the **Land,
Construction and Renovation System**, the read-only **📈 بازار ایران** market,
and the **Admin Panel**: players, main menu, profile, status, level/XP, wallet,
a time-based salary job system, a predefined business catalog with owned
balances and daily income, a full housing market with dynamic prices, land
trading, time-based construction and renovations that raise property value,
real TGJU-backed USD/gold/coin quotes with a restart-safe three-day scheduler,
and a button-driven admin console to run the game. Future systems (education,
vehicles, ...) will be built on top of this base step by step.

## Tech Stack

| Component   | Choice                                        |
|-------------|-----------------------------------------------|
| Language    | Python 3.10+ (developed and tested on 3.13)   |
| Bot framework | [python-telegram-bot](https://docs.python-telegram-bot.org) v22 (fully async) |
| Database    | SQLite via `aiosqlite` (async)                |
| ORM         | SQLAlchemy 2.0 (async, ORM-enabled updates)   |
| Config      | `python-dotenv` + environment variables       |
| Tests       | `pytest` + `pytest-asyncio`                   |

> **PostgreSQL-ready:** the database layer is URL-driven. Switching to
> PostgreSQL later only means changing `DATABASE_URL`
> (e.g. `postgresql+asyncpg://user:pass@host/db`) — no game code changes.

## Requirements

- Python **3.10 or newer**
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

## Installation

### 1. Clone and enter the project

```bash
cd iran_life_bot
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows (PowerShell: .venv\Scripts\Activate.ps1)
```

### 3. Install dependencies

```bash
pip install -r requirements-dev.txt   # runtime + test dependencies
# or: pip install -r requirements.txt  (runtime only)
```

### 4. Configure `.env`

```bash
cp .env.example .env
```

Then edit `.env` and set your real token:

```env
BOT_TOKEN=123456789:AA...your_real_token...
```

Never commit `.env` (it is already git-ignored). The bot **fails fast with a
clear message** if `BOT_TOKEN` is missing.

## 📈 بازار ایران

The player-facing Iranian market contains exactly four stored assets: **USD**,
**18-karat gold**, **Emami coin**, and a **Tehran housing reference price per
square metre**. Opening the market only reads the stored snapshot; it never
calls TGJU or changes a price. USD, gold, and coin are fetched independently
from the replaceable provider layer (`Service → Provider → external source`).
The default provider reads the validated TGJU profile pages, normalizes their
Rial values to whole Toman, and rejects incomplete or non-positive batches.
Network or parsing failures preserve the last valid prices.

A persisted scheduler updates the three external quotes every three days. Its
lease and cursor survive restarts and prevent concurrent workers from allowing
an older response to overwrite a newer cycle. The housing reference is seeded
from the existing housing catalog and never mutates individual property rows.

Provider, scheduler, initialization, and housing settings can be overridden
through environment variables (secrets are never logged):

```env
IRAN_MARKET_PROVIDER_BASE_URL=https://www.tgju.org/profile
IRAN_MARKET_API_KEY=                 # optional gateway credential
IRAN_MARKET_API_TIMEOUT_SECONDS=12
IRAN_MARKET_API_RETRY_ATTEMPTS=3
IRAN_MARKET_API_RETRY_BACKOFF_SECONDS=1.5
IRAN_MARKET_UPDATE_INTERVAL_SECONDS=259200
IRAN_MARKET_SCHEDULER_CHECK_SECONDS=60
IRAN_MARKET_INITIAL_RETRY_SECONDS=3600
IRAN_MARKET_FAILURE_RETRY_SECONDS=3600
IRAN_MARKET_UPDATE_LOCK_SECONDS=900
IRAN_MARKET_INITIAL_FETCH_ENABLED=true
IRAN_MARKET_HOUSING_REFERENCE_CITY=تهران
# optional fixed override; otherwise the selected catalog city's reference is used
IRAN_MARKET_HOUSING_REFERENCE_PRICE_PER_SQM=
```

The tables `iran_market_assets`, `iran_market_price_history`, and
`iran_market_update_state` are additive and are created by the existing
startup `create_all` path. Legacy Admin Economy tables (`market_assets` and
`market_price_ticks`) are intentionally untouched and remain separate.

## Database

- **Automatic:** the bot creates any missing tables on every startup
  (`post_init` hook). Existing tables and rows are never dropped or altered,
  so player data survives restarts.
- **Manual:** you can also initialize it yourself:

```bash
python scripts/init_db.py
```

The SQLite file lives at `data/iran_life_bot.db` by default (configurable via
`DATABASE_URL`).

## Running the Bot

```bash
python main.py
```

Stop it with `Ctrl+C` (a graceful shutdown log line is printed).

## Running the Tests

```bash
pytest
```

The suite covers registration, duplicate prevention (including concurrent
`/start`), starting values, level/XP progression, the money service, profile
and status retrieval, DB persistence across restarts, keyboard/menu shape,
handler flows, config guards, log-secret redaction, the time-based salary
job system (settlement, employer behaviour, penalties, bonuses and delayed
payments), the additive column migration, the **complete Housing system**
(dynamic pricing, market buying, player-to-player selling and renting,
rental contracts, rent payments, money-transfer atomicity, assets, schema
upgrade of old databases) and the **complete Land, Construction and
Renovation system** (dynamic land pricing, buying land, the full
button-driven construction wizard, progress and completion, house creation,
renovation options and value increases, cancellations with refunds, the
economy knob and schema upgrades), the **complete Admin Panel** (auth guard,
ban enforcement, Persian-number parsing, dashboard, users, economy, real
estate, jobs, trading, settings, database tools and logs — **113 tests**),
and the **complete Marriage and Family system** (marriage requests with
accept/reject, the already-married restrictions, Mahriyeh computation and
payment through the wallet, unaffordable-divorce blocking, the divorce waiver
for a wronged spouse, hidden cheating with escalating consequences and forced
divorce, relationship events with quality-scaled pregnancy odds, lazy birth
settlement, children, family history and profile integration) —
**458 tests**, including focused provider, scheduling, restart, failure-
preservation, stale-response and four-asset market coverage.

## Basic Project Structure

```
iran_life_bot/
├── app/
│   ├── bot/                     # Telegram layer (and nothing else)
│   │   ├── handlers/            #   start, jobs, business, Iran market, housing, land/construction, admin panel, family, error handler
│   │   ├── keyboards/           #   inline keyboard builders + callback ids
│   │   ├── messages/            #   ALL player-facing Persian texts
│   │   ├── middleware/          #   cross-cutting update processing
│   │   └── context.py           #   dependency access inside handlers
│   ├── core/
│   │   ├── config.py            # env-based settings (fails fast, no secrets)
│   │   ├── logging.py           # structured logging + secret redaction
│   │   └── constants.py         # starting values, tunable XP curve, limits
│   ├── database/
│   │   ├── models/              # SQLAlchemy ORM models (Player, Job, House, Land, ...)
│   │   ├── repositories/        # the only layer that queries the DB
│   │   ├── database.py          # async engine + session factory
│   │   └── migrations/          # migration strategy notes (Alembic later)
│   ├── game/
│   │   ├── player/              # pure domain: progression math, DTOs
│   │   ├── family/              # pure domain: marriage, mahriyeh, pregnancy
│   │   ├── business/            # pure domain: predefined catalog and DTOs
│   │   ├── housing/             # pure domain: city catalog, dynamic pricing, DTOs
│   │   ├── market/              # pure catalog, DTOs, replaceable TGJU provider
│   │   ├── realestate/          # pure domain: land pricing, construction, renovation
│   │   ├── admin/               # pure domain: runtime knobs, Persian-number parsing, DTOs
│   │   └── shared/              # shared domain errors
│   └── services/                # business logic + transaction boundaries
├── tests/                       # pytest suite
├── scripts/
│   └── init_db.py               # standalone DB initializer
├── .env.example
├── .gitignore
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
├── README.md
└── main.py                      # entry point
```

## Architecture

Strict dependency flow — each layer only talks to the one below it:

```
Telegram Handler   (app/bot/handlers)      → Telegram interaction only
       ↓
Service            (app/services)          → business rules + transactions
       ↓
Repository         (app/database/repositories) → all database access
       ↓
Database           (SQLAlchemy async engine)
```

Design decisions worth knowing:

- **One profile per Telegram user** is enforced by a *unique index* on
  `telegram_user_id` in the database itself, plus an idempotent
  register-or-get flow that also survives concurrent `/start` races.
- **Money is an exact integer** (Toman). Floats are never used. Removals are
  atomic single-statement operations — the balance can never go negative.
- **Level/XP progression** is isolated: pure math in `app/game/player/progression.py`,
  tunable constants in `app/core/constants.py`, mutations only via the
  `LevelService`. No system grants XP implicitly.
- **All Persian texts** live in `app/bot/messages/` — no strings scattered
  through handlers.
- **Secrets** come only from the environment; a log filter redacts the token
  even if it ever appears inside an exception traceback.
- **No age attribute** exists anywhere in the model — progression is Level + XP only.

## Job and Income System — «خر حمالی», time-based salary

The player-facing name of the whole job/income system is **خر حمالی** (it used
to be called شغل / مشاغل). `constants.JOBS_SYSTEM_NAME` is the single source of
that label, and the old texts `مشاغل` and `شغل من` still work as commands so
nobody is stranded by the rename. Jobs are no longer a "type `کار` to earn per
click" mechanic. Instead, each job pays a **hourly salary** from a named
**employer** (صاحبکار):

1. Pick a job from 💼 **خر حمالی** — the work start time is saved immediately.
2. Working time accrues automatically from that moment.
3. Press **💰 تسویه با صاحبکار** whenever you want to get paid:
   - the hours worked are calculated,
   - the salary is computed from the hourly rate,
   - the money is paid through the wallet system,
   - the work timer is reset.

Settling with the employer triggers a random **employer-behaviour event**:

| Event | Effect |
|-------|--------|
| ✅ Normal payment | Full earned salary is paid. |
| 🎉 Bonus payment | A random 10–30% bonus is added on top. |
| ⚠️ Mistake | A random 10–50% penalty is deducted from the earned salary. |
| ⏳ Delayed payment | The employer withholds payment — the timer keeps running so you can settle again later. |

Every event (payments, bonuses, penalties and delayed payments) is saved to the
`job_events` table and shown in 📜 تاریخچه تسویه‌ها.

### The selectable jobs

The catalog is exactly these six, seeded into the `jobs` table on first boot:

| Job | Level needed | Hourly salary | Employer |
|-----|--------------|---------------|----------|
| 🧱 بنایی | 1 | 80,000 | شرکت ساختمانی البرز |
| 🍽️ رستوران | 1 | 70,000 | رستوران آرمان |
| 🛍️ فروشندگی | 2 | 90,000 | مجموعه فروشگاه‌های آرمان |
| 🏍️ پیک موتوری | 3 | 120,000 | شرکت ارسال سریع پارس |
| 🚗 اسنپ | 5 | 160,000 | ناوگان اسنپ |
| 🏦 کارمند بانک | 8 | 220,000 | بانک پارسیان |

The three jobs the old catalog offered (کارگر، کارمند، متخصص) are **retired, not
deleted**: on the next boot each is backfilled (so anyone still working there is
paid at the rate they were hired for and their earnings history keeps
resolving) and then flagged `is_active = False`, which makes it unofferable.
Jobs an admin created in the panel are never touched, and the seed pass never
overwrites salary/level/employer values an admin has edited.

Everything else about the system is unchanged: the work timer, `settle_with_employer`,
the employer-behaviour rolls, `job_events`, XP and earnings behaviour, cooldowns
and the whole service layer.

## Business System 🏪

The Business System is deliberately catalog-driven: players cannot create a
custom business or submit an arbitrary type. The predefined data lives in
`app/game/business/catalog.py`, where each entry has a stable key, Persian
name, startup cost, minimum/maximum daily income and an availability flag.
`constants.BUSINESS_MAX_PER_PLAYER` controls the ownership cap (currently
**three** businesses per player).

Send **«کسب‌وکار»** or tap **🏪 کسب‌وکار** in the main menu to:

1. Browse every predefined business, its startup cost and expected daily
   income range.
2. Start an available business. The startup cost is checked and debited by the
   existing wallet service in the same transaction as the ownership row.
3. View owned businesses, their balances and the latest daily income.
4. Tap **💰 درآمد امروز** (or open the owned-business screen) to lazily settle
   each active business once for the current day.

Daily income is a random integer inside that business's configured range and is
credited to the business balance only — it never goes straight into the
player's personal wallet. The persisted `last_income_date` guard makes the
operation idempotent even if the player taps repeatedly or two requests race.
Existing owned businesses retain the terms captured when they were started, so
future catalog rebalancing affects new purchases without silently rewriting old
ones.

## Housing and Real-Estate System 🏠

Players own real houses with realistic properties, prices are **always computed
dynamically** — nothing is ever a fixed number — and the whole market is
**player-to-player** (no NPC buyers, sellers, landlords or tenants).

### Houses

Every house has a unique ID plus a full property list: city, neighborhood,
area (m²), bedrooms, living rooms, bathrooms, kitchen type (مدرن/معمولی/قدیمی),
construction year (سال ساخت, Solar Hijri — e.g. ۱۳۹۵), parking, elevator,
storage and a quality level (عالی/خوب/متوسط/ضعیف). The building's age is
never stored — it is derived internally as
``current_iranian_year() − construction_year`` wherever needed, while the UI
only ever shows the construction year.

### Dynamic pricing

The price of a house is recomputed from its attributes and the market catalog
every time it is shown:

```
price = base_price_per_sqm(city) × neighborhood_multiplier × area
      × size_factor × construction-year depreciation (floor 45%) × facility_bonus
      × kitchen_factor × quality_factor × market_factor × per-house jitter
```

* `app/game/housing/catalog.py` holds the Iranian cities (تهران، مشهد، اصفهان،
  شیراز، تبریز، کرج، قم، اهواز، رشت، یزد) with their neighborhoods and
  multipliers — **this file is the single connection point for a future live
  feed of the real Iranian housing market**: refresh it and every price in the
  game moves automatically.
* Rent follows the Iranian رهن/اجاره model: a bigger refundable deposit (رهن)
  lowers the monthly rent (اجاره).

### Buying, selling and renting

| Flow | How it works |
|------|--------------|
| Buy from the market | Ownerless houses (bank/developer) cost their live dynamic price. |
| Sell to players | Owner picks a price preset (85%–130% of live value) → other players buy it. Money and ownership move in **one atomic transaction**. |
| Rent to players | Owner picks a رهن/اجاره preset → a tenant signs a **rental contract** (stored with both parties), pays the deposit, then pays monthly rent via 💵 پرداخت اجاره. Either side can end the contract. |
| Assets | Owned houses are the player's assets — 🏠 خانه‌های من shows every house plus the total live value. |

Buying a house explicitly grants XP through the LevelService (never implicitly).

### Housing screens (all button-driven)

Send **«خانه»** (or use 🏠 خانه in the main menu):

* 🏠 خانه‌های من — assets + manage (فروش / اجاره‌دادن / لغو آگهی / پایان قرارداد)
* 🏖️ بازار مسکن — every purchasable house with ℹ️ and 🛒 buttons
* 🛏️ خانه‌های اجاره‌ای — rent offers from other players
* 📜 قراردادهای اجاره من — your contracts, rent payments and endings
* ℹ️ اطلاعات خانه — the full property sheet for any house

## Land, Construction and Renovation System 🌍🏗️🛠️

Everything starts with land. Land trades with **fully dynamic prices**, houses
are **built over real time** (never instantly) and renovations **raise
property value** by changing the very attributes the dynamic pricing engine
reads.

### Land

Every parcel has a unique ID, an owner, city, neighborhood, size (m²) and a
location-quality label (لوکس/عالی/خوب/متوسط derived from the neighborhood).
The market value is always recomputed live:

```
price = base_price_per_sqm(city) × LAND_RATIO(0.45) × neighborhood
      × size × wholesale_size_discount × market_factor × per-parcel jitter
```

``market_factor`` is the shared **economy knob**
(``constants.ECONOMY_MARKET_CONDITIONS``) — land prices, construction costs
and renovation costs all move together when the economy moves. This is the
future integration point for the Inflation/Economy system (and for real
Iranian market data, through the same housing catalog).

### Building on your land (🏗️ ساخت خانه)

A fully button-driven wizard picks: building type (آپارتمانی ۲–۴ طبقه /
ویلایی) → floors → total built area (bounded by land × floors) → bedrooms →
material grade (اقتصادی/استاندارد/لوکس) → facilities. Cost depends on size,
materials, floors, facilities and the live market; duration scales with
area/quality/floors (days). Money is paid upfront; progress can be followed:

```
🏗️ Building progress:
▓▓▓░░░░░░░ 40%
Time remaining: 6 days
```

On completion a brand-new House (age 0, chosen quality/kitchen/facilities) is
created on the parcel and plugs straight into the Housing system — it appears
in خانه‌های من, can be sold, rented out, and its value is the standard dynamic
house price. Cancelling an active project refunds 70%. Completion grants XP.

### Renovation (🛠️ بازسازی خانه)

Each owned, tenant-free house offers live-quoted options — raise quality,
renovate the kitchen, add a bathroom, add a room, add parking/elevator/
storage, or modernize an old building (advances the construction year).
Every option costs
money and takes days; on completion the house attributes change and the
dynamic pricing engine immediately values it higher (recorded as
value_before → value_after in the `property_upgrades` audit table).

### Screens

Inside 🏠 خانه: 🌍 زمین‌های من · 🛒 خرید زمین · 🏗️ ساخت خانه · 📈 وضعیت ساخت ·
🛠️ بازسازی خانه · ℹ️ اطلاعات ملک — plus the Persian text commands «زمین‌های من»،
«خرید زمین»، «ساخت خانه»، «وضعیت ساخت»، «بازسازی خانه». Completed
constructions and renovations settle lazily whenever any related screen is
opened (atomic, race-safe) — a future scheduler can also call
``RealEstateService.settle_due()`` periodically.

## Marriage and Family System 💍

Families are built, maintained and dissolved **entirely through text
commands** — this system adds no menu and no inline button anywhere, so it fits
inside the existing handler structure and the main menu is untouched.

| Command | How you send it | What it does |
|---|---|---|
| `ازدواج` | **reply to the target player's message** | opens a marriage request (quotes the Mahriyeh) |
| `قبول` | anywhere | accepts the request addressed to you → marriage recorded |
| `رد` | anywhere | rejects it |
| `لغو ازدواج` | anywhere | the proposer withdraws their open request |
| `طلاق` | anywhere | divorce — pays the stored Mahriyeh to the spouse |
| `رابطه` | **reply to your spouse's message** | relationship event, raises quality, may cause a pregnancy |
| `خیانت` | anywhere (answered **privately**) | hidden cheating attempt with escalating consequences |
| `خانواده` | anywhere | family card: status, spouse, marriage date, children, Mahriyeh |
| `فرزندان` / `تاریخچه خانواده` | anywhere | children list / family timeline |
| `راهنمای خانواده` | anywhere | the command list |

### Rules that are enforced, not suggested

* **One marriage at a time.** A married player cannot propose (`AlreadyMarriedError`)
  and a married target is refused with their name shown. The check runs inside
  the same transaction that creates the marriage, and the request row is
  claimed with a guarded `UPDATE`, so a double accept can never produce two
  marriages. A *partial unique index* also keeps the database itself holding at
  most one **pending** request per player (closed requests stay as history).
* **Gates:** level ≥ `MARRIAGE_MIN_LEVEL` (۳) and at least
  `MARRIAGE_MIN_MONEY` in the wallet before proposing.
* **Requests expire** after `MARRIAGE_REQUEST_EXPIRY_HOURS` (۲۴) and the expiry
  is settled lazily — an expired request cannot be accepted.

### Mahriyeh (مهریه) — computed, then frozen

At the wedding the Mahriyeh is computed from the proposer's own situation and
**stored on the marriage row**:

```
mahriyeh = base + level × per_level + wallet / wealth_divisor  (× market factor)
```

It is never recomputed afterwards, so an economy change mid-marriage cannot
rewrite a promise. Divorce **is** the moment it is paid: the initiator pays the
stored amount to the spouse through the existing wallet primitives, inside the
same transaction as the status change.

* Not enough money? The divorce is **refused** and the player is told the
  required amount, their balance and the shortfall.
* Caught cheating? The **wronged** spouse divorces **free** (waiver).

### Cheating (`خیانت`) — hidden, with escalating consequences

Two independent dice: whether the act happened
(`CHEATING_SUCCESS_CHANCE`) and whether it was found out
(`CHEATING_DISCOVERY_CHANCE`). Only a **discovery** has consequences, and they
escalate per discovery:

| Discovery | Money fine | Relationship damage | Extra |
|---|---|---|---|
| 1st | ۱٬۰۰۰٬۰۰۰ | −۲۵ | spouse is notified |
| 2nd | ۵٬۰۰۰٬۰۰۰ | −۴۰ | spouse may now divorce free |
| 3rd | ۱۰٬۰۰۰٬۰۰۰ | −۱۰۰ | **the marriage is dissolved by the system**, cheater pays |

The fine is *transferred* to the wronged spouse (money stays in the game), the
`social_penalties` counter records the reputation hit for the future society
system, and in a group chat the whole exchange is routed through a **private
message** so nothing leaks into the thread.

### Children and lazy birth

A `رابطه` event rolls a pregnancy chance that **scales with relationship
quality** (15 % base, ×1.6 at a perfect relationship). A conception is stored
on the marriage with a due date `PREGNANCY_DURATION_DAYS` (۷) later and completes
**lazily** — the exact strategy the construction/renovation system uses, so no
scheduler is required:

* any family screen (and the profile) calls `FamilyService.settle_due()`;
* completion is claimed with a guarded `UPDATE`, so two concurrent settlers
  never hand the same child to the family twice;
* the child row stores father, mother, birth date, Solar-Hijri birth year
  (age is always *derived*, like a house's construction year) and a growth
  stage — and both parents' `children_count` plus their XP are updated
  atomically.

`MAX_CHILDREN_PER_MARRIAGE` (۵) caps a family, and `expenses_total` plus
`growth_stage` are the ready-made hooks for the family-expenses and education
systems.

### Integration points

| Existing system | How the family uses it |
|---|---|
| Users | players resolved by Telegram id; the proposal target comes from `reply_to_message.from_user` |
| Wallet | `remove_money_if_enough` / `add_money` — the same atomic pair the housing market uses |
| Level/XP | `ازدواج` +۶۰, `رابطه` +۱۰, a birth +۱۰۰ per parent — always explicit, via `LevelService` |
| Profile | `💍 وضعیت ازدواج`, spouse name+id, marriage date and children count now render on the existing profile screen |
| Database | 6 new tables (`marriages`, `marriage_requests`, `divorce_records`, `children`, `relationship_events`, `family_history`) + additive `players` columns; old databases upgrade on boot with no rows dropped |

All tunables (gates, Mahriyeh formula, odds, tiers, durations, XP) live in
`app/core/constants.py`, and the pure rules in `app/game/family/domain.py` —
the same layout as the housing pricing engine.

## Admin Panel 🛡️

The `/admin` command opens a fully **button-driven control console** for the
game's administrators (default: Telegram ID `8154313073`). Everyone else is
blocked with a polite message, and a middleware layer stops every update from
banned players with a short notice before any handler runs.

* **📊 Dashboard** — live stats: total/active/banned users, money in
  circulation, houses, lands, jobs, active listings/contracts/rentals, the
  live market factor and the server/database health.
* **👥 Users** — paged list, search (by ID / username / name), full profile,
  transactions and properties; add/remove money, add/remove XP, set level,
  ban/unban. Persian digits and suffixes (k/m/B, میلیون/میلیارد) are parsed.
* **💰 Economy** — inflation rate, base market conditions, currency/gold/
  crypto assets with price history, timed economic events and a one-tap
  crisis preset. The **effective market factor** (base × events) drives all
  house, land, construction and renovation prices live.
* **🏠 Real estate** — every house/land with edit screens (area, city,
  construction year, facilities, quality, location, per-property price
  override), active sale listings (close/remove) and rental contracts
  (terminate).
* **💼 Jobs** — create jobs through a guided 6-step flow, edit salary/level/
  employer, enable/disable jobs, watch active workers.
* **📈 Trading** — market activity, sale history and rental volume (a full
  trading exchange stays a future system; the read-side scaffold is ready).
* **⚙️ Settings** — XP reward bounds/divisors, minimum settle minutes and
  **feature flags** that instantly enable/disable the jobs and housing
  systems (menus hide them automatically).
* **🗄️ Database tools** — stats, one-tap backups (also sent as a file),
  restore with a confirm step, and safe cleanup of old listings/audit
  rows/price ticks.
* **📋 Logs** — the immutable admin-audit trail (who did what, when),
  user/economy/land/DB action views and the recent error log.

The admin code follows the same architecture (handlers → `AdminService` →
repositories); every money/XP mutation reuses the existing atomic services,
and old databases are upgraded additively (no rows dropped).

## What is intentionally NOT in this stage

Education, skills, vehicles, loans, investments, a trading exchange, crime,
police, prisons and bankruptcy are **not implemented** — the architecture is
simply prepared for them. The read-only **📈 بازار ایران** quote screen is
implemented separately and is not a player trading exchange. (Marriage and
family **are** implemented — see the section above; child *growth*, education
and family expenses are deliberately left as the next step and already have
their columns.)

## Useful Commands

| Command                     | Purpose                        |
|-----------------------------|--------------------------------|
| `python main.py`            | Run the bot                    |
| `python scripts/init_db.py` | Initialize the database        |
| `pytest`                    | Run the test suite             |
| `cp .env.example .env`      | Create your local config       |
