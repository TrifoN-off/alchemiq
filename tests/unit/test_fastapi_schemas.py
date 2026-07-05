"""Hybrid schema derivation from a model's field catalog."""

from __future__ import annotations

import pytest

from alchemiq import Model
from alchemiq.fastapi.schemas import (
    create_schema,
    page_schema,
    pk_name,
    read_schema,
    update_schema,
)
from alchemiq.types import PK, Password
from alchemiq.types.temporal import DateTimeTz

pytestmark = pytest.mark.unit


class FapiSchemaWidget(Model):
    __tablename__ = "fapi_schema_widget"
    id: PK[int]
    name: str
    secret: Password
    note: str | None

    class Meta:
        timestamps = True  # auto-injects created_at / updated_at (server_default)


def test_pk_name() -> None:
    assert pk_name(FapiSchemaWidget) == "id"


def test_read_schema_omits_password_keeps_pk_and_timestamps() -> None:
    fields = read_schema(FapiSchemaWidget).model_fields
    assert "secret" not in fields
    assert {"id", "name", "note", "created_at", "updated_at"} <= set(fields)


def test_create_schema_excludes_pk_and_server_defaults_includes_password() -> None:
    fields = create_schema(FapiSchemaWidget).model_fields
    assert set(fields) == {"name", "secret", "note"}
    assert fields["name"].is_required()
    assert fields["secret"].is_required()
    assert not fields["note"].is_required()  # nullable -> optional


def test_update_schema_same_fields_all_optional() -> None:
    fields = update_schema(FapiSchemaWidget).model_fields
    assert set(fields) == {"name", "secret", "note"}
    assert all(not f.is_required() for f in fields.values())


def test_page_schema_shape() -> None:
    page = page_schema(read_schema(FapiSchemaWidget))
    assert set(page.model_fields) == {
        "items",
        "total",
        "page",
        "size",
        "pages",
        "has_next",
        "has_prev",
    }


def test_schemas_are_cached() -> None:
    assert create_schema(FapiSchemaWidget) is create_schema(FapiSchemaWidget)
    assert update_schema(FapiSchemaWidget) is update_schema(FapiSchemaWidget)
    read = read_schema(FapiSchemaWidget)
    assert page_schema(read) is page_schema(read)


class FapiSchemaPlainDeletedAt(Model):
    __tablename__ = "fapi_schema_plain_deleted_at"
    id: PK[int]
    name: str
    deleted_at: DateTimeTz | None  # a normal user column, NOT soft-delete


def test_writable_keeps_deleted_at_on_non_soft_model() -> None:
    fields = create_schema(FapiSchemaPlainDeletedAt).model_fields
    assert "deleted_at" in fields  # not stripped - model is not soft-delete
