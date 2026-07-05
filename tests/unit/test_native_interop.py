from __future__ import annotations

import pytest
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from alchemiq import Model
from alchemiq.fastapi.schemas import create_schema
from alchemiq.types import PK
from alchemiq.types.base import _NativeField

pytestmark = pytest.mark.unit


class _Native(Model):
    __tablename__ = "native_unit_native"
    id: PK[int]
    name: str
    payload: Mapped[dict | None] = mapped_column(JSONB)
    label: Mapped[str] = mapped_column(String(50))
    # non-optional annotation but explicit nullable=True on the column
    extra: Mapped[dict] = mapped_column(JSONB, nullable=True)


class _BareNative(Model):
    __tablename__ = "native_unit_bare"
    id: PK[int]
    note: Mapped[str | None]  # bare Mapped, no mapped_column value - SA infers the column


def test_native_field_registered() -> None:
    assert isinstance(_Native.__alchemiq_fields__["payload"], _NativeField)
    assert isinstance(_Native.__alchemiq_fields__["label"], _NativeField)


def test_native_field_python_type() -> None:
    assert _Native.__alchemiq_fields__["payload"].python_type is dict
    assert _Native.__alchemiq_fields__["label"].python_type is str


def test_native_field_nullable_reconciled_from_column() -> None:
    assert _Native.__alchemiq_fields__["payload"].config.nullable is True
    assert _Native.__alchemiq_fields__["label"].config.nullable is False


def test_native_explicit_nullable_override_reconciled() -> None:
    # non-optional annotation but explicit nullable=True: reconcile reads the real column (True),
    # which pure-annotation inference would get wrong.
    assert _Native.__alchemiq_fields__["extra"].config.nullable is True


def test_bare_mapped_native_registered() -> None:
    assert isinstance(_BareNative.__alchemiq_fields__["note"], _NativeField)
    assert _BareNative.__alchemiq_fields__["note"].config.nullable is True


def test_alchemiq_field_coexists_with_native() -> None:
    assert "name" in _Native.__alchemiq_fields__
    assert not isinstance(_Native.__alchemiq_fields__["name"], _NativeField)


def test_native_field_no_eager_validation() -> None:
    # escape hatch: no FieldType.validate set-listener is attached, so any value assigns cleanly
    obj = _Native(id=1, name="a", label="x", payload={"any": "thing"})
    obj.payload = {"k": [1, 2, 3]}
    assert obj.payload == {"k": [1, 2, 3]}


def test_native_field_in_pydantic_schema() -> None:
    schema = _Native.to_schema()
    assert "payload" in schema.model_fields
    assert "label" in schema.model_fields


def test_native_field_in_fastapi_create_schema() -> None:
    schema = create_schema(_Native)
    assert "payload" in schema.model_fields
    assert "label" in schema.model_fields
