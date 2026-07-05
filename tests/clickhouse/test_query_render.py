import pytest

from alchemiq.clickhouse import ClickHouseModel, MergeTree
from alchemiq.clickhouse.query import ClickHouseQuerySet, render_sql
from alchemiq.clickhouse.types import UInt32


class _Q(ClickHouseModel):
    user_id: int = UInt32()
    country: str

    class Meta:
        engine = MergeTree(order_by=("user_id",))


@pytest.mark.unit
def test_render_filter_eq_inlines_literal():
    qs = ClickHouseQuerySet(_Q).filter(country="US")
    sql = render_sql(qs)
    assert "FROM _q" in sql
    assert "WHERE" in sql and "country" in sql and "'US'" in sql


@pytest.mark.unit
def test_render_order_limit():
    qs = ClickHouseQuerySet(_Q).order_by("-user_id").limit(10)
    sql = render_sql(qs)
    assert "ORDER BY" in sql and "user_id" in sql and "DESC" in sql
    assert "LIMIT 10" in sql


@pytest.mark.unit
def test_render_gt_lookup():
    qs = ClickHouseQuerySet(_Q).filter(user_id__gt=1000)
    sql = render_sql(qs)
    assert "user_id > 1000" in sql.replace("  ", " ")


@pytest.mark.unit
def test_render_only_projects_columns():
    qs = ClickHouseQuerySet(_Q).only("user_id")
    sql = render_sql(qs)
    assert "user_id" in sql
    assert "country" not in sql  # projection drops unlisted columns


@pytest.mark.unit
def test_render_offset():
    qs = ClickHouseQuerySet(_Q).limit(10).offset(5)
    sql = render_sql(qs)
    # CH uses MySQL-style LIMIT offset, count syntax: "LIMIT 5, 10"
    assert "LIMIT 5, 10" in sql


@pytest.mark.unit
def test_render_distinct():
    qs = ClickHouseQuerySet(_Q).distinct()
    sql = render_sql(qs)
    assert "DISTINCT" in sql


@pytest.mark.unit
def test_render_exclude_negates():
    qs = ClickHouseQuerySet(_Q).exclude(country="US")
    sql = render_sql(qs)
    assert "country" in sql and "'US'" in sql
    assert "!=" in sql or "NOT" in sql.upper()  # negated predicate
