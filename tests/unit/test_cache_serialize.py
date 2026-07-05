from __future__ import annotations

import pytest

from alchemiq.cache import serialize
from tests.unit._cache_models import KItem

pytestmark = pytest.mark.unit


def test_secret_fields_detects_password_and_is_memoized() -> None:
    s1 = serialize.secret_fields(KItem)
    assert "secret" in s1  # Password field excluded
    assert "name" not in s1
    assert serialize.secret_fields(KItem) is s1  # memoized identity


def test_row_round_trip_omits_secret() -> None:
    item = KItem(id=1, name="al", secret="hunter2")
    encoded = serialize.encode_row(item)
    assert "hunter2" not in encoded
    back = serialize.decode_row(KItem, encoded)
    assert back.name == "al"
    assert getattr(back, "secret", None) is None  # excluded -> unset/None


def test_rows_round_trip() -> None:
    rows = [KItem(id=1, name="a", secret="x"), KItem(id=2, name="b", secret="y")]
    encoded = serialize.encode_rows(rows)
    back = serialize.decode_rows(KItem, encoded)
    assert [r.name for r in back] == ["a", "b"]


def test_int_and_bool_round_trip() -> None:
    assert serialize.decode_int(serialize.encode_int(42)) == 42
    assert serialize.decode_bool(serialize.encode_bool(True)) is True
    assert serialize.decode_bool(serialize.encode_bool(False)) is False
