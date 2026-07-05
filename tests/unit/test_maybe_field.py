from __future__ import annotations

from decimal import Decimal

from alchemiq import Model
from alchemiq.types import PK, Email, Maybe, Money, Nothing, Some
from alchemiq.types.maybe import MaybeField, _MaybeType
from alchemiq.types.strings import Email as EmailField


class Profile(Model):
    id: PK[int]
    nickname: Maybe[str]
    backup_email: Maybe[Email]


# ---------------------------------------------------------------------------
# Attribute-side tests (from brief)
# ---------------------------------------------------------------------------


def test_maybe_column_is_nullable():
    assert Profile.__table__.c.nickname.nullable is True


def test_assign_some_validates_inner():
    p = Profile()
    p.backup_email = Some("X@Y.com")
    assert p.backup_email == Some("x@y.com")


def test_assign_nothing():
    p = Profile()
    p.nickname = Nothing
    assert p.nickname is Nothing


def test_auto_wrap_raw_value():
    p = Profile()
    p.nickname = "neo"
    assert p.nickname == Some("neo")


def test_backup_email_column_is_nullable():
    assert Profile.__table__.c.backup_email.nullable is True


# ---------------------------------------------------------------------------
# MaybeField unit tests
# ---------------------------------------------------------------------------


def test_maybe_field_validate_nothing():
    from alchemiq.types.base import Field

    inner = Field()
    inner.python_type = str
    mf = MaybeField(inner)
    assert mf.validate(Nothing) is Nothing


def test_maybe_field_validate_some():
    inner = EmailField()
    mf = MaybeField(inner)
    result = mf.validate(Some("USER@EXAMPLE.COM"))
    assert result == Some("user@example.com")


def test_maybe_field_validate_none_becomes_nothing():
    from alchemiq.types.base import Field

    inner = Field()
    inner.python_type = str
    mf = MaybeField(inner)
    assert mf.validate(None) is Nothing


def test_maybe_field_validate_raw_auto_wraps():
    from alchemiq.types.base import Field

    inner = Field()
    inner.python_type = str
    mf = MaybeField(inner)
    assert mf.validate("hello") == Some("hello")


def test_maybe_field_is_nullable():
    from alchemiq.types.base import Field

    inner = Field()
    inner.python_type = str
    mf = MaybeField(inner)
    assert mf.config.nullable is True


# ---------------------------------------------------------------------------
# _MaybeType TypeDecorator bind/result tests
# ---------------------------------------------------------------------------


def test_maybe_type_bind_some_str():
    inner = EmailField()
    mt = _MaybeType(inner)
    assert mt.process_bind_param(Some("test@example.com"), None) == "test@example.com"


def test_maybe_type_bind_nothing():
    inner = EmailField()
    mt = _MaybeType(inner)
    assert mt.process_bind_param(Nothing, None) is None


def test_maybe_type_bind_none():
    inner = EmailField()
    mt = _MaybeType(inner)
    assert mt.process_bind_param(None, None) is None


def test_maybe_type_result_none_becomes_nothing():
    inner = EmailField()
    mt = _MaybeType(inner)
    assert mt.process_result_value(None, None) is Nothing


def test_maybe_type_result_value_becomes_some():
    inner = EmailField()
    mt = _MaybeType(inner)
    assert mt.process_result_value("user@example.com", None) == Some("user@example.com")


def test_maybe_type_bind_some_raw_str():
    from alchemiq.types.base import Field

    inner = Field()
    inner.python_type = str
    mt = _MaybeType(inner)
    assert mt.process_bind_param(Some("hello"), None) == "hello"


def test_maybe_type_result_raw_str():
    from alchemiq.types.base import Field

    inner = Field()
    inner.python_type = str
    mt = _MaybeType(inner)
    assert mt.process_result_value("hello", None) == Some("hello")


# ---------------------------------------------------------------------------
# _MaybeType nested TypeDecorator (Maybe[Money])
# ---------------------------------------------------------------------------


def test_maybe_type_bind_some_money():
    """Maybe[Money]: bind should unwrap Some, then apply MinorUnits transform."""
    inner = Money()
    mt = _MaybeType(inner)
    # Decimal("12.34") -> 1234 minor units
    result = mt.process_bind_param(Some(Decimal("12.34")), None)
    assert result == 1234


def test_maybe_type_bind_nothing_money():
    inner = Money()
    mt = _MaybeType(inner)
    assert mt.process_bind_param(Nothing, None) is None


def test_maybe_type_result_money():
    """Maybe[Money]: result should re-wrap via MinorUnits, then wrap in Some."""
    inner = Money()
    mt = _MaybeType(inner)
    result = mt.process_result_value(1234, None)
    assert result == Some(Decimal("12.34"))


def test_maybe_type_result_none_money():
    inner = Money()
    mt = _MaybeType(inner)
    assert mt.process_result_value(None, None) is Nothing
