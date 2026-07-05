"""Integration tests: QuerySet + Q execution against real PostgreSQL.

Tests:
1. Relationship-traversal QuerySet select returns the correct rows.
2. Inferred on_delete=RESTRICT FK blocks a parent delete (IntegrityError).
3. Serialized->deserialized Q (base64 round-trip) filters correctly.

Each test owns its engine lifecycle (create_all / drop_all) so DDL and data
are always cleaned up, regardless of test outcome.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from alchemiq import ForeignKey, Model
from alchemiq.model.registry import metadata
from alchemiq.query import Q, QuerySet
from alchemiq.types import PK

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Model declarations (module-level so SQLAlchemy registers them exactly once)
# ---------------------------------------------------------------------------


class Country(Model):
    """Parent model - used in all three tests."""

    __tablename__ = "it_country"

    id: PK[int]
    code: str


class City(Model):
    """Child model with non-nullable FK -> on_delete defaults to RESTRICT."""

    __tablename__ = "it_city"

    id: PK[int]
    name: str
    country: Country = ForeignKey(related_name="cities")  # type: ignore[assignment]


class ItTreeNode(Model):
    """Self-referential adjacency-list tree - used in self-ref integration test."""

    __tablename__ = "it_tree"

    id: PK[int]
    name: str
    parent: "ItTreeNode | None" = ForeignKey(related_name="children")  # type: ignore[assignment]  # noqa: UP037


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_traversal_select_executes(pg_container) -> None:
    """QuerySet with a relationship-traversal filter (country__code) returns correct rows."""
    engine = create_async_engine(pg_container.get_connection_url())
    try:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
            await conn.execute(
                text("INSERT INTO it_country (id, code) VALUES (1, 'US'), (2, 'FR')")
            )
            await conn.execute(
                text(
                    "INSERT INTO it_city (id, name, country_id)"
                    " VALUES (1, 'NYC', 1), (2, 'Paris', 2)"
                )
            )

        qs = QuerySet(City).filter(country__code="FR").order_by("name")
        async with engine.connect() as conn:
            rows = (await conn.execute(qs.compile())).all()

        assert len(rows) == 1
        assert rows[0].name == "Paris"
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.drop_all)
        await engine.dispose()


@pytest.mark.integration
async def test_on_delete_restrict_enforced(pg_container) -> None:
    """Deleting a parent row while a child references it must raise IntegrityError (RESTRICT)."""
    engine = create_async_engine(pg_container.get_connection_url())
    try:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
            await conn.execute(text("INSERT INTO it_country (id, code) VALUES (10, 'DE')"))
            await conn.execute(
                text("INSERT INTO it_city (id, name, country_id) VALUES (10, 'Berlin', 10)")
            )

        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM it_country WHERE id = 10"))
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.drop_all)
        await engine.dispose()


@pytest.mark.integration
async def test_serialized_q_roundtrips_and_filters(pg_container) -> None:
    """Q serialized to base64 and restored via Q.from_base64 filters correctly."""
    engine = create_async_engine(pg_container.get_connection_url())
    try:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
            await conn.execute(
                text("INSERT INTO it_country (id, code) VALUES (3, 'JP'), (4, 'BR'), (5, 'US')")
            )

        wire = Q(code__in=["JP", "BR"]).to_base64()
        restored = Q.from_base64(wire, model=Country)
        qs = QuerySet(Country).filter(restored).order_by("code")
        async with engine.connect() as conn:
            rows = (await conn.execute(qs.compile())).all()

        assert [r.code for r in rows] == ["BR", "JP"]
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.drop_all)
        await engine.dispose()


@pytest.mark.integration
async def test_self_ref_fk_traversal(pg_container) -> None:
    """Self-referential FK works end-to-end: root + child, traverse via parent__name filter."""
    engine = create_async_engine(pg_container.get_connection_url())
    try:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
            # Insert root (parent_id NULL) then child pointing to root
            await conn.execute(
                text("INSERT INTO it_tree (id, name, parent_id) VALUES (1, 'root', NULL)")
            )
            await conn.execute(
                text("INSERT INTO it_tree (id, name, parent_id) VALUES (2, 'child', 1)")
            )

        # Filter children whose parent has name='root'
        qs = QuerySet(ItTreeNode).filter(parent__name="root")
        async with engine.connect() as conn:
            rows = (await conn.execute(qs.compile())).all()

        assert len(rows) == 1
        assert rows[0].name == "child"
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.drop_all)
        await engine.dispose()
