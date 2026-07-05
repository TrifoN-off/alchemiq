from __future__ import annotations

import pytest

from alchemiq import Model
from alchemiq.exceptions import InvalidCursorError
from alchemiq.query.cursor import (
    build_seek,
    decode_cursor,
    effective_order,
    encode_cursor,
    reverse_order,
)
from alchemiq.types import PK

pytestmark = pytest.mark.unit


class CursorUnitRow(Model):
    __tablename__ = "cursor_unit_row"
    id: PK[int]
    score: int


def test_effective_order_defaults_to_pk() -> None:
    assert effective_order(CursorUnitRow, ()) == ("id",)


def test_effective_order_appends_pk_tiebreaker() -> None:
    assert effective_order(CursorUnitRow, ("-score",)) == ("-score", "id")


def test_effective_order_keeps_pk_when_present() -> None:
    assert effective_order(CursorUnitRow, ("id",)) == ("id",)


def test_reverse_order() -> None:
    assert reverse_order(("-score", "id")) == ("score", "-id")


def test_encode_decode_round_trip() -> None:
    row = CursorUnitRow(id=7, score=42)
    token = encode_cursor(CursorUnitRow, ("score", "id"), row)
    assert decode_cursor(token, CursorUnitRow, ("score", "id")) == [42, 7]


def test_decode_rejects_bad_base64() -> None:
    with pytest.raises(InvalidCursorError):
        decode_cursor("!!!not base64!!!", CursorUnitRow, ("id",))


def test_decode_rejects_field_mismatch() -> None:
    row = CursorUnitRow(id=7, score=42)
    token = encode_cursor(CursorUnitRow, ("id",), row)
    with pytest.raises(InvalidCursorError):
        decode_cursor(token, CursorUnitRow, ("score",))  # order changed -> stale cursor


def test_build_seek_forward_ascending_uses_gt() -> None:
    sql = str(build_seek(CursorUnitRow, ("id",), [5], backward=False))
    assert ">" in sql and "<" not in sql


def test_build_seek_forward_descending_uses_lt() -> None:
    sql = str(build_seek(CursorUnitRow, ("-id",), [5], backward=False))
    assert "<" in sql
