import pytest

from alchemiq import Model, Repository
from alchemiq.signals import clear, post_create, post_delete, pre_update
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class SigRow(Model):
    __tablename__ = "signals_sig_row"
    id: PK[int]
    name: str


@pytest.fixture(autouse=True)
def _clear_signals():
    clear()
    yield
    clear()


async def test_post_create_fires(configured_db):
    seen: list[int] = []

    @post_create(SigRow)
    async def on_create(instance, **kw):
        seen.append(instance.id)

    await Repository(SigRow).create(id=1, name="a")
    assert seen == [1]


async def test_pre_update_fires(configured_db):
    seen: list[str] = []

    @pre_update(SigRow)
    async def on_update(instance, **kw):
        seen.append(instance.name)

    repo = Repository(SigRow)
    await repo.create(id=2, name="a")
    await repo.update(2, name="b")
    assert seen == ["b"]  # fired after the change was applied, before flush


async def test_post_delete_fires(configured_db):
    seen: list[int] = []

    @post_delete(SigRow)
    async def on_delete(instance, **kw):
        seen.append(instance.id)

    repo = Repository(SigRow)
    await repo.create(id=3, name="a")
    await repo.delete(3)
    assert seen == [3]


async def test_raising_handler_rolls_back_write(configured_db):
    @post_create(SigRow)
    async def boom(instance, **kw):
        raise RuntimeError("nope")

    repo = Repository(SigRow)
    with pytest.raises(RuntimeError, match="nope"):
        await repo.create(id=4, name="a")
    # The row must NOT have been persisted (post_create fired before commit).
    assert await repo.get_or_none(id=4) is None
