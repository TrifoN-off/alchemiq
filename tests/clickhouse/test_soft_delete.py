"""Tests for ClickHouse-native soft-delete via ReplacingMergeTree(ver, is_deleted)."""

from __future__ import annotations

import pytest
from clickhouse_sqlalchemy import types as ch  # ty: ignore[unresolved-import]

from alchemiq.clickhouse import ClickHouseModel, ClickHouseRepository, ReplacingMergeTree
from alchemiq.clickhouse.model import ch_engine_of
from alchemiq.clickhouse.query import ClickHouseQuerySet, render_sql
from alchemiq.clickhouse.types import UInt32
from alchemiq.exceptions import ConfigError, UnsupportedOperationError


class _Doc(ClickHouseModel):
    key: int = UInt32()
    body: str

    class Meta:
        soft_delete = True
        engine = ReplacingMergeTree(order_by=("key",))


# Composite-key soft-delete model for ORDER BY guard tests.
class _DocComposite(ClickHouseModel):
    key: int = UInt32()
    tenant_id: int = UInt32()
    body: str

    class Meta:
        soft_delete = True
        engine = ReplacingMergeTree(order_by=("key", "tenant_id"))


# Integration model: includes the experimental CLEANUP setting (R4).
class _Note(ClickHouseModel):
    key: int = UInt32()
    body: str

    class Meta:
        soft_delete = True
        engine = ReplacingMergeTree(
            order_by=("key",),
            settings={"allow_experimental_replacing_merge_with_cleanup": 1},
        )


# ── unit: column injection ──────────────────────────────────────────────────


@pytest.mark.unit
def test_soft_delete_injects_columns():
    cols = _Doc.__table__.c
    assert isinstance(cols.is_deleted.type, ch.UInt8)
    assert isinstance(cols._version.type, ch.DateTime64)
    assert "deleted_at" in cols


@pytest.mark.unit
def test_soft_delete_rebuilds_engine_with_ver_and_flag():
    e = ch_engine_of(_Doc)
    assert isinstance(e, ReplacingMergeTree)
    assert e.version == "_version"
    assert e.is_deleted == "is_deleted"
    assert "ReplacingMergeTree(_version, is_deleted)" in e.engine_clause()


@pytest.mark.unit
def test_soft_delete_preserves_user_settings_on_engine_rebuild():
    """R4: dataclasses.replace preserves settings= so CLEANUP setting survives."""
    e = ch_engine_of(_Note)
    assert e.settings == {"allow_experimental_replacing_merge_with_cleanup": 1}
    clause = e.engine_clause()
    assert "allow_experimental_replacing_merge_with_cleanup = 1" in clause


@pytest.mark.unit
def test_soft_delete_requires_replacing_merge_tree():
    with pytest.raises(ConfigError):

        class _Bad(ClickHouseModel):
            key: int = UInt32()

            class Meta:
                soft_delete = True
                from alchemiq.clickhouse import MergeTree

                engine = MergeTree(order_by=("key",))


# ── unit: FINAL rendering ────────────────────────────────────────────────────


@pytest.mark.unit
def test_soft_delete_read_renders_final():
    """The rendered SQL for a soft-delete model must contain FROM <table> FINAL."""
    qs = ClickHouseQuerySet(_Doc)
    sql = render_sql(qs)
    # Must contain FINAL after the FROM clause and before WHERE (or end).
    assert "FROM _doc" in sql
    assert "FINAL" in sql
    from_idx = sql.index("FROM _doc")
    final_idx = sql.index("FINAL")
    assert final_idx > from_idx, "FINAL must appear after FROM _doc"


@pytest.mark.unit
def test_soft_delete_read_filters_deleted_at():
    """Default read (EXCLUDE mode) must filter deleted_at IS NULL."""
    qs = ClickHouseQuerySet(_Doc)
    sql = render_sql(qs)
    assert "deleted_at IS NULL" in sql


@pytest.mark.unit
def test_with_deleted_no_final_no_deleted_at_filter():
    """with_deleted() must NOT use FINAL and must NOT add any deleted_at predicate.
    INCLUDE mode means both live and tombstone rows are returned from the raw
    un-collapsed history; deleted_predicate() returns None for INCLUDE."""
    qs = ClickHouseQuerySet(_Doc).with_deleted()
    sql = render_sql(qs)
    assert "FINAL" not in sql
    assert "deleted_at IS" not in sql  # INCLUDE: no deleted_at predicate at all


@pytest.mark.unit
def test_only_deleted_no_final_and_is_not_null():
    """only_deleted() must NOT use FINAL and must filter deleted_at IS NOT NULL."""
    qs = ClickHouseQuerySet(_Doc).only_deleted()
    sql = render_sql(qs)
    assert "FINAL" not in sql
    assert "IS NOT NULL" in sql


# ── integration: full round-trip ─────────────────────────────────────────────


@pytest.mark.clickhouse
async def test_delete_hidden_then_cleanup_removes(configured_clickhouse):
    repo = ClickHouseRepository(_Note)
    await repo.insert(_Note(key=1, body="hello"))
    assert await repo.count() == 1  # FINAL + deleted_at IS NULL

    await repo.delete(key=1)  # tombstone insert
    assert await repo.count() == 0  # hidden under FINAL + deleted_at IS NULL
    # No FINAL, INCLUDE mode: raw history shows 2 physical rows (live + tombstone).
    assert await repo.with_deleted().count() == 2
    # No FINAL, ONLY mode: just the tombstone row (deleted_at IS NOT NULL).
    assert await repo.only_deleted().count() == 1

    await repo.cleanup()  # OPTIMIZE ... FINAL CLEANUP
    # CLEANUP purges all physical rows for the deleted key; 0 rows remain.
    assert await repo.with_deleted().count() == 0


@pytest.mark.clickhouse
async def test_with_deleted_includes_live_rows(configured_clickhouse):
    """with_deleted() must include live (never-deleted) rows - this test would have
    caught the ONLY/INCLUDE bug where with_deleted() hid live rows entirely."""
    repo = ClickHouseRepository(_Note)
    await repo.insert(_Note(key=10, body="alive"))  # never deleted
    assert await repo.count() == 1  # normal FINAL read: 1 live
    # INCLUDE mode: live row visible (was 0 under the ONLY bug)
    assert await repo.with_deleted().count() == 1
    assert await repo.only_deleted().count() == 0  # ONLY: no tombstones


@pytest.mark.clickhouse
async def test_restore_inserts_live_row(configured_clickhouse):
    """Line 221: restore() inserts a tombstone with is_deleted=0, making row visible."""
    repo = ClickHouseRepository(_Note)
    await repo.insert(_Note(key=20, body="data"))
    await repo.delete(key=20)
    assert await repo.count() == 0  # hidden after delete

    await repo.restore(key=20)
    # After OPTIMIZE FINAL, ReplacingMergeTree collapses to the latest version.
    await repo.cleanup()
    assert await repo.count() == 1  # restored row is now visible again


# ── unit: composite ORDER BY key guard ──────────────────────────────────────


@pytest.mark.unit
async def test_delete_composite_key_partial_raises():
    """delete() with only part of a composite ORDER BY key must raise UnsupportedOperationError.

    Without this guard, _tombstone() would fill the missing column with a zero-value,
    producing a tombstone on a different sorting key - the live row would remain visible
    and a spurious row would be inserted (silent data bug).
    """
    repo = ClickHouseRepository(_DocComposite)
    with pytest.raises(UnsupportedOperationError, match="tenant_id"):
        await repo.delete(key=1)  # tenant_id missing -> must raise, not silently mis-delete


@pytest.mark.unit
async def test_restore_composite_key_partial_raises():
    """restore() with only part of a composite ORDER BY key must raise UnsupportedOperationError."""
    repo = ClickHouseRepository(_DocComposite)
    with pytest.raises(UnsupportedOperationError, match="tenant_id"):
        await repo.restore(key=1)  # tenant_id missing -> must raise


@pytest.mark.clickhouse
async def test_delete_composite_key_full_collapses(configured_clickhouse):
    """delete(key=1, tenant_id=7) inserts a correctly-keyed tombstone; FINAL hides the row.

    This verifies the full-key path: the tombstone lands on the exact same sorting key
    as the live row so ReplacingMergeTree FINAL collapses them properly.
    """
    repo = ClickHouseRepository(_DocComposite)
    await repo.insert(_DocComposite(key=1, tenant_id=7, body="hello"))
    assert await repo.count() == 1

    # Full-key delete - must NOT raise and must produce a correctly-keyed tombstone.
    await repo.delete(key=1, tenant_id=7)
    assert await repo.count() == 0  # hidden under FINAL + deleted_at IS NULL

    # Raw history (no FINAL): exactly 2 physical rows (live + tombstone).
    assert await repo.with_deleted().count() == 2
    # Tombstone row is the deleted one.
    assert await repo.only_deleted().count() == 1
