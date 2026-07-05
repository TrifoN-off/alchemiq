import datetime as dt

import pytest
from clickhouse_sqlalchemy import types as ch

from alchemiq.clickhouse import ClickHouseModel, MergeTree, ReplacingMergeTree
from alchemiq.clickhouse.model import ch_engine_of
from alchemiq.clickhouse.types import DateTime64, UInt32


class _PageView(ClickHouseModel):
    event_time: dt.datetime = DateTime64(3)
    user_id: int = UInt32()
    url: str

    class Meta:
        engine = MergeTree(order_by=("event_time", "user_id"))


# --- Model with expression ORDER BY (R2-b fix) ---


class _ExprOrderByEvent(ClickHouseModel):
    """Model whose ORDER BY is a pure SQL expression, not a column name."""

    event_time: dt.datetime = DateTime64(3)
    user_id: int = UInt32()

    class Meta:
        tablename = "expr_order_by_event"
        engine = ReplacingMergeTree(order_by="toYYYYMM(event_time)")


# --- Model with all bare-annotation types (R2 type-injection test) ---


class _BareAnnotationTypes(ClickHouseModel):
    """All bare python-type annotations resolved to CH column types via _CHGenericField."""

    i: int
    s: str
    f: float
    b: bool
    d: dt.datetime
    dt_date: dt.date

    class Meta:
        tablename = "bare_annotation_types"
        engine = MergeTree(order_by="i")


@pytest.mark.unit
def test_model_tablename_snake_case():
    assert _PageView.__tablename__ == "_page_view"


@pytest.mark.unit
def test_model_fields_registered():
    assert set(_PageView.__alchemiq_fields__) == {"event_time", "user_id", "url"}


@pytest.mark.unit
def test_model_ch_column_types():
    cols = _PageView.__table__.c
    assert isinstance(cols.user_id.type, ch.UInt32)
    assert isinstance(cols.event_time.type, ch.DateTime64)
    assert isinstance(cols.url.type, ch.String)


@pytest.mark.unit
def test_model_engine_attached():
    e = ch_engine_of(_PageView)
    assert isinstance(e, MergeTree)
    assert e.order_by == ("event_time", "user_id")


@pytest.mark.unit
def test_model_on_separate_metadata():
    from alchemiq.clickhouse.registry import ch_metadata
    from alchemiq.model.registry import metadata as pg_metadata

    assert "_page_view" in ch_metadata.tables
    assert "_page_view" not in pg_metadata.tables


# ---------------------------------------------------------------------------
# New tests for R2-b (expression ORDER BY -> surrogate PK) and R2-c (layer sync)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_expression_order_by_builds_and_has_pk():
    """R2-b: expression ORDER BY must not leave the model PK-less.

    When all order_by entries are SQL expressions (not column names), _mark_order_by_as_pk
    must fall back to picking the first field as a surrogate SA PK so the mapper proceeds.
    pk_name() must return a real field name (not raise ConfigError).
    """
    from alchemiq.query.queryset import pk_name

    name = pk_name(_ExprOrderByEvent)
    # Must be one of the actual mapped field names (surrogate PK chosen from __alchemiq_fields__).
    assert name in _ExprOrderByEvent.__alchemiq_fields__


@pytest.mark.unit
def test_column_order_by_pk_name_and_config_in_sync():
    """R2-c: for a normal column-name ORDER BY, both SA and alchemiq layers must agree.

    pk_name() reads field.config.primary_key; it must return the first ORDER BY column,
    and that field's config.primary_key must be True (not just the SA column flag).
    """
    from alchemiq.query.queryset import pk_name

    pk = pk_name(_PageView)
    assert pk == "event_time"
    assert _PageView.__alchemiq_fields__["event_time"].config.primary_key is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "field_name, expected_type",
    [
        ("i", ch.Int64),
        ("s", ch.String),
        ("f", ch.Float64),
        ("b", ch.UInt8),
        ("d", ch.DateTime64),
        ("dt_date", ch.Date),
    ],
)
def test_bare_annotation_ch_column_types(field_name: str, expected_type: type) -> None:
    """Bare python-type annotations must map to the correct clickhouse_sqlalchemy column type."""
    col = _BareAnnotationTypes.__table__.c[field_name]
    assert isinstance(col.type, expected_type), (
        f"Field '{field_name}': expected {expected_type.__name__}, got {type(col.type).__name__}"
    )
