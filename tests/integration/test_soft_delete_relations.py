import pytest

from alchemiq import Model, Repository, UnitOfWork
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class SdRelAuthor(Model):
    __tablename__ = "sd_rel_author"
    id: PK[int]
    name: str

    class Meta:
        soft_delete = True


class SdRelPost(Model):
    __tablename__ = "sd_rel_post"
    id: PK[int]
    title: str
    author: SdRelAuthor

    class Meta:
        soft_delete = True


async def _seed() -> None:
    async with UnitOfWork():
        await Repository(SdRelAuthor).create(id=1, name="Ann")
        await Repository(SdRelPost).create(id=1, title="live", author_id=1)
        await Repository(SdRelPost).create(id=2, title="dead", author_id=1)
        await Repository(SdRelAuthor).create(id=2, name="Bob")
        await Repository(SdRelPost).create(id=3, title="bob post", author_id=2)
    async with UnitOfWork():
        await Repository(SdRelPost).delete(2)
        await Repository(SdRelAuthor).delete(2)


async def test_prefetch_excludes_tombstones(configured_db):
    await _seed()
    ann = await Repository(SdRelAuthor).prefetch_related("sd_rel_post_set").get(id=1)
    assert [p.id for p in ann.sd_rel_post_set] == [1]


async def test_serialized_relations_exclude_tombstones(configured_db):
    await _seed()
    ann = await Repository(SdRelAuthor).prefetch_related("sd_rel_post_set").get(id=1)
    d = ann.to_dict(relations=("sd_rel_post_set",))
    assert [p["title"] for p in d["sd_rel_post_set"]] == ["live"]


async def test_select_related_tombstoned_target_loads_none(configured_db):
    await _seed()
    post = await Repository(SdRelPost).select_related("author").get(id=3)
    assert post.author is None  # Bob is a tombstone; FK column keeps its value
    assert post.author_id == 2


async def test_select_related_live_target_still_loads(configured_db):
    await _seed()
    post = await Repository(SdRelPost).select_related("author").get(id=1)
    assert post.author is not None
    assert post.author.name == "Ann"


async def test_traversal_filter_excludes_tombstoned_join(configured_db):
    await _seed()
    hits = await Repository(SdRelPost).filter(author__name="Bob").all()
    assert hits == []
    live_hits = await Repository(SdRelPost).filter(author__name="Ann").all()
    assert [p.id for p in live_hits] == [1]


async def test_with_deleted_includes_relations(configured_db):
    await _seed()
    ann = await Repository(SdRelAuthor).with_deleted().prefetch_related("sd_rel_post_set").get(id=1)
    assert sorted(p.id for p in ann.sd_rel_post_set) == [1, 2]
    post = await Repository(SdRelPost).with_deleted().select_related("author").get(id=3)
    assert post.author is not None
    assert post.author.name == "Bob"


async def test_with_deleted_traversal_matches_tombstoned_join(configured_db):
    await _seed()
    hits = await Repository(SdRelPost).with_deleted().filter(author__name="Bob").all()
    assert [p.id for p in hits] == [3]


async def test_only_deleted_relations_load_unfiltered(configured_db):
    # only_deleted() is an administrative escape hatch: root rows are tombstones,
    # their relations load without the liveness filter (restore tooling needs them).
    await _seed()
    tombs = await Repository(SdRelPost).only_deleted().select_related("author").all()
    assert [p.id for p in tombs] == [2]
    assert tombs[0].author is not None
    assert tombs[0].author.name == "Ann"


async def test_restore_and_hard_delete_still_reach_tombstones(configured_db):
    await _seed()
    restored = await Repository(SdRelPost).restore(2)
    assert restored.deleted_at is None
    await Repository(SdRelPost).delete(2)
    await Repository(SdRelPost).hard_delete(2)
    assert await Repository(SdRelPost).with_deleted().get_or_none(id=2) is None
