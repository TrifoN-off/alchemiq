import pytest

from alchemiq.clickhouse import ClickHouseModel, ClickHouseRepository, MergeTree
from alchemiq.clickhouse.types import UInt32
from alchemiq.exceptions import UnsupportedOperationError


class _Plain(ClickHouseModel):
    id: int = UInt32()

    class Meta:
        engine = MergeTree(order_by=("id",))


@pytest.mark.unit
@pytest.mark.parametrize("method", ["update", "bulk_update", "get_or_create", "update_or_create"])
async def test_mutations_unsupported(method):
    repo = ClickHouseRepository(_Plain)
    with pytest.raises(UnsupportedOperationError):
        await getattr(repo, method)()


@pytest.mark.unit
async def test_delete_unsupported_on_non_soft_delete():
    repo = ClickHouseRepository(_Plain)
    with pytest.raises(UnsupportedOperationError):
        await repo.delete(id=1)


@pytest.mark.unit
async def test_restore_unsupported_on_non_soft_delete():
    repo = ClickHouseRepository(_Plain)
    with pytest.raises(UnsupportedOperationError):
        await repo.restore(id=1)


@pytest.mark.unit
async def test_cleanup_unsupported_on_non_soft_delete():
    repo = ClickHouseRepository(_Plain)
    with pytest.raises(UnsupportedOperationError):
        await repo.cleanup()
