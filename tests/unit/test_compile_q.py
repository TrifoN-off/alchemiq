import pytest
from sqlalchemy.dialects import postgresql

from alchemiq import Model
from alchemiq.exceptions import QueryError, UnknownFieldError, UnknownOperatorError
from alchemiq.query import Q
from alchemiq.query.compiler import compile_q
from alchemiq.types import PK


class Person(Model):
    id: PK[int]
    name: str
    age: int


def sql(expr) -> str:
    return str(expr.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_single_condition():
    assert "person.age >= 18" in sql(compile_q(Q(age__gte=18), Person))


def test_anded_conditions():
    out = sql(compile_q(Q(age__gte=18, name="neo"), Person))
    assert "person.age >= 18" in out
    assert "AND" in out
    assert "person.name = 'neo'" in out


def test_or_tree():
    out = sql(compile_q(Q(name="neo") | Q(name="trinity"), Person))
    assert " OR " in out


def test_negation():
    out = sql(compile_q(~Q(name="neo", age__gte=18), Person))
    assert "NOT (" in out  # NOT wraps the AND of both conditions


def test_empty_q_is_true():
    assert "true" in sql(compile_q(Q(), Person)).lower()


def test_unknown_field_raises():
    with pytest.raises(UnknownFieldError):
        compile_q(Q(nope=1), Person)


def test_unknown_operator_raises():
    with pytest.raises(UnknownOperatorError):
        compile_q(Q(age__zzz=1), Person)


def test_traversal_path_rejected_until_task_12():
    with pytest.raises(QueryError):
        compile_q(Q(author__name="x"), Person)
