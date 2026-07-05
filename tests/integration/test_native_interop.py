from __future__ import annotations

import pytest
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from alchemiq import Model, Repository
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class Doc(Model):
    __tablename__ = "native_doc"
    id: PK[int]
    title: str
    payload: Mapped[dict | None] = mapped_column(JSONB)


class CustomPk(Model):
    __tablename__ = "native_custom_pk"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: str


async def test_native_column_round_trip(configured_db) -> None:
    repo = Repository(Doc)
    await repo.create(id=1, title="t", payload={"k": 1})
    got = await repo.get(id=1)
    assert got.payload == {"k": 1}
    assert got.to_dict()["payload"] == {"k": 1}  # native column serialized


async def test_native_nullable_persists_none(configured_db) -> None:
    repo = Repository(Doc)
    await repo.create(id=2, title="t2")  # payload omitted -> NULL (reconciled nullable column)
    got = await repo.get(id=2)
    assert got.payload is None


async def test_native_custom_pk(configured_db) -> None:
    repo = Repository(CustomPk)
    await repo.create(code="abc", name="n")
    got = await repo.get(code="abc")  # pk_name found the native PK
    assert got.name == "n"


async def test_filter_by_native_column(configured_db) -> None:
    repo = Repository(CustomPk)
    await repo.create(code="x1", name="a")
    await repo.create(code="x2", name="b")
    rows = await repo.filter(code="x1").all()  # filter compiles on the native column
    assert [r.code for r in rows] == ["x1"]


async def test_order_by_native_column(configured_db) -> None:
    repo = Repository(CustomPk)
    await repo.create(code="b", name="2")
    await repo.create(code="a", name="1")
    await repo.create(code="c", name="3")
    asc = await repo.order_by("code").all()
    assert [r.code for r in asc] == ["a", "b", "c"]
    desc = await repo.order_by("-code").all()
    assert [r.code for r in desc] == ["c", "b", "a"]


async def test_bulk_upsert_native_column(configured_db) -> None:
    repo = Repository(Doc)
    await repo.bulk_upsert(
        [Doc(id=50, title="x", payload={"v": 1}), Doc(id=51, title="y", payload={"v": 2})]
    )
    assert (await repo.get(id=50)).payload == {"v": 1}
    # conflict-update path must also carry the native column
    await repo.bulk_upsert([Doc(id=50, title="x", payload={"v": 99})])
    assert (await repo.get(id=50)).payload == {"v": 99}
