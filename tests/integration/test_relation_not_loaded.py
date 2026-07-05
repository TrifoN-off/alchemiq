import pytest

from alchemiq import ForeignKey, Model
from alchemiq.exceptions import RelationNotLoaded
from alchemiq.runtime.session import session_scope
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class RnlAuthor(Model):
    __tablename__ = "rnl_author"
    id: PK[int]
    name: str


class RnlBook(Model):
    __tablename__ = "rnl_book"
    id: PK[int]
    title: str
    author: RnlAuthor = ForeignKey(related_name="books")  # type: ignore[assignment]


async def test_unloaded_relation_access_raises(configured_db):
    async with session_scope(write=True) as s:
        s.add(RnlAuthor(id=1, name="A"))
        await s.flush()
        s.add(RnlBook(id=1, title="T", author_id=1))

    async with session_scope(write=False) as s:
        book = await s.get(RnlBook, 1)
        with pytest.raises(RelationNotLoaded):
            _ = book.author
