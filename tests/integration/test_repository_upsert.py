import pytest

from alchemiq import Model, Repository
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class UpRow(Model):
    __tablename__ = "repo_upsert_up_row"
    id: PK[int]
    email: str
    name: str


async def test_get_or_create_creates_then_gets(configured_db):
    repo = Repository(UpRow)
    obj, created = await repo.get_or_create(id=1, email="a@b.c", defaults={"name": "Ann"})
    assert created is True and obj.name == "Ann"

    again, created2 = await repo.get_or_create(id=1, email="a@b.c", defaults={"name": "X"})
    assert created2 is False
    assert again.name == "Ann"  # not overwritten


async def test_update_or_create_updates_existing(configured_db):
    repo = Repository(UpRow)
    await repo.create(id=2, email="c@d.e", name="old")
    obj, created = await repo.update_or_create(id=2, defaults={"name": "new"})
    assert created is False and obj.name == "new"


async def test_update_or_create_creates_when_absent(configured_db):
    repo = Repository(UpRow)
    obj, created = await repo.update_or_create(id=3, email="z@z.z", defaults={"name": "fresh"})
    assert created is True and obj.name == "fresh"
