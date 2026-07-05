import pytest

from alchemiq import Model
from alchemiq.exceptions import ValidationError
from alchemiq.types import PK, Email


class Account(Model):
    id: PK[int]
    email: Email


def test_email_normalized_on_assignment():
    a = Account()
    a.email = "JOHN@Example.COM"
    assert a.email == "john@example.com"


def test_bad_email_raises_immediately():
    a = Account()
    with pytest.raises(ValidationError) as ei:
        a.email = "not-an-email"
    assert ei.value.field == "email"


def test_constructor_aggregates_errors():
    with pytest.raises(ValidationError) as ei:
        Account(email="nope")
    # single bad field -> single error passthrough
    assert ei.value.field == "email"


def test_valid_construction():
    a = Account(email="A@B.com")
    assert a.email == "a@b.com"


class TwoEmailAccount(Model):
    id: PK[int]
    email: Email
    alt_email: Email


def test_constructor_aggregates_multiple_errors():
    with pytest.raises(ValidationError) as ei:
        TwoEmailAccount(email="bad-email", alt_email="also-bad")
    err = ei.value
    assert len(err.errors) == 2
    fields = {e.field for e in err.errors}
    assert fields == {"email", "alt_email"}
