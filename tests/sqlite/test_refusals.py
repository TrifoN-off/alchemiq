"""Loud refusals on SQLite: PostgreSQL-only features fail with actionable errors."""

from __future__ import annotations

import pytest

from alchemiq import Repository
from alchemiq.exceptions import ConfigError, QueryError
from alchemiq.runtime.engine import require_engine
from tests.sqlite._models import SqAuthor, SqnopeArrayed


async def test_array_ddl_refuses_on_sqlite(sqlite_db) -> None:
    engine = require_engine()
    with pytest.raises(ConfigError, match=r"Array fields are PostgreSQL-only.*'tags'"):
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: SqnopeArrayed.__table__.create(c))


async def test_explain_refuses_on_sqlite(sqlite_db) -> None:
    with pytest.raises(QueryError, match=r"explain.*PostgreSQL-only"):
        await Repository(SqAuthor).explain()
