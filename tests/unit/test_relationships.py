import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from alchemiq import ForeignKey, Model
from alchemiq.exceptions import ConfigError
from alchemiq.types import PK, Maybe


class Org(Model):
    id: PK[int]
    name: str


class Member(Model):
    id: PK[int]
    org: Org  # required -> RESTRICT
    sponsor: Org | None = ForeignKey(related_name="sponsored")  # optional -> SET NULL
    mentor: Maybe[Org] = ForeignKey(related_name="mentored")  # optional -> SET NULL


def test_fk_column_materialized():
    assert "org_id" in Member.__alchemiq_fields__
    assert hasattr(Member, "org_id")


def test_relationship_registered():
    rel = Member.__alchemiq_relationships__["org"]
    assert rel.target is Org
    assert rel.direction == "many_to_one"
    assert rel.fk_attr == "org_id"


def test_reverse_registered_on_target():
    # default related_name for Member -> 'member_set'
    assert "member_set" in Org.__alchemiq_relationships__
    assert Org.__alchemiq_relationships__["member_set"].target is Member
    assert Org.__alchemiq_relationships__["sponsored"].target is Member


def test_on_delete_inferred_restrict_for_required():
    ddl = str(CreateTable(Member.__table__).compile(dialect=postgresql.dialect()))
    assert "ON DELETE RESTRICT" in ddl


def test_on_delete_inferred_set_null_for_optional():
    ddl = str(CreateTable(Member.__table__).compile(dialect=postgresql.dialect()))
    assert "ON DELETE SET NULL" in ddl


def test_explicit_cascade_overrides():
    class DocCascade(Model):
        __tablename__ = "doc_cascade"
        id: PK[int]
        owner: Org = ForeignKey(on_delete="CASCADE", related_name="docs")

    ddl = str(CreateTable(DocCascade.__table__).compile(dialect=postgresql.dialect()))
    assert "ON DELETE CASCADE" in ddl


def test_duplicate_related_name_raises():
    with pytest.raises(ConfigError):

        class Bad(Model):
            id: PK[int]
            a: Org  # default related_name 'bad_set'
            b: Org  # also 'bad_set' -> collision


def test_fk_field_config_reflects_nullability():
    assert Member.__alchemiq_fields__["org_id"].config.nullable is False
    assert Member.__alchemiq_fields__["sponsor_id"].config.nullable is True
