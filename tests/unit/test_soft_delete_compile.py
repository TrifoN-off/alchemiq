import pytest

from alchemiq import Model, QuerySet
from alchemiq.exceptions import ConfigError
from alchemiq.types import PK

pytestmark = pytest.mark.unit


class SoftDoc(Model):
    __tablename__ = "soft_compile_doc"
    id: PK[int]
    name: str

    class Meta:
        soft_delete = True


class PlainDoc(Model):
    __tablename__ = "soft_compile_plain_compile_doc"
    id: PK[int]
    name: str


def _sql(qs: QuerySet) -> str:
    return str(qs.compile())


def test_default_excludes_deleted():
    assert "deleted_at IS NULL" in _sql(QuerySet(SoftDoc).filter(name="x"))


def test_with_deleted_drops_predicate():
    sql = _sql(QuerySet(SoftDoc).with_deleted().filter(name="x"))
    assert "deleted_at IS NULL" not in sql
    assert "deleted_at IS NOT NULL" not in sql


def test_only_deleted_selects_tombstones():
    assert "deleted_at IS NOT NULL" in _sql(QuerySet(SoftDoc).only_deleted())


def test_plain_model_has_no_predicate():
    assert "deleted_at" not in _sql(QuerySet(PlainDoc).filter(name="x"))


def test_chain_methods_on_plain_model_raise():
    with pytest.raises(ConfigError):
        QuerySet(PlainDoc).with_deleted()
    with pytest.raises(ConfigError):
        QuerySet(PlainDoc).only_deleted()


def test_deleted_mode_literal_matches_constants() -> None:
    from typing import get_args

    from alchemiq.query.soft_delete import EXCLUDE, INCLUDE, ONLY, DeletedMode

    assert set(get_args(DeletedMode)) == {EXCLUDE, INCLUDE, ONLY} == {"exclude", "include", "only"}
