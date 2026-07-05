import pytest

from alchemiq import Model, Repository, UnitOfWork
from alchemiq.exceptions import RelationNotLoaded
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class SerRelAuthor(Model):
    __tablename__ = "ser_rel_ser_author"
    id: PK[int]
    name: str


class SerRelBook(Model):
    __tablename__ = "ser_rel_ser_book"
    id: PK[int]
    title: str
    author: SerRelAuthor


async def test_loaded_relation_nests(configured_db):
    async with UnitOfWork():
        await Repository(SerRelAuthor).create(id=1, name="Ann")
        await Repository(SerRelBook).create(id=1, title="T", author_id=1)
    book = await Repository(SerRelBook).select_related("author").get(id=1)
    d = book.to_dict(relations=("author",))
    assert d["author_id"] == 1
    assert d["author"]["name"] == "Ann"


async def test_unloaded_relation_raises(configured_db):
    async with UnitOfWork():
        await Repository(SerRelAuthor).create(id=2, name="Bea")
        await Repository(SerRelBook).create(id=2, title="U", author_id=2)
    book = await Repository(SerRelBook).get(id=2)  # author NOT loaded
    assert book.to_dict()["author_id"] == 2  # scalar FK id still present
    with pytest.raises(RelationNotLoaded):
        book.to_dict(relations=("author",))


async def test_loaded_list_relation_nests(configured_db):
    async with UnitOfWork():
        await Repository(SerRelAuthor).create(id=3, name="Cy")
        await Repository(SerRelBook).create(id=3, title="A", author_id=3)
        await Repository(SerRelBook).create(id=4, title="B", author_id=3)
    author = await Repository(SerRelAuthor).prefetch_related("ser_rel_book_set").get(id=3)
    d = author.to_dict(relations=("ser_rel_book_set",))
    titles = sorted(b["title"] for b in d["ser_rel_book_set"])
    assert titles == ["A", "B"]
