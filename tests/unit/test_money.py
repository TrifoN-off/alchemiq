from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from alchemiq import Model
from alchemiq.types import PK, Money
from alchemiq.types.numeric import MinorUnits


class Wallet(Model):
    id: PK[int]
    balance: Money


def test_money_column_is_biginteger_decorator():
    deco = Wallet.__table__.c.balance.type
    assert isinstance(deco, MinorUnits)


def test_bind_converts_decimal_to_minor_units():
    deco = MinorUnits(scale=2)
    assert deco.process_bind_param(Decimal("12.34"), dialect=None) == 1234


def test_result_converts_minor_units_to_decimal():
    deco = MinorUnits(scale=2)
    assert deco.process_result_value(1234, dialect=None) == Decimal("12.34")


def test_validate_quantizes():
    m = Money()
    # 1.005 with ROUND_HALF_EVEN rounds to 1.00 (rounds to even digit)
    assert m.validate("1.005") == Decimal("1.00")


def test_validate_coerces_string():
    m = Money()
    assert m.validate("42.50") == Decimal("42.50")


def test_validate_rejects_non_decimal():
    m = Money()
    from alchemiq.exceptions import ValidationError

    with pytest.raises(ValidationError):
        m.validate("not-a-number")


def test_bind_none_returns_none():
    deco = MinorUnits(scale=2)
    assert deco.process_bind_param(None, dialect=None) is None


def test_result_none_returns_none():
    deco = MinorUnits(scale=2)
    assert deco.process_result_value(None, dialect=None) is None


# Bounded money range: -999_999.99 to 999_999.99 with exactly 2 decimal places
_MONEY_STRATEGY = st.decimals(
    min_value=Decimal("-999999.99"),
    max_value=Decimal("999999.99"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


@settings(max_examples=200)
@given(value=_MONEY_STRATEGY)
def test_minor_units_round_trip(value: Decimal) -> None:
    """MinorUnits must be lossless for exact 2-decimal-place values."""
    deco = MinorUnits(scale=2)
    bound = deco.process_bind_param(value, None)
    result = deco.process_result_value(bound, None)
    assert result == value
