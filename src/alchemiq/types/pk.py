"""PK - primary-key field type.

Usage::

    class User(Model):
        id: PK[int]

``PK[int]`` returns a ``PK`` instance pre-configured as a BIGINT autoincrement primary key
(INTEGER on SQLite, where only INTEGER PRIMARY KEY autoincrements).
"""

from __future__ import annotations

import uuid
from functools import partial
from typing import Any

from sqlalchemy import BigInteger, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.types import TypeEngine

from alchemiq._internal.ids import nanoid, uuid7
from alchemiq.exceptions import ConfigError
from alchemiq.types.base import FieldType


class PK[T](FieldType[T]):
    """Primary key. ``PK[int]`` -> BIGINT autoincrement (INTEGER on SQLite)."""

    python_type = int

    def __init__(self, inner: type = int, **kw: Any) -> None:
        super().__init__(primary_key=True, **kw)
        if inner is not int:
            raise ConfigError(f"PK[{inner!r}] unsupported in this slice; use PK[int]")
        self.python_type = inner

    def __class_getitem__(cls, item: type) -> PK:
        return cls(item)

    def column_type(self) -> TypeEngine[Any]:
        """Return ``BigInteger`` (``INTEGER`` on SQLite for autoincrement)."""
        return BigInteger().with_variant(Integer(), "sqlite")


class UUID4(FieldType[uuid.UUID]):
    """UUID version 4 (random) field. Stores as PostgreSQL native UUID."""

    python_type = uuid.UUID

    def __init__(self, **kw: Any) -> None:
        kw.setdefault("primary_key", False)
        super().__init__(default=uuid.uuid4, **kw)

    def column_type(self) -> TypeEngine[Any]:
        """Return ``PgUUID(as_uuid=True)`` (``CHAR(32)`` string storage on SQLite)."""
        return PgUUID(as_uuid=True).with_variant(Uuid(native_uuid=False), "sqlite")


class UUID7(FieldType[uuid.UUID]):
    """UUID version 7 (time-ordered) field. Stores as PostgreSQL native UUID."""

    python_type = uuid.UUID

    def __init__(self, **kw: Any) -> None:
        super().__init__(default=uuid7, **kw)

    def column_type(self) -> TypeEngine[Any]:
        """Return ``PgUUID(as_uuid=True)`` (``CHAR(32)`` string storage on SQLite)."""
        return PgUUID(as_uuid=True).with_variant(Uuid(native_uuid=False), "sqlite")


class NanoID(FieldType[str]):
    """NanoID string field stored as ``VARCHAR(size)``. Default size is 21 characters."""

    python_type = str

    def __init__(self, size: int = 21, **kw: Any) -> None:
        super().__init__(default=partial(nanoid, size), max_length=size, **kw)
        self.size = size

    def column_type(self) -> TypeEngine[Any]:
        """Return ``String(size)``."""
        return String(self.size)
