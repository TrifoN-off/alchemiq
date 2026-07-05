from __future__ import annotations

import pytest
from sqlalchemy import Column, ForeignKey, Table
from sqlalchemy.orm import Mapped, relationship

from alchemiq import Model, Repository
from alchemiq.exceptions import RelationNotLoaded
from alchemiq.model.registry import metadata
from alchemiq.runtime.session import session_scope
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class NTag(Model):
    __tablename__ = "native_rel_ntag"
    id: PK[int]
    name: str


# native through-style M2M association table (escape-hatch territory)
_npost_ntag = Table(
    "native_rel_npost_ntag",
    metadata,
    Column("npost_id", ForeignKey("native_rel_npost.id"), primary_key=True),
    Column("ntag_id", ForeignKey("native_rel_ntag.id"), primary_key=True),
)


class NPost(Model):
    __tablename__ = "native_rel_npost"
    id: PK[int]
    title: str
    tags: Mapped[list[NTag]] = relationship(secondary=_npost_ntag, lazy="raise_on_sql")  # native


async def test_native_m2m_loads_and_traverses(configured_db) -> None:
    async with session_scope(write=True) as s:
        t1, t2 = NTag(id=1, name="a"), NTag(id=2, name="b")
        s.add_all([t1, t2, NPost(id=1, title="p", tags=[t1, t2])])
    post = await Repository(NPost).prefetch_related("tags").filter(id=1).first()
    assert post is not None
    assert {t.name for t in post.tags} == {"a", "b"}
    hits = await Repository(NPost).filter(tags__name="a").all()  # traversal across native M2M
    assert [p.id for p in hits] == [1]


async def test_native_relationship_raise_on_sql_surfaces_relation_not_loaded(configured_db) -> None:
    async with session_scope(write=True) as s:
        s.add(NPost(id=2, title="q"))
    post = await Repository(NPost).filter(id=2).first()  # tags not loaded
    assert post is not None
    with pytest.raises(RelationNotLoaded):
        _ = post.tags
