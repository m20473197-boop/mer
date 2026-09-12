"""Standalone database initializer.

Usage (from the project root):

    python scripts/init_db.py

Creates any missing tables using DATABASE_URL from the environment / .env
file. Existing tables and data are never touched, so this is safe to run
any number of times.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_database_url  # noqa: E402
from app.database.database import Database  # noqa: E402


async def main() -> None:
    database = Database(load_database_url())
    try:
        await database.create_all()
        safe_url = database.engine.url.render_as_string(hide_password=True)
        print(f"✅ Database initialized: {safe_url}")
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
