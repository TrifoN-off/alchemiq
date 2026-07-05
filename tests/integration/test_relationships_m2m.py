from __future__ import annotations

import pytest

from alchemiq import Model, Repository
from alchemiq.runtime.session import session_scope
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class Tag(Model):
    __tablename__ = "m2m_tag"
    id: PK[int]
    name: str


class M2MIntPost(Model):
    __tablename__ = "m2m_post"
    id: PK[int]
    title: str
    tags: list[Tag]


async def _seed() -> None:
    async with session_scope(write=True) as s:
        t1, t2 = Tag(id=1, name="a"), Tag(id=2, name="b")
        p1 = M2MIntPost(id=1, title="p", tags=[t1, t2])
        p2 = M2MIntPost(id=2, title="q", tags=[t1])
        s.add_all([t1, t2, p1, p2])


async def test_m2m_round_trip_prefetch(configured_db) -> None:
    await _seed()
    post = await Repository(M2MIntPost).prefetch_related("tags").filter(id=1).first()
    assert post is not None
    assert {t.name for t in post.tags} == {"a", "b"}


async def test_m2m_reverse_collection(configured_db) -> None:
    await _seed()
    tag = await Repository(Tag).prefetch_related("m2m_int_post_set").filter(id=1).first()
    assert tag is not None
    assert {p.title for p in tag.m2m_int_post_set} == {"p", "q"}


async def test_m2m_filter_traversal(configured_db) -> None:
    await _seed()
    posts = await Repository(M2MIntPost).filter(tags__name="b").all()
    assert [p.id for p in posts] == [1]
