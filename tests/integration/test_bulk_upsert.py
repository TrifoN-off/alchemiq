from __future__ import annotations

import pytest

from alchemiq import Model, Repository
from alchemiq.types import PK, Field

pytestmark = pytest.mark.integration


class BulkUpsertRow(Model):
    __tablename__ = "bulk_upsert_row"
    id: PK[int]
    email: str = Field(unique=True)
    name: str


async def test_inserts_new_rows(configured_db) -> None:
    repo = Repository(BulkUpsertRow)
    n = await repo.bulk_upsert(
        [BulkUpsertRow(id=1, email="a@x.c", name="A"), BulkUpsertRow(id=2, email="b@x.c", name="B")]
    )
    assert n == 2
    assert await repo.count() == 2


async def test_updates_on_pk_conflict(configured_db) -> None:
    repo = Repository(BulkUpsertRow)
    await repo.bulk_upsert([BulkUpsertRow(id=1, email="a@x.c", name="A")])
    await repo.bulk_upsert([BulkUpsertRow(id=1, email="a@x.c", name="A2")])
    row = await repo.get(id=1)
    assert row.name == "A2"
    assert await repo.count() == 1


async def test_conflict_on_unique_email(configured_db) -> None:
    repo = Repository(BulkUpsertRow)
    await repo.bulk_upsert([BulkUpsertRow(id=1, email="dup@x.c", name="first")])
    await repo.bulk_upsert(
        [BulkUpsertRow(id=2, email="dup@x.c", name="second")],
        conflict=["email"],
        update_fields=["name"],
    )
    assert await repo.count() == 1
    row = await repo.get(email="dup@x.c")
    assert row.name == "second" and row.id == 1  # updated in place, PK untouched


async def test_ignore_conflicts_does_nothing(configured_db) -> None:
    repo = Repository(BulkUpsertRow)
    await repo.bulk_upsert([BulkUpsertRow(id=1, email="a@x.c", name="orig")])
    n = await repo.bulk_upsert(
        [BulkUpsertRow(id=1, email="a@x.c", name="changed")], ignore_conflicts=True
    )
    assert n == 0
    row = await repo.get(id=1)
    assert row.name == "orig"  # untouched


async def test_empty_returns_zero(configured_db) -> None:
    assert await Repository(BulkUpsertRow).bulk_upsert([]) == 0
