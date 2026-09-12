# Database Migrations

## Current strategy (stage 1)

- The schema is created with SQLAlchemy `Base.metadata.create_all`:
  - automatically on bot startup (via `post_init` in `main.py`),
  - or manually via `python scripts/init_db.py`.
- `create_all` only **adds missing tables** — it never drops or alters
  existing data, so player data survives bot restarts.
- The additive `iran_market_assets`, `iran_market_price_history`, and
  `iran_market_update_state` tables belong to the separate `📈 بازار ایران`
  service. They do not replace or alter the legacy Admin Economy
  `market_assets` / `market_price_ticks` tables.

## Renames & data conversions (lightweight, idempotent)

A few schema changes beyond plain additions are handled by the same
startup mechanism in ``app/database/database.py``:

- **Column renames** (``_SQLITE_COLUMN_RENAMES``) — e.g. the
  construction-year update renamed ``houses.building_age_years`` to
  ``construction_year``.
- **One-shot data conversions** — after that rename, stored ages were
  converted to construction years via a single guarded
  ``UPDATE houses SET construction_year = <current_iranian_year> − construction_year
  WHERE construction_year < 1330`` (real Solar-Hijri years are ≥ 1330, so the
  guard makes the migration naturally idempotent).

Every step is idempotent and runs on every boot, so existing house data
survives the upgrade untouched apart from the intended conversion.

## Future strategy

Once the schema changes grow beyond these targeted steps,
[Alembic](https://alembic.sqlalchemy.org) will be introduced and its version
files will live in this package.

The models already attach a stable naming convention to all constraints,
which keeps that transition smooth.
