"""Driverless-DSN normalization in configure()."""

from __future__ import annotations

from alchemiq.runtime.engine import _normalized_url


def test_sqlite_scheme_gets_aiosqlite_driver() -> None:
    assert str(_normalized_url("sqlite:///./app.db")) == "sqlite+aiosqlite:///./app.db"
    assert str(_normalized_url("sqlite://")) == "sqlite+aiosqlite://"


def test_postgresql_scheme_gets_asyncpg_driver() -> None:
    assert _normalized_url("postgresql://u:p@h:5432/db").drivername == "postgresql+asyncpg"


def test_explicit_drivers_pass_through_unchanged() -> None:
    assert _normalized_url("postgresql+psycopg://u:p@h/db").drivername == "postgresql+psycopg"
    assert _normalized_url("sqlite+aiosqlite:///x.db").drivername == "sqlite+aiosqlite"
