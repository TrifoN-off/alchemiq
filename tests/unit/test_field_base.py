import dataclasses

import pytest
from sqlalchemy import String

from alchemiq.types.base import _MISSING, Field, FieldConfig


def test_field_stores_knobs():
    f = Field(max_length=100, unique=True, index=True)
    assert f.config.unique is True
    assert f.config.index is True
    assert f.config.default is _MISSING


def test_field_config_is_frozen():
    cfg = FieldConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.unique = True  # type: ignore[misc]


def test_field_column_type_uses_max_length():
    f = Field(max_length=50)
    f.python_type = str
    col_type = f.column_type()
    assert isinstance(col_type, String)
    assert col_type.length == 50


def test_fieldtype_validate_is_identity_by_default():
    f = Field()
    f.python_type = str
    assert f.validate("x") == "x"
