"""Targeted unit tests to close coverage gaps found by the Task-13 gate pass."""

from __future__ import annotations

import datetime as dt

import pytest

from alchemiq.clickhouse import (
    ClickHouseModel,
    ClickHouseRepository,
    MergeTree,
    ReplacingMergeTree,
)
from alchemiq.clickhouse.connection import configure_clickhouse, dispose_clickhouse
from alchemiq.clickhouse.model import ch_engine_of
from alchemiq.clickhouse.publisher import ClickHousePublisher
from alchemiq.clickhouse.query import ClickHouseQuerySet
from alchemiq.clickhouse.repository import _insert_rows
from alchemiq.clickhouse.types import UInt32
from alchemiq.exceptions import ConfigError

# ─── shared model fixtures ───────────────────────────────────────────────────


class _Item(ClickHouseModel):
    id: int = UInt32()
    name: str

    class Meta:
        engine = MergeTree(order_by=("id",))


class _SoftItem(ClickHouseModel):
    id: int = UInt32()

    class Meta:
        soft_delete = True
        engine = ReplacingMergeTree(order_by=("id",))


# ─── connection.py lines 34, 40 ──────────────────────────────────────────────


@pytest.mark.unit
async def test_configure_with_dsn_stored():
    """Line 34: dsn kwarg is stored in _config."""
    import alchemiq.clickhouse.connection as _conn

    configure_clickhouse(dsn="clickhouse://localhost:8123/default")
    assert _conn._config is not None and "dsn" in _conn._config
    await dispose_clickhouse()


@pytest.mark.unit
async def test_configure_with_settings_stored():
    """Line 40: settings kwarg is stored in _config."""
    import alchemiq.clickhouse.connection as _conn

    configure_clickhouse(host="localhost", settings={"max_threads": 4})
    assert _conn._config is not None and "settings" in _conn._config
    await dispose_clickhouse()


# ─── engines.py lines 34, 36 ─────────────────────────────────────────────────


@pytest.mark.unit
def test_engine_clause_with_primary_key():
    """Line 34: PRIMARY KEY is rendered when primary_key is set."""
    e = MergeTree(order_by="id", primary_key="id")
    assert "PRIMARY KEY id" in e.engine_clause()


@pytest.mark.unit
def test_engine_clause_with_sample_by():
    """Line 36: SAMPLE BY is rendered when sample_by is set."""
    e = MergeTree(order_by="id", sample_by="rand()")
    assert "SAMPLE BY rand()" in e.engine_clause()


@pytest.mark.unit
def test_cols_none_returns_none():
    """Line 9: _cols(None) returns None (used internally by engine_clause)."""
    from alchemiq.clickhouse.engines import _cols

    assert _cols(None) is None


# ─── model.py lines 143, 166-167, 172 ───────────────────────────────────────


@pytest.mark.unit
def test_ch_engine_of_raises_when_no_engine():
    """Line 143: ch_engine_of raises ConfigError for plain class without engine."""

    class _NoEngine:
        pass

    with pytest.raises(ConfigError, match="has no Meta.engine"):
        ch_engine_of(_NoEngine)


@pytest.mark.unit
def test_abstract_subclass_is_allowed():
    """Lines 166-167: abstract intermediate subclass does not need Meta.engine."""

    class _AbstractBase(ClickHouseModel):
        __abstract__ = True

    # Should not raise - abstract branch returns early.
    assert _AbstractBase.__abstract__ is True


@pytest.mark.unit
def test_no_meta_engine_raises_config_error():
    """Line 172: ConfigError when ClickHouseModel subclass has no Meta.engine."""
    with pytest.raises(ConfigError, match="require Meta.engine"):

        class _Bad(ClickHouseModel):
            id: int = UInt32()

            class Meta:
                pass  # no engine


# ─── types.py lines 126-127 ──────────────────────────────────────────────────


@pytest.mark.unit
def test_scalar_ch_unknown_type_raises():
    """Lines 126-127: ConfigError for a Python type with no CH mapping."""
    from alchemiq.clickhouse.types import _scalar_ch

    with pytest.raises(ConfigError, match="No default ClickHouse type"):
        _scalar_ch(bytes)


# ─── publisher.py lines 27, 31 ───────────────────────────────────────────────


@pytest.mark.unit
def test_publisher_custom_mapper_used():
    """Line 27: _to_row returns custom mapper result when mapper is provided."""
    from alchemiq.outbox.message import OutboxMessage

    publisher = ClickHousePublisher(_Item, mapper=lambda m: {"id": 99, "name": "x"})
    # OutboxMessage only needs the fields listed in _FIELDS; supply minimal required.
    msg = OutboxMessage(
        id="1",
        topic="t",
        payload=b"{}",
        headers={},
        aggregate_type="A",
        aggregate_id="1",
        event_type="E",
    )
    row = publisher._to_row(msg)
    assert row == {"id": 99, "name": "x"}


@pytest.mark.unit
async def test_publisher_publish_delegates_to_publish_batch(monkeypatch):
    """Line 31: publish() forwards to publish_batch()."""
    from alchemiq.outbox.message import OutboxMessage

    captured: list = []

    async def _fake_batch(msgs: list) -> None:
        captured.extend(msgs)

    msg = OutboxMessage(
        id="2",
        topic="t",
        payload=b"{}",
        headers={},
        aggregate_type="A",
        aggregate_id="2",
        event_type="E",
    )

    publisher = ClickHousePublisher(_Item)
    monkeypatch.setattr(publisher, "publish_batch", _fake_batch)
    await publisher.publish(msg)
    assert msg in captured


# ─── query.py lines 85, 89, 99 ───────────────────────────────────────────────


@pytest.mark.unit
def test_queryset_final_sets_flag():
    """Line 85: final() returns a clone with _final=True."""
    qs = ClickHouseQuerySet(_Item).final()
    assert qs._final is True


@pytest.mark.unit
def test_with_deleted_raises_on_non_soft_delete():
    """Line 89: with_deleted() raises ConfigError on non-soft-delete model."""
    qs = ClickHouseQuerySet(_Item)
    with pytest.raises(ConfigError, match="not soft-delete"):
        qs.with_deleted()


@pytest.mark.unit
def test_only_deleted_raises_on_non_soft_delete():
    """Line 99: only_deleted() raises ConfigError on non-soft-delete model."""
    qs = ClickHouseQuerySet(_Item)
    with pytest.raises(ConfigError, match="not soft-delete"):
        qs.only_deleted()


# ─── repository.py delegate methods (lines 104,110,113,116,119,122,131,134) ──


@pytest.mark.unit
def test_repository_exclude_returns_queryset():
    """Line 104: exclude() returns a ClickHouseQuerySet."""
    repo = ClickHouseRepository(_Item)
    assert isinstance(repo.exclude(id=1), ClickHouseQuerySet)


@pytest.mark.unit
def test_repository_limit_returns_queryset():
    """Line 110: limit() returns a ClickHouseQuerySet."""
    assert isinstance(ClickHouseRepository(_Item).limit(10), ClickHouseQuerySet)


@pytest.mark.unit
def test_repository_offset_returns_queryset():
    """Line 113: offset() returns a ClickHouseQuerySet."""
    assert isinstance(ClickHouseRepository(_Item).offset(5), ClickHouseQuerySet)


@pytest.mark.unit
def test_repository_distinct_returns_queryset():
    """Line 116: distinct() returns a ClickHouseQuerySet."""
    assert isinstance(ClickHouseRepository(_Item).distinct(), ClickHouseQuerySet)


@pytest.mark.unit
def test_repository_only_returns_queryset():
    """Line 119: only() returns a ClickHouseQuerySet."""
    assert isinstance(ClickHouseRepository(_Item).only("id"), ClickHouseQuerySet)


@pytest.mark.unit
def test_repository_final_returns_queryset():
    """Line 122: final() returns a ClickHouseQuerySet with _final=True."""
    qs = ClickHouseRepository(_Item).final()
    assert isinstance(qs, ClickHouseQuerySet)
    assert qs._final is True


@pytest.mark.unit
def test_repository_with_deleted_propagates_config_error():
    """Line 131: with_deleted() on non-soft-delete raises ConfigError."""
    with pytest.raises(ConfigError, match="not soft-delete"):
        ClickHouseRepository(_Item).with_deleted()


@pytest.mark.unit
def test_repository_only_deleted_propagates_config_error():
    """Line 134: only_deleted() on non-soft-delete raises ConfigError."""
    with pytest.raises(ConfigError, match="not soft-delete"):
        ClickHouseRepository(_Item).only_deleted()


# ─── repository.py line 92 ───────────────────────────────────────────────────


@pytest.mark.unit
def test_repository_no_model_raises_type_error():
    """Line 92: ClickHouseRepository() with no model raises TypeError."""
    with pytest.raises(TypeError, match="needs a model"):
        ClickHouseRepository()  # type: ignore[call-arg]


# ─── repository.py line 67 ───────────────────────────────────────────────────


@pytest.mark.unit
async def test_insert_rows_empty_list_returns_early():
    """Line 67: _insert_rows returns immediately for empty list (no CH call)."""
    # Safe even without CH configured - the early return at line 67 fires before
    # get_clickhouse_client() is called.
    await _insert_rows(_Item, [])


# ─── repository.py lines 45-46, 54, 57-59: _col_value edge cases ─────────────


@pytest.mark.unit
def test_col_value_zero_arg_callable_default():
    """Lines 45-46: 0-arg lambda default (TypeError path) returns its result."""
    from sqlalchemy import Column, Integer

    from alchemiq.clickhouse.repository import _col_value

    col = Column("x", Integer(), default=lambda: 42)
    # SA attaches a ColumnDefault whose .arg is the lambda.
    # col.default is None until the Column is part of a Table; let's simulate.
    from sqlalchemy.sql.schema import ColumnDefault

    col.default = ColumnDefault(lambda: 42)  # type: ignore[assignment]

    class _Obj:
        x = None

    result = _col_value(_Obj(), col)
    assert result == 42


@pytest.mark.unit
def test_col_value_nullable_ch_type_returns_none():
    """Line 54: non-nullable SA col whose CH type is Nullable(...) returns None."""
    from clickhouse_sqlalchemy import types as ch
    from sqlalchemy import Column

    from alchemiq.clickhouse.repository import _col_value

    col = Column("x", ch.Nullable(ch.UInt32()), nullable=False)

    class _Obj:
        x = None

    assert _col_value(_Obj(), col) is None


@pytest.mark.unit
def test_col_value_datetime64_returns_epoch():
    """Lines 57-58: non-nullable DateTime64 col without default returns epoch datetime."""
    from clickhouse_sqlalchemy import types as ch
    from sqlalchemy import Column

    from alchemiq.clickhouse.repository import _col_value

    col = Column("ts", ch.DateTime64(3), nullable=False)

    class _Obj:
        ts = None

    result = _col_value(_Obj(), col)
    assert result == dt.datetime(1970, 1, 1, tzinfo=dt.UTC)


@pytest.mark.unit
def test_col_value_numeric_type_returns_zero():
    """Line 59: non-nullable UInt32 col without default returns 0."""
    from clickhouse_sqlalchemy import types as ch
    from sqlalchemy import Column

    from alchemiq.clickhouse.repository import _col_value

    col = Column("n", ch.UInt32(), nullable=False)

    class _Obj:
        n = None

    assert _col_value(_Obj(), col) == 0
