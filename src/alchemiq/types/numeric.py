"""Numeric field types: Money, Positive, NonNegative, Percent, Bounded, RoundedDecimal."""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from sqlalchemy import BigInteger, Numeric, text
from sqlalchemy.types import TypeDecorator, TypeEngine

from alchemiq.exceptions import ValidationError
from alchemiq.types.base import FieldType


class MinorUnits(TypeDecorator[Decimal]):
    """Store a Decimal as integer minor units (e.g. cents/kopecks) in a BigInteger column."""

    impl = BigInteger
    cache_ok = True

    def __init__(self, scale: int = 2) -> None:
        super().__init__()
        self.scale = scale

    def process_bind_param(self, value: Decimal | None, dialect: Any) -> int | None:
        """Convert a ``Decimal`` to an integer minor-units value before writing."""
        if value is None:
            return None
        return int((Decimal(value) * (10**self.scale)).to_integral_value(ROUND_HALF_EVEN))

    def process_result_value(self, value: int | None, dialect: Any) -> Decimal | None:
        """Convert an integer minor-units value back to ``Decimal`` after reading."""
        if value is None:
            return None
        return Decimal(value) / Decimal(10**self.scale)


class Money(FieldType[Decimal]):
    """Decimal money field stored as integer minor units via MinorUnits TypeDecorator.

    Values are quantized to ``scale`` decimal places (default 2) using ROUND_HALF_EVEN
    before storage. Reads return a ``Decimal`` with the same precision.
    """

    python_type = Decimal

    def __init__(self, scale: int = 2, **kw: Any) -> None:
        super().__init__(**kw)
        self.scale = scale

    def column_type(self) -> TypeEngine[Any]:
        """Return a ``MinorUnits`` TypeDecorator backed by ``BigInteger``."""
        return MinorUnits(scale=self.scale)

    def validate(self, value: Any) -> Decimal:
        """Validate and quantize ``value`` to ``scale`` decimal places."""
        try:
            dec = Decimal(str(value))
        except Exception as e:
            raise ValidationError(reason="not a valid decimal", value=value) from e
        quant = Decimal(1).scaleb(-self.scale)
        return dec.quantize(quant, ROUND_HALF_EVEN)


class _RangeMixin(FieldType[int]):
    """Shared validation for numeric range types with optional min/max bounds."""

    min_value: int | None = None
    max_value: int | None = None

    def validate(self, value: Any) -> Any:
        if self.min_value is not None and value < self.min_value:
            raise ValidationError(reason=f"must be >= {self.min_value}", value=value)
        if self.max_value is not None and value > self.max_value:
            raise ValidationError(reason=f"must be <= {self.max_value}", value=value)
        return value


class Positive(_RangeMixin):
    """Integer field that must be strictly positive (>= 1)."""

    python_type = int
    min_value = 1

    def column_type(self) -> TypeEngine[Any]:
        """Return ``BigInteger``."""
        return BigInteger()


class NonNegative(_RangeMixin):
    """Integer field that must be non-negative (>= 0)."""

    python_type = int
    min_value = 0

    def column_type(self) -> TypeEngine[Any]:
        """Return ``BigInteger``."""
        return BigInteger()


class Percent(_RangeMixin):
    """Integer field representing a percentage (0-100 inclusive)."""

    python_type = int
    min_value = 0
    max_value = 100

    def column_type(self) -> TypeEngine[Any]:
        """Return ``BigInteger``."""
        return BigInteger()


class Bounded(_RangeMixin):
    """Integer field with custom inclusive min/max bounds."""

    python_type = int

    def __init__(self, min: int, max: int, **kw: Any) -> None:
        super().__init__(**kw)
        self.min_value = min
        self.max_value = max

    def column_type(self) -> TypeEngine[Any]:
        """Return ``BigInteger``."""
        return BigInteger()


class RoundedDecimal(FieldType[Decimal]):
    """Decimal field stored as ``NUMERIC(38, places)`` and quantized to a fixed precision.

    Rounding uses ROUND_HALF_EVEN. Default precision is 2 decimal places.
    """

    python_type = Decimal

    def __init__(self, places: int = 2, **kw: Any) -> None:
        super().__init__(**kw)
        self.places = places

    def column_type(self) -> TypeEngine[Any]:
        """Return ``Numeric(38, places)``."""
        return Numeric(38, self.places)

    def validate(self, value: Any) -> Decimal:
        """Quantize ``value`` to ``places`` decimal places using ROUND_HALF_EVEN."""
        quant = Decimal(1).scaleb(-self.places)
        return Decimal(str(value)).quantize(quant, ROUND_HALF_EVEN)


class Version(FieldType[int]):
    """Optimistic-locking version counter, auto-injected by ``Meta.versioned``.

    Integer, NOT NULL, ``server_default`` 1 so non-ORM core inserts (e.g.
    ``bulk_upsert``) still produce a valid starting version. The increment is
    driven by SQLAlchemy's ``version_id_col`` - deliberately NO ``onupdate`` here.
    """

    python_type = int

    def __init__(self, **kw: Any) -> None:
        super().__init__(server_default=text("1"), **kw)

    def column_type(self) -> TypeEngine[Any]:
        """Return ``BigInteger``."""
        return BigInteger()
