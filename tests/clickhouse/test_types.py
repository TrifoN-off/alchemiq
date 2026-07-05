import datetime as dt
from decimal import Decimal
from uuid import UUID

import pytest
from clickhouse_sqlalchemy import types as ch

from alchemiq.clickhouse.types import (
    DateTime64,
    Enum8,
    Float32,
    Int16,
    LowCardinality,
    UInt32,
    ch_column_type,
)


@pytest.mark.unit
def test_uint32_column_type():
    f = UInt32()
    assert f.python_type is int
    assert isinstance(f.column_type(), ch.UInt32)


@pytest.mark.unit
def test_datetime64_precision():
    f = DateTime64(6)
    assert f.python_type is dt.datetime
    col = f.column_type()
    assert isinstance(col, ch.DateTime64)
    assert col.precision == 6


@pytest.mark.unit
def test_lowcardinality_wraps_string():
    f = LowCardinality()
    assert f.python_type is str
    assert isinstance(f.column_type(), ch.LowCardinality)


@pytest.mark.unit
def test_enum8_members():
    f = Enum8({"a": 1, "b": 2})
    assert f.python_type is str
    col = f.column_type()
    assert isinstance(col, ch.Enum8)
    members = {m.name: m.value for m in col.enum_class}
    assert members == {"a": 1, "b": 2}


@pytest.mark.unit
@pytest.mark.parametrize(
    "py,expected",
    [
        (int, ch.Int64),
        (str, ch.String),
        (float, ch.Float64),
        (bool, ch.UInt8),
        (dt.datetime, ch.DateTime64),
        (dt.date, ch.Date),
    ],
)
def test_default_python_to_ch_map(py, expected):
    assert isinstance(ch_column_type(py), expected)


@pytest.mark.unit
def test_int16_and_float32():
    assert isinstance(Int16().column_type(), ch.Int16)
    assert isinstance(Float32().column_type(), ch.Float32)


@pytest.mark.unit
def test_ch_column_type_decimal():
    col = ch_column_type(Decimal)
    assert isinstance(col, ch.Decimal)
    assert col.precision == 38
    assert col.scale == 9


@pytest.mark.unit
def test_ch_column_type_uuid():
    col = ch_column_type(UUID)
    assert isinstance(col, ch.UUID)
