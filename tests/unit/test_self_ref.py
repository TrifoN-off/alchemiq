"""Unit tests for self-referential ForeignKey (adjacency-list trees).

Tests must fail before the fix is applied (RED), then pass after (GREEN).

Model names are unique across the test suite to avoid SQLAlchemy registry collisions.

NOTE: Do NOT add 'from __future__ import annotations' here - that would stringify
ALL annotations (including PK[int]) and break model registration via the NameError
fallback path, which doesn't have localns either. The self-ref string annotation
'TreeNode | None' is written explicitly as a string literal to simulate the
forward-reference case.
"""

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from alchemiq import ForeignKey, Model
from alchemiq.exceptions import QueryError
from alchemiq.query.queryset import QuerySet
from alchemiq.types import PK

# ---------------------------------------------------------------------------
# Models - declared once at module level (SQLAlchemy can only register once)
# ---------------------------------------------------------------------------


class TreeNode(Model):
    """Self-referential nullable FK - adjacency-list tree.
    Note: 'parent' annotation must be a string to avoid NameError at class-body parse time.
    """

    __tablename__ = "sr_tree_node"

    id: PK[int]
    name: str
    parent: "TreeNode | None" = ForeignKey(related_name="children")  # type: ignore[assignment]  # noqa: UP037


class OrgUnit(Model):
    """Self-referential required FK - org hierarchy."""

    __tablename__ = "sr_org_unit"

    id: PK[int]
    title: str
    boss: "OrgUnit" = ForeignKey(related_name="reports")  # type: ignore[assignment]  # noqa: UP037


# ---------------------------------------------------------------------------
# TreeNode tests (nullable self-ref)
# ---------------------------------------------------------------------------


def test_sr_fk_column_in_fields():
    """parent_id synthetic FK field must be present in __alchemiq_fields__."""
    assert "parent_id" in TreeNode.__alchemiq_fields__


def test_sr_many_to_one_relationship_registered():
    """TreeNode.parent must be registered as many_to_one pointing at TreeNode."""
    rel = TreeNode.__alchemiq_relationships__["parent"]
    assert rel.direction == "many_to_one"
    assert rel.target is TreeNode
    assert rel.fk_attr == "parent_id"


def test_sr_one_to_many_relationship_registered():
    """TreeNode.children (backref) must be registered as one_to_many pointing at TreeNode."""
    rel = TreeNode.__alchemiq_relationships__["children"]
    assert rel.direction == "one_to_many"
    assert rel.target is TreeNode
    assert rel.fk_attr == "parent_id"


def test_sr_ddl_contains_self_ref_fk():
    """Compiled DDL must contain a FOREIGN KEY referencing the same table (tree_node)."""
    ddl = str(CreateTable(TreeNode.__table__).compile(dialect=postgresql.dialect()))
    # The FK must reference the same table
    assert "REFERENCES sr_tree_node" in ddl


def test_sr_nullable_fk_uses_set_null():
    """Nullable self-ref FK must use ON DELETE SET NULL."""
    ddl = str(CreateTable(TreeNode.__table__).compile(dialect=postgresql.dialect()))
    assert "ON DELETE SET NULL" in ddl


def test_sr_nullable_fk_field_is_nullable():
    """The synthetic parent_id field must be nullable (mirrors annotation)."""
    assert TreeNode.__alchemiq_fields__["parent_id"].config.nullable is True


# ---------------------------------------------------------------------------
# OrgUnit tests (required self-ref)
# ---------------------------------------------------------------------------


def test_sr_required_fk_column_in_fields():
    """boss_id synthetic FK field must be present in OrgUnit.__alchemiq_fields__."""
    assert "boss_id" in OrgUnit.__alchemiq_fields__


def test_sr_required_many_to_one_registered():
    """OrgUnit.boss must be registered as many_to_one pointing at OrgUnit."""
    rel = OrgUnit.__alchemiq_relationships__["boss"]
    assert rel.direction == "many_to_one"
    assert rel.target is OrgUnit


def test_sr_required_one_to_many_registered():
    """OrgUnit.reports (backref) must be registered as one_to_many pointing at OrgUnit."""
    rel = OrgUnit.__alchemiq_relationships__["reports"]
    assert rel.direction == "one_to_many"
    assert rel.target is OrgUnit


def test_sr_required_fk_uses_restrict():
    """Required self-ref FK must use ON DELETE RESTRICT."""
    ddl = str(CreateTable(OrgUnit.__table__).compile(dialect=postgresql.dialect()))
    assert "ON DELETE RESTRICT" in ddl


# ---------------------------------------------------------------------------
# Multi-hop self-ref guard tests
# ---------------------------------------------------------------------------


def test_two_hop_self_ref_raises():
    # grandparent traversal is unsupported and must fail loudly, not silently mis-compile
    with pytest.raises(QueryError):
        QuerySet(TreeNode).filter(parent__parent__name="x").compile()


def test_two_filters_on_same_parent_dedup_to_one_join():
    # two SEPARATE filters on the same parent are legitimate -> one aliased self-join, no error
    stmt = (
        QuerySet(TreeNode).filter(parent__name="a").filter(parent__name__startswith="r").compile()
    )
    out = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert out.count("JOIN") == 1
