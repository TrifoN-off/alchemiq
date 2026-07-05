from sqlalchemy import inspect as sa_inspect

from alchemiq import ForeignKey, Model
from alchemiq.types import PK


class LzAuthor(Model):
    __tablename__ = "lazy_lz_author"
    id: PK[int]
    name: str


class LzBook(Model):
    __tablename__ = "lazy_lz_book"
    id: PK[int]
    title: str
    author: LzAuthor = ForeignKey(related_name="books")  # type: ignore[assignment]


def test_forward_relationship_is_raise_on_sql():
    rels = sa_inspect(LzBook).relationships
    assert rels["author"].lazy == "raise_on_sql"


def test_reverse_relationship_is_raise_on_sql():
    rels = sa_inspect(LzAuthor).relationships
    assert rels["books"].lazy == "raise_on_sql"
