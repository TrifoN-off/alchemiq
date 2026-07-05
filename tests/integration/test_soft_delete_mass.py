import pytest

from alchemiq import Model, Repository
from alchemiq.exceptions import QueryError
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class SoftMassRow(Model):
    __tablename__ = "soft_mass_row"
    id: PK[int]
    tag: str

    class Meta:
        soft_delete = True


async def test_mass_delete_soft_deletes(configured_db):
    repo = Repository(SoftMassRow)
    await repo.create(id=1, tag="x")
    await repo.create(id=2, tag="x")
    await repo.create(id=3, tag="y")
    n = await repo.filter(tag="x").delete()
    assert n == 2
    assert await repo.count() == 1  # only the "y" row visible
    assert len(await repo.with_deleted().all()) == 3  # tombstones retained


async def test_mass_delete_requires_filter(configured_db):
    with pytest.raises(QueryError):
        await Repository(SoftMassRow)._qs().delete()  # no filter -> guard fires even for soft model


async def test_mass_hard_delete_purges(configured_db):
    repo = Repository(SoftMassRow)
    await repo.create(id=4, tag="z")
    await repo.create(id=5, tag="z")
    n = await repo.filter(tag="z").hard_delete()
    assert n == 2
    assert len(await repo.with_deleted().all()) == 0


async def test_mass_update_excludes_deleted(configured_db):
    repo = Repository(SoftMassRow)
    await repo.create(id=6, tag="a")
    await repo.create(id=7, tag="a")
    await repo.delete(6)  # tombstone
    n = await repo.filter(tag="a").update(tag="b")  # must skip the tombstone
    assert n == 1


async def test_hard_delete_only_deleted_purges_tombstones(configured_db):
    repo = Repository(SoftMassRow)
    await repo.create(id=8, tag="p")
    await repo.create(id=9, tag="p")
    await repo.delete(8)  # tombstone id=8 (live id=9 stays)
    n = await repo.only_deleted().filter(tag="p").hard_delete()
    assert n == 1  # only the tombstone purged
    assert await repo.get_or_none(id=9) is not None  # live row survives
    assert len(await repo.with_deleted().all()) == 1  # only id=9 remains


async def test_delete_all_soft_deletes_every_row(configured_db):
    repo = Repository(SoftMassRow)
    await repo.create(id=10, tag="m")
    await repo.create(id=11, tag="n")
    n = await repo.delete_all()  # full-table escape hatch, no filter
    assert n == 2
    assert await repo.count() == 0  # all soft-deleted -> none live
    deleted = await repo.with_deleted().all()
    assert len(deleted) == 2  # rows RETAINED as tombstones (UPDATE, not physical DELETE)
    assert all(r.deleted_at is not None for r in deleted)
