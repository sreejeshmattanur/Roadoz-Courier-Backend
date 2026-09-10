import asyncio

import pytest
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine, init_db
from app.main import (
    _seed_default_role_permissions,
    _seed_driver_role,
    _seed_permissions,
    _seed_super_admin,
)


async def _patch_sqlite_dev_schema():
    """ponytail: init_db won't ALTER existing sqlite tables; patch known pull deltas."""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return

    patches = [
        ("roles", "warehouse_id", "VARCHAR(36)"),
        ("users", "warehouse_id", "VARCHAR(36)"),
        ("drivers", "warehouse_id", "VARCHAR(36)"),
        ("drivers", "meta", "JSON"),
        ("vehicles", "warehouse_id", "VARCHAR(36)"),
        ("franchises", "latitude", "REAL"),
        ("franchises", "longitude", "REAL"),
        ("trip_sheets", "driver_status", "VARCHAR(30)"),
        ("trip_sheets", "accepted_at", "DATETIME"),
        ("trip_sheets", "started_at", "DATETIME"),
        ("trip_sheets", "completed_at", "DATETIME"),
        ("trip_sheets", "updated_at", "DATETIME"),
        ("orders", "meta", "JSON"),
    ]
    drop_columns = [
        ("drivers", "public_id"),
        ("vehicles", "public_id"),
    ]
    async with engine.begin() as conn:
        for table, column, col_type in patches:
            result = await conn.execute(text(f"PRAGMA table_info({table})"))
            cols = {row[1] for row in result.fetchall()}
            if column not in cols:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
        for table, column in drop_columns:
            result = await conn.execute(text(f"PRAGMA table_info({table})"))
            cols = {row[1] for row in result.fetchall()}
            if column in cols:
                await conn.execute(text(f"DROP INDEX IF EXISTS ix_{table}_public_id"))
                await conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    async def _setup():
        await init_db()
        await _patch_sqlite_dev_schema()
        await _seed_permissions()
        await _seed_super_admin()
        await _seed_default_role_permissions()
        await _seed_driver_role()

    asyncio.run(_setup())
