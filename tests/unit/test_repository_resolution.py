from __future__ import annotations

import pytest

from alchemiq import Model, Repository
from alchemiq.types import PK

pytestmark = pytest.mark.unit


class ResUser(Model):
    __tablename__ = "repo_resolve_res_user"
    id: PK[int]
    name: str


class ResUserRepository(Repository[ResUser]):
    pass


def test_factory_sets_model():
    assert Repository(ResUser).model is ResUser


def test_subclass_resolves_model_from_generic():
    assert ResUserRepository().model is ResUser


def test_filter_returns_queryset():
    from alchemiq.query import QuerySet

    assert isinstance(Repository(ResUser).filter(name="x"), QuerySet)


def test_no_model_raises():
    with pytest.raises(TypeError, match="Repository needs a model"):
        Repository()


async def test_update_or_create_falls_back_to_create_when_row_vanishes(monkeypatch) -> None:
    """If the matched row is deleted between lookup and update, update_or_create
    must not raise NotFoundError - it falls through to create()."""
    from alchemiq.exceptions import NotFoundError
    from alchemiq.repository.base import Repository as _Repo

    class _UoCRow(Model):
        __tablename__ = "repo_resolve_uoc_row"
        id: PK[int]
        name: str

    repo: _Repo = _Repo(_UoCRow)
    existing = _UoCRow(id=7, name="old")
    created_sentinel = _UoCRow(id=7, name="new")

    async def fake_get_or_none(**lookups):
        return existing

    async def fake_update(_id, **changes):
        raise NotFoundError("row deleted concurrently")

    async def fake_create(**values):
        return created_sentinel

    monkeypatch.setattr(repo, "get_or_none", fake_get_or_none)
    monkeypatch.setattr(repo, "update", fake_update)
    monkeypatch.setattr(repo, "create", fake_create)

    obj, created = await repo.update_or_create(defaults={"name": "new"}, id=7)
    assert obj is created_sentinel
    assert created is True
