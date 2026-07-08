"""Alembic env.py for the alchemiq PostgreSQL migration template (online + offline modes)."""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config
target_metadata = config.attributes["target_metadata"]
url = config.attributes["url"]
render_item = config.attributes.get("render_item")


def do_run_migrations(connection: Connection) -> None:
    """Configure Alembic context and run pending migrations on *connection*."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_item=render_item,
        compare_type=True,
        # SQLite cannot ALTER most things in place; batch mode makes autogen
        # emit batch_alter_table blocks (a no-op flag for PostgreSQL).
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    """Connect to the database and run migrations in online mode."""
    engine = create_async_engine(url)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_offline() -> None:
    """Emit migration SQL to stdout without a live database connection (offline mode)."""
    context.configure(
        url=url,
        target_metadata=target_metadata,
        render_item=render_item,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=url.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_offline()
else:
    asyncio.run(run_online())
