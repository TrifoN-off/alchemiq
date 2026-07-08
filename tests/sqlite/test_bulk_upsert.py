"""bulk_upsert on SQLite: INSERT ... ON CONFLICT via the sqlite dialect insert."""

from __future__ import annotations

from alchemiq import Repository
from tests.sqlite._models import SqUpsertItem


async def test_insert_then_update_on_pk_conflict(sqlite_db) -> None:
    repo = Repository(SqUpsertItem)
    assert await repo.bulk_upsert([SqUpsertItem(id=1, sku="a", qty=1)]) == 1
    await repo.bulk_upsert([SqUpsertItem(id=1, sku="a", qty=5)])
    row = await repo.get(id=1)
    assert row.qty == 5


async def test_ignore_conflicts_keeps_existing_row(sqlite_db) -> None:
    repo = Repository(SqUpsertItem)
    await repo.bulk_upsert([SqUpsertItem(id=1, sku="a", qty=1)])
    await repo.bulk_upsert([SqUpsertItem(id=1, sku="a", qty=9)], ignore_conflicts=True)
    row = await repo.get(id=1)
    assert row.qty == 1


async def test_conflict_on_unique_column(sqlite_db) -> None:
    repo = Repository(SqUpsertItem)
    await repo.bulk_upsert([SqUpsertItem(id=1, sku="a", qty=1)])
    await repo.bulk_upsert(
        [SqUpsertItem(id=2, sku="a", qty=7)],
        conflict=["sku"],
        update_fields=["qty"],
    )
    row = await repo.get(id=1)
    assert row.qty == 7


async def test_mixed_batch_inserts_and_updates(sqlite_db) -> None:
    repo = Repository(SqUpsertItem)
    await repo.bulk_upsert([SqUpsertItem(id=1, sku="a", qty=1)])
    n = await repo.bulk_upsert(
        [SqUpsertItem(id=1, sku="a", qty=2), SqUpsertItem(id=2, sku="b", qty=3)]
    )
    assert n == 2
    assert (await repo.get(id=1)).qty == 2
    assert (await repo.get(id=2)).qty == 3
