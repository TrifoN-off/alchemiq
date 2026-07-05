"""PG Alembic backend round-trip: makemigrations -> migrate -> rollback."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

# Import model so MigrationAccount registers in global metadata at collection time.
import tests.integration._migration_models  # noqa: F401
from alchemiq.migrations.config import AlchemiqConfig, PostgresSettings
from alchemiq.migrations.postgres import backend

pytestmark = pytest.mark.integration


def _parts_from_url(url: str) -> dict:
    from sqlalchemy.engine import make_url

    u = make_url(url)
    return {
        "host": u.host,
        "port": u.port,
        "database": u.database,
        "username": u.username,
        "password": u.password,
    }


def _cfg(tmp_path: Path, url_parts: dict) -> AlchemiqConfig:
    return AlchemiqConfig(
        root=tmp_path,
        models=("tests.integration._migration_models",),
        migrations_dir="migrations",
        postgres=PostgresSettings(**url_parts),
    )


async def _get_table_names(url: str) -> list[str]:
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
    await engine.dispose()
    return tables


async def _create_existing_tables(url: str) -> None:
    """Pre-create every registered table except migration_account.

    SQLAlchemy DDL handles TypeDecorators (e.g. _MaybeType) correctly via
    impl_instance.  Pre-populating the DB means autogenerate only sees
    migration_account as missing, so the generated migration is minimal.
    """
    from alchemiq.model.registry import metadata

    engine = create_async_engine(url)
    to_create = [t for t in metadata.sorted_tables if t.name != "migration_account"]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: metadata.create_all(c, tables=to_create))
    await engine.dispose()


def test_pg_makemigrations_migrate_rollback(pg_container, tmp_path) -> None:
    url = pg_container.get_connection_url()

    # Pre-create all registered tables except migration_account so that Alembic
    # autogenerate detects only migration_account as new (avoids generating DDL for
    # custom types like _MaybeType that Alembic cannot round-trip).
    asyncio.run(_create_existing_tables(url))

    parts = _parts_from_url(url)
    cfg = _cfg(tmp_path, parts)

    # 1. Autogenerate - only migration_account should appear as new.
    backend.makemigrations(cfg, "init")
    versions = list((tmp_path / "migrations" / "postgres" / "versions").glob("*.py"))
    assert versions, "a revision file should be generated"
    text_src = versions[0].read_text("utf-8")
    assert "LargeBinary" in text_src  # render_item rendered _EncryptedType as its impl

    # 2. Apply migration - sync Alembic call; then inspect via own asyncio.run.
    backend.migrate(cfg)
    tables = asyncio.run(_get_table_names(url))
    assert "migration_account" in tables

    # history() must not raise; exercised here to cover the backend path.
    backend.history(cfg)

    # 3. Rollback - sync Alembic call; then confirm table is gone.
    backend.rollback(cfg)
    tables = asyncio.run(_get_table_names(url))
    assert "migration_account" not in tables
