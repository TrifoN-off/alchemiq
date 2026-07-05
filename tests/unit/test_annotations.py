from alchemiq._internal.annotations import resolve_field
from alchemiq.types.base import _MISSING, Field, FieldType


class FakeStr(FieldType):
    python_type = str

    def column_type(self):
        from sqlalchemy import String

        return String()


def test_plain_type_becomes_generic_field():
    f = resolve_field("name", str, _MISSING)
    assert isinstance(f, Field)
    assert f.python_type is str
    assert f.config.nullable is False


def test_optional_sets_nullable():
    f = resolve_field("name", str | None, _MISSING)
    assert f.python_type is str
    assert f.config.nullable is True


def test_plain_literal_becomes_default():
    f = resolve_field("count", int, 0)
    assert f.python_type is int
    assert f.config.default == 0


def test_semantic_type_class_is_instantiated():
    f = resolve_field("email", FakeStr, _MISSING)
    assert isinstance(f, FakeStr)
    assert f.python_type is str


def test_value_descriptor_wins():
    desc = Field(max_length=100, unique=True)
    f = resolve_field("name", str, desc)
    assert f is desc
    assert f.python_type is str  # filled from annotation
