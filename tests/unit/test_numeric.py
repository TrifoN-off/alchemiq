from decimal import Decimal

import pytest

from alchemiq.exceptions import ValidationError
from alchemiq.types import Bounded, NonNegative, Percent, Positive, RoundedDecimal


def test_positive_rejects_zero():
    with pytest.raises(ValidationError):
        Positive().validate(0)
    assert Positive().validate(5) == 5


def test_non_negative_allows_zero():
    assert NonNegative().validate(0) == 0
    with pytest.raises(ValidationError):
        NonNegative().validate(-1)


def test_percent_bounds():
    assert Percent().validate(100) == 100
    with pytest.raises(ValidationError):
        Percent().validate(101)


def test_percent_lower_bound():
    assert Percent().validate(0) == 0
    with pytest.raises(ValidationError):
        Percent().validate(-1)


def test_bounded_inclusive():
    b = Bounded(0, 10)
    assert b.validate(10) == 10
    with pytest.raises(ValidationError):
        b.validate(11)


def test_bounded_lower_bound():
    b = Bounded(0, 10)
    assert b.validate(0) == 0
    with pytest.raises(ValidationError):
        b.validate(-1)


def test_rounded_decimal_quantizes():
    assert RoundedDecimal(places=2).validate("1.005") == Decimal("1.00")
