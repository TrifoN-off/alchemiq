"""Relationship loading on SQLite: FK select_related, O2O, M2M both directions."""

from __future__ import annotations

from alchemiq import Repository
from alchemiq.runtime.session import session_scope
from tests.sqlite._models import SqAuthor, SqBook, SqPost, SqProfile, SqTag, SqUser


async def test_fk_select_related(sqlite_db) -> None:
    async with session_scope(write=True) as s:
        s.add(SqAuthor(id=1, name="Ada"))
        await s.flush()
        s.add(SqBook(id=1, title="Notes", author_id=1))
    book = await Repository(SqBook).select_related("author").filter(id=1).first()
    assert book is not None
    assert book.author.name == "Ada"


async def test_fk_reverse_prefetch(sqlite_db) -> None:
    async with session_scope(write=True) as s:
        s.add(SqAuthor(id=1, name="Ada"))
        await s.flush()
        s.add_all([SqBook(id=1, title="A", author_id=1), SqBook(id=2, title="B", author_id=1)])
    author = await Repository(SqAuthor).prefetch_related("books").filter(id=1).first()
    assert author is not None
    assert {b.title for b in author.books} == {"A", "B"}


async def test_one_to_one_round_trip(sqlite_db) -> None:
    async with session_scope(write=True) as s:
        s.add(SqProfile(id=1, bio="hi"))
        await s.flush()
        s.add(SqUser(id=1, profile_id=1))
    user = await Repository(SqUser).select_related("profile").filter(id=1).first()
    assert user is not None
    assert user.profile.bio == "hi"


async def test_m2m_round_trip_and_reverse(sqlite_db) -> None:
    async with session_scope(write=True) as s:
        t1, t2 = SqTag(id=1, name="a"), SqTag(id=2, name="b")
        p1 = SqPost(id=1, title="p", tags=[t1, t2])
        p2 = SqPost(id=2, title="q", tags=[t1])
        s.add_all([t1, t2, p1, p2])
    post = await Repository(SqPost).prefetch_related("tags").filter(id=1).first()
    assert post is not None
    assert {t.name for t in post.tags} == {"a", "b"}
    tag = await Repository(SqTag).prefetch_related("sq_post_set").filter(id=1).first()
    assert tag is not None
    assert {p.title for p in tag.sq_post_set} == {"p", "q"}
