import pytest

from alchemiq import Model, Repository
from alchemiq.exceptions import ConfigError, NotFoundError
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class SoftRow(Model):
    __tablename__ = "soft_row"
    id: PK[int]
    name: str

    class Meta:
        soft_delete = True


class PlainRow(Model):
    __tablename__ = "soft_plain_restore_row"
    id: PK[int]
    name: str


async def test_delete_hides_but_keeps_row(configured_db):
    repo = Repository(SoftRow)
    await repo.create(id=1, name="a")
    await repo.delete(1)
    assert await repo.get_or_none(id=1) is None  # hidden from default reads
    assert await repo.with_deleted().get(id=1) is not None  # row still present
    assert (await repo.with_deleted().get(id=1)).deleted_at is not None


async def test_only_deleted_lists_tombstones(configured_db):
    repo = Repository(SoftRow)
    await repo.create(id=2, name="live")
    await repo.create(id=3, name="dead")
    await repo.delete(3)
    tombstones = await repo.only_deleted().all()
    assert [r.id for r in tombstones] == [3]


async def test_second_delete_raises_not_found(configured_db):
    repo = Repository(SoftRow)
    await repo.create(id=4, name="a")
    await repo.delete(4)
    with pytest.raises(NotFoundError):
        await repo.delete(4)  # already a tombstone -> invisible to delete()


async def test_count_excludes_deleted(configured_db):
    repo = Repository(SoftRow)
    await repo.create(id=5, name="a")
    await repo.create(id=6, name="b")
    await repo.delete(6)
    assert await repo.count() == 1


async def test_restore_brings_row_back(configured_db):
    repo = Repository(SoftRow)
    await repo.create(id=10, name="a")
    await repo.delete(10)
    restored = await repo.restore(10)
    assert restored.deleted_at is None
    assert await repo.get_or_none(id=10) is not None


async def test_restore_non_tombstone_raises(configured_db):
    repo = Repository(SoftRow)
    await repo.create(id=11, name="a")
    with pytest.raises(NotFoundError):
        await repo.restore(11)  # not deleted -> nothing to restore


async def test_hard_delete_purges_tombstone(configured_db):
    repo = Repository(SoftRow)
    await repo.create(id=12, name="a")
    await repo.delete(12)
    await repo.hard_delete(12)  # sees and purges the tombstone
    assert await repo.with_deleted().get_or_none(id=12) is None


async def test_restore_on_plain_model_raises(configured_db):
    with pytest.raises(ConfigError):
        await Repository(PlainRow).restore(1)
