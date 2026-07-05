from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from alchemiq import Model, OneToOne, Repository
from alchemiq.runtime.session import session_scope
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class O2OIntProfile(Model):
    __tablename__ = "o2o_profile"
    id: PK[int]
    bio: str


class O2OIntUser(Model):
    __tablename__ = "o2o_user"
    id: PK[int]
    profile: OneToOne[O2OIntProfile]


async def test_o2o_round_trip(configured_db) -> None:
    async with session_scope(write=True) as s:
        s.add(O2OIntProfile(id=1, bio="hi"))
        await s.flush()
        s.add(O2OIntUser(id=1, profile_id=1))
    user = await Repository(O2OIntUser).select_related("profile").filter(id=1).first()
    assert user is not None
    assert user.profile.bio == "hi"


async def test_o2o_reverse_scalar(configured_db) -> None:
    async with session_scope(write=True) as s:
        s.add(O2OIntProfile(id=2, bio="yo"))
        await s.flush()
        s.add(O2OIntUser(id=2, profile_id=2))
    profile = await Repository(O2OIntProfile).select_related("o2o_int_user").filter(id=2).first()
    assert profile is not None
    assert profile.o2o_int_user.id == 2  # scalar, not a collection
    assert not isinstance(profile.o2o_int_user, list)  # 1:1 reverse is scalar, not a collection


async def test_o2o_unique_enforced(configured_db) -> None:
    async with session_scope(write=True) as s:
        s.add(O2OIntProfile(id=3, bio="x"))
        await s.flush()
        s.add(O2OIntUser(id=3, profile_id=3))
    with pytest.raises(IntegrityError):
        async with session_scope(write=True) as s:
            s.add(O2OIntUser(id=4, profile_id=3))  # second FK to same profile -> unique violation
