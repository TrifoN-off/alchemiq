from __future__ import annotations

import inspect

import pytest

from alchemiq import Model, Repository
from alchemiq.runtime.providers import (
    db_session,
    repository,
    resolve_repository,
    unit_of_work,
)
from alchemiq.types import PK

pytestmark = pytest.mark.unit


class ProvidersRow(Model):
    __tablename__ = "providers_prov_row"
    id: PK[int]
    name: str


class ProvidersRepo(Repository[ProvidersRow]):
    pass


def test_resolve_from_model() -> None:
    assert resolve_repository(ProvidersRow).model is ProvidersRow


def test_resolve_from_repository_subclass() -> None:
    repo = resolve_repository(ProvidersRepo)
    assert isinstance(repo, Repository)
    assert repo.model is ProvidersRow


def test_resolve_passes_through_instance() -> None:
    inst = ProvidersRepo()
    assert resolve_repository(inst) is inst


def test_repository_provider_returns_shared_instance() -> None:
    provide = repository(ProvidersRow)
    assert provide() is provide()


def test_uow_and_session_are_async_generators() -> None:
    assert inspect.isasyncgenfunction(unit_of_work)
    assert inspect.isasyncgenfunction(db_session)


def test_fastapi_deps_reexports_the_same_objects() -> None:
    from alchemiq.fastapi import deps as fa

    assert fa.repository is repository
    assert fa.resolve_repository is resolve_repository
    assert fa.unit_of_work is unit_of_work
    assert fa.db_session is db_session
