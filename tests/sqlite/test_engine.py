"""Engine-level SQLite behaviour: FK enforcement and driverless DSNs."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

import alchemiq
from alchemiq.runtime.engine import require_engine
from alchemiq.runtime.session import session_scope
from tests.sqlite._models import SqBook


async def test_fk_violations_are_enforced(sqlite_db) -> None:
    with pytest.raises(IntegrityError):
        async with session_scope(write=True) as s:
            s.add(SqBook(id=1, title="orphan", author_id=999))


async def test_driverless_sqlite_dsn_is_normalized() -> None:
    alchemiq.configure("sqlite://")
    try:
        assert require_engine().dialect.name == "sqlite"
    finally:
        await alchemiq.dispose()
