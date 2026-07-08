"""Temporal field types: DateTimeTz, Date, Time, UnixTimestamp, CreatedAt, UpdatedAt."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import BigInteger, DateTime, func
from sqlalchemy import Date as SaDate
from sqlalchemy import Time as SaTime
from sqlalchemy.types import TypeDecorator, TypeEngine

from alchemiq.exceptions import ValidationError
from alchemiq.types.base import FieldType


class _SqliteUtcDateTime(TypeDecorator[dt.datetime]):
    """SQLite storage for tz-aware datetimes: naive UTC on disk, aware UTC in Python.

    SQLite has no timezone-aware column type, so ``DateTime(timezone=True)``
    would round-trip as a NAIVE datetime and silently break parity with
    PostgreSQL.  Write: any tz-aware datetime -> naive UTC.  Read: naive ->
    UTC-aware.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: dt.datetime | None, dialect: Any) -> dt.datetime | None:
        """Convert a tz-aware datetime to naive UTC for storage."""
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValidationError(reason="datetime must be timezone-aware", value=value)
        return value.astimezone(dt.UTC).replace(tzinfo=None)

    def process_result_value(self, value: dt.datetime | None, dialect: Any) -> dt.datetime | None:
        """Attach UTC to the stored naive datetime."""
        if value is None:
            return None
        return value.replace(tzinfo=dt.UTC)


def _tz_datetime() -> TypeEngine[Any]:
    return DateTime(timezone=True).with_variant(_SqliteUtcDateTime(), "sqlite")


class DateTimeTz(FieldType[dt.datetime]):
    """Timezone-aware datetime field stored as ``DateTime(timezone=True)``.

    Raises ``ValidationError`` if a naive ``datetime`` (no ``tzinfo``) is assigned.
    """

    python_type = dt.datetime

    def column_type(self) -> TypeEngine[Any]:
        """Return ``DateTime(timezone=True)`` (UTC-normalizing variant on SQLite)."""
        return _tz_datetime()

    def validate(self, value: Any) -> Any:
        """Reject naive datetimes; pass through tz-aware values unchanged."""
        if isinstance(value, dt.datetime) and value.tzinfo is None:
            raise ValidationError(reason="datetime must be timezone-aware", value=value)
        return value


class Date(FieldType[dt.date]):
    """Calendar date field stored as a SQL ``DATE`` column."""

    python_type = dt.date

    def column_type(self) -> TypeEngine[Any]:
        """Return ``SaDate()``."""
        return SaDate()


class Time(FieldType[dt.time]):
    """Time-of-day field stored as a SQL ``TIME`` column."""

    python_type = dt.time

    def column_type(self) -> TypeEngine[Any]:
        """Return ``SaTime()``."""
        return SaTime()


class EpochInt(TypeDecorator[dt.datetime]):
    """``BigInteger`` TypeDecorator that stores datetimes as Unix seconds.

    Write: tz-aware ``datetime`` -> ``int(timestamp())``. Naive datetimes raise
    ``ValidationError``. Read: integer -> UTC-aware ``datetime``.
    """

    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value: dt.datetime | None, dialect: Any) -> int | None:
        """Convert a tz-aware datetime to a Unix timestamp integer."""
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValidationError(reason="datetime must be tz-aware", value=value)
        return int(value.timestamp())

    def process_result_value(self, value: int | None, dialect: Any) -> dt.datetime | None:
        """Convert a Unix timestamp integer to a UTC-aware datetime."""
        if value is None:
            return None
        return dt.datetime.fromtimestamp(value, tz=dt.UTC)


class UnixTimestamp(FieldType[dt.datetime]):
    """Datetime stored as a Unix epoch integer (``BigInteger``) via ``EpochInt``.

    Raises ``ValidationError`` if a naive ``datetime`` (no ``tzinfo``) is assigned.
    Reads return a UTC-aware ``datetime``.
    """

    python_type = dt.datetime

    def column_type(self) -> TypeEngine[Any]:
        """Return ``EpochInt()`` backed by ``BigInteger``."""
        return EpochInt()

    def validate(self, value: Any) -> Any:
        """Reject naive datetimes; pass through tz-aware values unchanged."""
        if isinstance(value, dt.datetime) and value.tzinfo is None:
            raise ValidationError(reason="datetime must be timezone-aware", value=value)
        return value


class CreatedAt(FieldType[dt.datetime]):
    """Auto-populated creation timestamp - ``DateTime(timezone=True)``, ``server_default=now()``.

    Set once by the database on insert; NOT NULL by default.
    """

    python_type = dt.datetime

    def __init__(self, **kw: Any) -> None:
        kw.setdefault("nullable", False)
        super().__init__(server_default=func.now(), **kw)

    def column_type(self) -> TypeEngine[Any]:
        """Return ``DateTime(timezone=True)`` (UTC-normalizing variant on SQLite)."""
        return _tz_datetime()


class UpdatedAt(FieldType[dt.datetime]):
    """Auto-updated modification timestamp - ``DateTime(timezone=True)``, ``onupdate=now()``.

    Set by the database on insert and refreshed on every UPDATE; NOT NULL by default.
    """

    python_type = dt.datetime

    def __init__(self, **kw: Any) -> None:
        kw.setdefault("nullable", False)
        super().__init__(server_default=func.now(), onupdate=func.now(), **kw)

    def column_type(self) -> TypeEngine[Any]:
        """Return ``DateTime(timezone=True)`` (UTC-normalizing variant on SQLite)."""
        return _tz_datetime()
