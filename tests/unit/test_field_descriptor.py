import enum

import pytest

from alchemiq import Model
from alchemiq.types import PK
from alchemiq.types.base import Field, FieldType
from alchemiq.types.special import Enum as AlchemiqEnum


class _Color(enum.Enum):
    RED = "red"
    BLUE = "blue"


@pytest.mark.unit
def test_fieldtype_is_generic():
    # FieldType must be subscriptable (Generic[T]) so concrete types can bind T.
    assert FieldType[int] is not None


@pytest.mark.unit
def test_descriptor_stubs_are_typing_only():
    # The __get__/__set__ stubs exist ONLY for type checkers (under TYPE_CHECKING),
    # so FieldType instances are never real descriptors at runtime.
    assert not hasattr(FieldType, "__get__")
    assert not hasattr(FieldType, "__set__")


@pytest.mark.unit
def test_generic_field_runtime_unchanged():
    f = Field()
    f.python_type = int
    assert f.python_type is int
    assert f.build_column() is not None


@pytest.mark.unit
def test_enum_subscript_builds_runtime_instance():
    # Enum[Color] must evaluate to a configured Enum instance at runtime (like PK[int]).
    field = AlchemiqEnum[_Color]
    assert isinstance(field, AlchemiqEnum)
    assert field.enum_cls is _Color


@pytest.mark.unit
def test_enum_subscript_model_builds_and_validates():
    class _M(Model):
        __tablename__ = "td_enum_subscript"
        id: PK[int]
        status: AlchemiqEnum[_Color]

    m = _M(status=_Color.RED)
    assert m.status is _Color.RED
    assert "status" in _M.__alchemiq_fields__
