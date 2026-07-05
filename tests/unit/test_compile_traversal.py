import pytest
from sqlalchemy.dialects import postgresql

from alchemiq import ForeignKey, Model
from alchemiq.exceptions import QueryError, UnknownFieldError
from alchemiq.query import QuerySet
from alchemiq.types import PK


class Author(Model):
    id: PK[int]
    name: str


class Book(Model):
    id: PK[int]
    title: str
    author: Author = ForeignKey(related_name="books")


def sql(qs) -> str:
    return str(
        qs.compile().compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


def test_forward_traversal_adds_join():
    out = sql(QuerySet(Book).filter(author__name__icontains="neo"))
    assert "JOIN author" in out
    assert "author.name ILIKE" in out


def test_direct_fk_filter_no_join():
    out = sql(QuerySet(Book).filter(author_id=5))
    assert "JOIN" not in out
    assert "book.author_id = 5" in out


def test_reverse_traversal_adds_join():
    out = sql(QuerySet(Author).filter(books__title__startswith="How"))
    assert "JOIN book" in out
    assert "book.title LIKE 'How%%'" in out


def test_duplicate_relation_joined_once():
    out = sql(QuerySet(Book).filter(author__name="neo").filter(author__id__gte=2))
    assert out.count("JOIN author") == 1


def test_unknown_relation_segment_raises():
    with pytest.raises(UnknownFieldError):
        QuerySet(Book).filter(nope__name="x").compile()


def test_two_relations_to_same_table_raise():
    class Editor(Model):
        id: PK[int]
        name: str

    class Manuscript(Model):
        id: PK[int]
        author: Editor = ForeignKey(related_name="authored")
        reviewer: Editor = ForeignKey(related_name="reviewed")

    with pytest.raises(QueryError):
        QuerySet(Manuscript).filter(author__name="a").filter(reviewer__name="b").compile()


def test_multi_hop_three_level_traversal():
    class Realm(Model):
        id: PK[int]
        code: str

    class House(Model):
        id: PK[int]
        realm: Realm = ForeignKey(related_name="houses")

    class Scroll(Model):
        id: PK[int]
        title: str
        house: House = ForeignKey(related_name="scrolls")

    out = sql(QuerySet(Scroll).filter(house__realm__code="US"))
    assert out.count("JOIN") == 2
    assert "realm.code = 'US'" in out
