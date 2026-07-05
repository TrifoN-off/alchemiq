from __future__ import annotations

import pytest

from alchemiq import ManyToMany, Model
from alchemiq.exceptions import ConfigError
from alchemiq.model.registry import metadata
from alchemiq.model.relationships import detect_relationship
from alchemiq.types import PK

pytestmark = pytest.mark.unit


class M2MTag(Model):
    __tablename__ = "m2m_unit_tag"
    id: PK[int]
    name: str


class M2MPost(Model):
    __tablename__ = "m2m_unit_post"
    id: PK[int]
    title: str
    tags: list[M2MTag]


def test_detect_m2m() -> None:
    rel = detect_relationship(list[M2MTag])
    assert rel.kind == "many_to_many"
    assert rel.target is M2MTag


def test_detect_list_of_scalar_is_not_relationship() -> None:
    assert detect_relationship(list[int]).kind == ""


def test_m2m_registered() -> None:
    info = M2MPost.__alchemiq_relationships__["tags"]
    assert info.direction == "many_to_many"
    assert info.target is M2MTag
    assert info.fk_attr is None


def test_m2m_reverse_backref_registered() -> None:
    assert "m2m_post_set" in M2MTag.__alchemiq_relationships__


def test_m2m_assoc_table_built() -> None:
    assert "m2m_unit_post_m2m_unit_tag" in metadata.tables
    assoc = metadata.tables["m2m_unit_post_m2m_unit_tag"]
    assert set(assoc.c.keys()) == {"m2m_post_id", "m2m_tag_id"}


def test_m2m_no_scalar_fk_field() -> None:
    # M2M registers NO <name>_id field on the model (FKs live on the assoc table)
    assert "tags_id" not in M2MPost.__alchemiq_fields__


def test_m2m_double_to_same_target_collides() -> None:
    with pytest.raises(ConfigError):

        class DoubleM2M(Model):
            __tablename__ = "m2m_unit_double"
            id: PK[int]
            tags: list[M2MTag]
            more: list[M2MTag]  # same default reverse + same assoc-table name -> collision


def test_m2m_marker_overrides_resolve_collision() -> None:
    class TwoM2M(Model):
        __tablename__ = "m2m_unit_two"
        id: PK[int]
        tags: list[M2MTag]
        featured: list[M2MTag] = ManyToMany(  # type: ignore[assignment]
            related_name="featured_two_set", secondary="m2m_unit_two_featured"
        )

    assert "featured_two_set" in M2MTag.__alchemiq_relationships__
    assert "m2m_unit_two_featured" in metadata.tables


def test_detect_set_of_model_is_m2m() -> None:
    assert detect_relationship(set[M2MTag]).kind == "many_to_many"


def test_detect_multiarg_list_is_not_relationship() -> None:
    # len(get_args) != 1 must NOT crash - graceful "not a relationship"
    assert detect_relationship(list[int, str]).kind == ""
