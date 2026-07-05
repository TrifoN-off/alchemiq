from sqlalchemy import Column, Integer, String
from sqlalchemy.dialects import postgresql

from alchemiq.query.lookups import (
    LOOKUPS,
    VALUE_KIND,
    escape_like,
    parse_key,
)

col = Column("name", String)
age = Column("age", Integer)


def sql(expr) -> str:
    return str(expr.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_parse_key_with_operator():
    assert parse_key("age__gte") == (["age"], "gte")


def test_parse_key_bare_field_is_exact():
    assert parse_key("name") == (["name"], "exact")


def test_parse_key_traversal_path():
    assert parse_key("author__name__icontains") == (["author", "name"], "icontains")


def test_parse_key_trailing_nonsuffix_is_exact():
    # 'created_at' has '__'-free name; a path whose last segment is not a lookup is exact
    assert parse_key("author__name") == (["author", "name"], "exact")


def test_exact_and_comparisons():
    assert "age = 18" in sql(LOOKUPS["exact"](age, 18))
    assert "age != 18" in sql(LOOKUPS["ne"](age, 18))
    assert "age >= 18" in sql(LOOKUPS["gte"](age, 18))


def test_in_and_nin():
    assert "IN (1, 2)" in sql(LOOKUPS["in"](age, [1, 2]))
    assert "NOT IN (1, 2)" in sql(LOOKUPS["nin"](age, [1, 2]))


def test_isnull_both_directions():
    assert "IS NULL" in sql(LOOKUPS["isnull"](col, True))
    assert "IS NOT NULL" in sql(LOOKUPS["isnull"](col, False))


def test_text_lookups_use_like_ilike():
    assert "LIKE '%%neo%%'" in sql(LOOKUPS["contains"](col, "neo"))
    assert "ILIKE '%%neo%%'" in sql(LOOKUPS["icontains"](col, "neo"))
    assert "LIKE 'neo%%'" in sql(LOOKUPS["startswith"](col, "neo"))
    assert "LIKE '%%neo'" in sql(LOOKUPS["endswith"](col, "neo"))


def test_range_between():
    assert "BETWEEN 1 AND 9" in sql(LOOKUPS["range"](age, (1, 9)))


def test_escape_like_specials():
    assert escape_like("50%_x") == r"50\%\_x"


def test_jcontains_uses_containment_operator():
    from sqlalchemy.dialects.postgresql import JSONB

    jcol = Column("data", JSONB)
    compiled = str(LOOKUPS["jcontains"](jcol, {"k": 1}).compile(dialect=postgresql.dialect()))
    assert "@>" in compiled


def test_value_kind_mapping():
    assert VALUE_KIND["in"] == "list"
    assert VALUE_KIND["range"] == "pair"
    assert VALUE_KIND["isnull"] == "bool"
    assert VALUE_KIND["icontains"] == "text"
    assert VALUE_KIND["exact"] == "scalar"
