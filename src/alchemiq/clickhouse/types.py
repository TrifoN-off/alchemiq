"""ClickHouse-typed FieldType descriptors and the Python-to-CH type mapping table."""

from __future__ import annotations

import datetime as dt
import enum as _enum
from decimal import Decimal
from typing import Any
from uuid import UUID

from clickhouse_sqlalchemy import types as ch  # ty: ignore[unresolved-import]
from sqlalchemy.types import TypeEngine

from alchemiq.exceptions import ConfigError
from alchemiq.types.base import FieldType


class _CHField(FieldType):
    """Base for fixed-CH-type fields; subclasses set python_type + _ch."""

    _ch: type[TypeEngine[Any]]

    def column_type(self) -> TypeEngine[Any]:
        return self._ch()


class UInt8(_CHField):
    """ClickHouse UInt8 column field (unsigned 8-bit integer, range 0-255)."""

    python_type = int
    _ch = ch.UInt8


class UInt16(_CHField):
    """ClickHouse UInt16 column field (unsigned 16-bit integer)."""

    python_type = int
    _ch = ch.UInt16


class UInt32(_CHField):
    """ClickHouse UInt32 column field (unsigned 32-bit integer)."""

    python_type = int
    _ch = ch.UInt32


class UInt64(_CHField):
    """ClickHouse UInt64 column field (unsigned 64-bit integer)."""

    python_type = int
    _ch = ch.UInt64


class Int8(_CHField):
    """ClickHouse Int8 column field (signed 8-bit integer)."""

    python_type = int
    _ch = ch.Int8


class Int16(_CHField):
    """ClickHouse Int16 column field (signed 16-bit integer)."""

    python_type = int
    _ch = ch.Int16


class Int32(_CHField):
    """ClickHouse Int32 column field (signed 32-bit integer)."""

    python_type = int
    _ch = ch.Int32


class Int64(_CHField):
    """ClickHouse Int64 column field (signed 64-bit integer)."""

    python_type = int
    _ch = ch.Int64


class Float32(_CHField):
    """ClickHouse Float32 column field (single-precision float)."""

    python_type = float
    _ch = ch.Float32


class Float64(_CHField):
    """ClickHouse Float64 column field (double-precision float)."""

    python_type = float
    _ch = ch.Float64


class LowCardinality(FieldType):
    """ClickHouse LowCardinality wrapper - dictionary-encodes a column for low-cardinality data.

    :param inner: Python type whose default CH scalar is used as the inner type
        (default ``str``).
    """

    def __init__(self, inner: type = str, **kw: Any) -> None:
        super().__init__(python_type=inner, **kw)

    def column_type(self) -> TypeEngine[Any]:
        """Return ``LowCardinality(<inner_ch_type>)``."""
        return ch.LowCardinality(_scalar_ch(self.python_type))


class DateTime64(FieldType):
    """ClickHouse DateTime64 column field with configurable sub-second precision.

    When ``nullable=True`` is passed, the column type is wrapped in
    ``Nullable(DateTime64)`` because ClickHouse requires the explicit ``Nullable``
    wrapper in DDL.

    :param precision: Sub-second precision digits (0-9; default ``3`` = milliseconds).
    """

    python_type = dt.datetime

    def __init__(self, precision: int = 3, **kw: Any) -> None:
        super().__init__(**kw)
        self.precision = precision

    def column_type(self) -> TypeEngine[Any]:
        """Return ``DateTime64(precision)`` or ``Nullable(DateTime64(precision))``."""
        inner = ch.DateTime64(self.precision)
        # ClickHouse uses Nullable(Type) syntax for nullable columns;
        # SA's nullable=True alone does not produce the Nullable wrapper in CH DDL.
        if self.config.nullable:
            return ch.Nullable(inner)
        return inner


class Enum8(FieldType):
    """ClickHouse Enum8 column field defined by an explicit name-to-integer mapping.

    :param members: Dict mapping member name to integer value, e.g.
        ``{"active": 1, "inactive": 2}``.
    """

    python_type = str

    def __init__(self, members: dict[str, int], **kw: Any) -> None:
        super().__init__(**kw)
        self.members = members

    def column_type(self) -> TypeEngine[Any]:
        """Return a ``ch.Enum8`` type built from the members mapping."""
        ch_enum = _enum.IntEnum("ch_enum", self.members)
        return ch.Enum8(ch_enum)


_SCALAR: dict[type, type[TypeEngine[Any]]] = {
    int: ch.Int64,
    str: ch.String,
    float: ch.Float64,
    bool: ch.UInt8,
    dt.datetime: ch.DateTime64,
    dt.date: ch.Date,
    Decimal: ch.Decimal,
    UUID: ch.UUID,
}


def _scalar_ch(python_type: type) -> TypeEngine[Any]:
    try:
        factory = _SCALAR[python_type]
    except KeyError as e:
        raise ConfigError(f"No default ClickHouse type for {python_type!r}") from e
    if factory is ch.DateTime64:
        return factory(3)
    if factory is ch.Decimal:
        return factory(38, 9)
    return factory()


def ch_column_type(python_type: type) -> TypeEngine[Any]:
    """Default Python->ClickHouse column type for a bare annotation."""
    return _scalar_ch(python_type)
