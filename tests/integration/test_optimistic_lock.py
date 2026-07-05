from __future__ import annotations

import pytest

from alchemiq import Model, Repository, version_of
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class VersionedRow(Model):
    __tablename__ = "lock_versioned"
    id: PK[int]
    name: str

    class Meta:
        versioned = True


class PlainRow(Model):
    __tablename__ = "lock_plain"
    id: PK[int]
    name: str


async def test_create_sets_version_to_one(configured_db) -> None:
    repo = Repository(VersionedRow)
    row = await repo.create(id=1, name="a")
    assert version_of(row) == 1


async def test_update_increments_version(configured_db) -> None:
    repo = Repository(VersionedRow)
    await repo.create(id=2, name="a")
    r2 = await repo.update(2, name="b")
    assert version_of(r2) == 2
    r3 = await repo.update(2, name="c")
    assert version_of(r3) == 3


async def test_update_correct_expected_version(configured_db) -> None:
    repo = Repository(VersionedRow)
    await repo.create(id=10, name="a")
    r = await repo.update(10, expected_version=1, name="b")
    assert version_of(r) == 2


async def test_update_stale_expected_version_raises(configured_db) -> None:
    from alchemiq import ConcurrentModificationError

    repo = Repository(VersionedRow)
    await repo.create(id=11, name="a")
    await repo.update(11, name="b")  # version -> 2
    with pytest.raises(ConcurrentModificationError):
        await repo.update(11, expected_version=1, name="c")


async def test_update_without_version_is_lenient(configured_db) -> None:
    repo = Repository(VersionedRow)
    await repo.create(id=12, name="a")
    r = await repo.update(12, name="b")  # no expected_version -> still bumps
    assert version_of(r) == 2


async def test_update_expected_version_on_non_versioned_raises(configured_db) -> None:
    from alchemiq.exceptions import ConfigError

    repo = Repository(PlainRow)
    await repo.create(id=13, name="a")
    with pytest.raises(ConfigError):
        await repo.update(13, expected_version=1, name="b")


async def test_concurrent_flush_wraps_staledata(configured_db) -> None:
    from alchemiq import ConcurrentModificationError, UnitOfWork
    from alchemiq.runtime.engine import require_sessionmaker

    repo = Repository(VersionedRow)
    await repo.create(id=14, name="a")
    with pytest.raises(ConcurrentModificationError):
        async with UnitOfWork():
            loaded = await repo.get(id=14)  # identity-map holds version 1
            assert version_of(loaded) == 1
            sm = require_sessionmaker()
            async with sm() as other:  # external txn bumps the row to version 2
                ext = await other.get(VersionedRow, 14)
                ext.name = "ext"
                await other.commit()
            # session.get returns the stale identity-mapped instance (_version 1);
            # flush emits UPDATE ... WHERE _version=1 -> 0 rows -> StaleDataError -> wrap.
            await repo.update(14, name="mine")


class SoftVersionedRow(Model):
    __tablename__ = "lock_soft_versioned"
    id: PK[int]
    name: str

    class Meta:
        soft_delete = True
        versioned = True


async def test_hard_delete_correct_version(configured_db) -> None:
    repo = Repository(VersionedRow)
    await repo.create(id=20, name="a")
    await repo.delete(20, expected_version=1)
    assert await repo.get_or_none(id=20) is None


async def test_hard_delete_stale_version_raises(configured_db) -> None:
    from alchemiq import ConcurrentModificationError

    repo = Repository(VersionedRow)
    await repo.create(id=21, name="a")
    await repo.update(21, name="b")  # version -> 2
    with pytest.raises(ConcurrentModificationError):
        await repo.delete(21, expected_version=1)
    assert await repo.get_or_none(id=21) is not None  # not deleted


async def test_soft_delete_with_version_bumps(configured_db) -> None:
    repo = Repository(SoftVersionedRow)
    await repo.create(id=22, name="a")
    await repo.delete(22, expected_version=1)  # soft-delete; UPDATE bumps version
    assert await repo.get_or_none(id=22) is None  # excluded by soft-delete
    tomb = await repo.with_deleted().get(id=22)
    assert tomb.deleted_at is not None
    assert version_of(tomb) == 2


async def test_soft_delete_stale_version_raises(configured_db) -> None:
    from alchemiq import ConcurrentModificationError

    repo = Repository(SoftVersionedRow)
    await repo.create(id=23, name="a")
    await repo.update(23, name="b")  # version -> 2
    with pytest.raises(ConcurrentModificationError):
        await repo.delete(23, expected_version=1)
    assert await repo.get_or_none(id=23) is not None  # not soft-deleted (rollback safety)


async def test_concurrent_hard_delete_wraps_staledata(configured_db) -> None:
    from alchemiq import ConcurrentModificationError, UnitOfWork
    from alchemiq.runtime.engine import require_sessionmaker

    repo = Repository(VersionedRow)
    await repo.create(id=31, name="a")
    with pytest.raises(ConcurrentModificationError):
        async with UnitOfWork():
            loaded = await repo.get(id=31)
            assert version_of(loaded) == 1
            sm = require_sessionmaker()
            async with sm() as other:
                ext = await other.get(VersionedRow, 31)
                ext.name = "ext"
                await other.commit()
            await repo.hard_delete(31)


async def test_concurrent_restore_wraps_staledata(configured_db) -> None:
    from alchemiq import ConcurrentModificationError, UnitOfWork
    from alchemiq.query.soft_delete import INCLUDE
    from alchemiq.runtime.engine import require_sessionmaker
    from alchemiq.runtime.soft_delete_filter import DELETED_MODE_OPTION

    repo = Repository(SoftVersionedRow)
    await repo.create(id=32, name="a")
    await repo.delete(32)  # soft-delete -> tombstone, version 2
    with pytest.raises(ConcurrentModificationError):
        async with UnitOfWork():
            tomb = await repo.with_deleted().get(id=32)  # _version 2 into UoW identity map
            assert tomb.deleted_at is not None
            sm = require_sessionmaker()
            async with sm() as other:
                # alchemiq-made sessions filter tombstones; opt in to reach one
                ext = await other.get(
                    SoftVersionedRow, 32, execution_options={DELETED_MODE_OPTION: INCLUDE}
                )
                assert ext is not None
                ext.name = "ext"
                await other.commit()  # _version 2 -> 3
            await repo.restore(32)  # flush WHERE _version=2 -> 0 rows -> StaleData -> wrap
