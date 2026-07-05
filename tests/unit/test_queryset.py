from sqlalchemy.dialects import postgresql

from alchemiq import Model
from alchemiq.query import QuerySet
from alchemiq.types import PK


class Person(Model):
    __tablename__ = "person_qs"
    id: PK[int]
    name: str
    age: int


def sql(qs) -> str:
    return str(
        qs.compile().compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


def test_filter_builds_where():
    out = sql(QuerySet(Person).filter(age__gte=18))
    assert "WHERE person_qs.age >= 18" in out


def test_chaining_is_immutable():
    base = QuerySet(Person)
    filtered = base.filter(age__gte=18)
    assert base._where == ()
    assert filtered._where != ()


def test_exclude_negates():
    out = sql(QuerySet(Person).exclude(name__in=["banned", "evil"]))
    assert "NOT" in out


def test_order_by_desc_and_asc():
    out = sql(QuerySet(Person).order_by("-age", "name"))
    assert "ORDER BY person_qs.age DESC, person_qs.name" in out


def test_limit_offset_distinct():
    out = sql(QuerySet(Person).distinct().limit(10).offset(5))
    assert "DISTINCT" in out
    assert "LIMIT 10" in out
    assert "OFFSET 5" in out


def test_only_projects_columns():
    out = sql(QuerySet(Person).only("id", "name"))
    assert "person_qs.id" in out and "person_qs.name" in out
    assert "person_qs.age" not in out


def test_multiple_filters_are_anded():
    out = sql(QuerySet(Person).filter(age__gte=18).filter(name="neo"))
    assert "person_qs.age >= 18" in out
    assert "person_qs.name = 'neo'" in out
    assert "AND" in out
