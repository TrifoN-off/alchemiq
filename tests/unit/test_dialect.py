"""Unit tests for the internal dialect helpers."""

from __future__ import annotations

import builtins

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import make_url

from alchemiq._internal.dialect import (
    dialect_of,
    ensure_async_driver,
    insert_for,
    require_postgres,
)
from alchemiq.exceptions import ConfigError, QueryError


class _FakePgBind:
    class dialect:  # noqa: N801 - mimics sqlalchemy's lowercase attribute
        name = "postgresql"


def _sqlite_bind():
    return create_engine("sqlite://")  # sync stdlib sqlite3; no aiosqlite needed here


def test_dialect_of_reads_engine_dialect() -> None:
    assert dialect_of(_sqlite_bind()) == "sqlite"
    assert dialect_of(_FakePgBind()) == "postgresql"


def test_insert_for_picks_dialect_insert() -> None:
    assert insert_for(_sqlite_bind()) is sqlite_insert
    assert insert_for(_FakePgBind()) is pg_insert


def test_require_postgres_raises_uniform_message_on_sqlite() -> None:
    with pytest.raises(ConfigError, match=r"PostgreSQL-only.*feature matrix"):
        require_postgres("QuerySet.explain()", _sqlite_bind())


def test_require_postgres_supports_custom_exception() -> None:
    with pytest.raises(QueryError):
        require_postgres("QuerySet.explain()", _sqlite_bind(), exc=QueryError)


def test_require_postgres_is_noop_on_postgres() -> None:
    require_postgres("anything", _FakePgBind())


def test_ensure_async_driver_missing_aiosqlite_raises_configerror(monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "aiosqlite":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ConfigError, match=r"alchemiq\[sqlite\]"):
        ensure_async_driver(make_url("sqlite+aiosqlite:///:memory:"))


def test_ensure_async_driver_missing_asyncpg_raises_configerror(monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "asyncpg":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ConfigError, match=r"alchemiq\[postgres\]"):
        ensure_async_driver(make_url("postgresql+asyncpg://u:p@h/db"))


def test_ensure_async_driver_ignores_unmapped_backends() -> None:
    ensure_async_driver(make_url("clickhouse://user:pass@host/db"))  # no-op


def test_ensure_async_driver_ignores_other_explicit_drivers(monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "asyncpg":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    # Even with asyncpg unavailable, a non-bundled explicit driver is a no-op.
    monkeypatch.setattr(builtins, "__import__", fake_import)
    ensure_async_driver(make_url("postgresql+psycopg://u:p@h/db"))
