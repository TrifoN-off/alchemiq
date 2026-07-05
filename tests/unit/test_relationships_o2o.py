from __future__ import annotations

import pytest

from alchemiq import Model, OneToOne
from alchemiq.model.relationships import detect_relationship
from alchemiq.types import PK

pytestmark = pytest.mark.unit


class O2OProfile(Model):
    __tablename__ = "o2o_unit_profile"
    id: PK[int]
    bio: str


class O2OUser(Model):
    __tablename__ = "o2o_unit_user"
    id: PK[int]
    profile: OneToOne[O2OProfile]


def test_detect_one_to_one() -> None:
    rel = detect_relationship(OneToOne[O2OProfile])
    assert rel.kind == "one_to_one"
    assert rel.target is O2OProfile


def test_o2o_fk_is_unique() -> None:
    col = O2OUser.__table__.c.profile_id
    assert col.unique is True
    assert col.nullable is False


def test_o2o_registered_and_fk_field() -> None:
    assert O2OUser.__alchemiq_relationships__["profile"].direction == "one_to_one"
    assert "profile_id" in O2OUser.__alchemiq_fields__


def test_o2o_reverse_is_scalar_singular() -> None:
    # reverse accessor on the target is singular `_snake(cls)`, not `<class>_set`
    assert "o2o_user" in O2OProfile.__alchemiq_relationships__
