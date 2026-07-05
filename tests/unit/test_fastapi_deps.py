"""DI providers: repository resolution (no DB needed)."""

from __future__ import annotations

import pytest

from alchemiq import Model, Repository
from alchemiq.fastapi.deps import repository, resolve_repository
from alchemiq.types import PK

pytestmark = pytest.mark.unit


class FapiDepsRow(Model):
    __tablename__ = "fapi_deps_dep_row"
    id: PK[int]
    name: str


class FapiDepsRepo(Repository[FapiDepsRow]):
    pass


def test_resolve_from_model() -> None:
    assert resolve_repository(FapiDepsRow).model is FapiDepsRow


def test_resolve_from_repository_subclass() -> None:
    repo = resolve_repository(FapiDepsRepo)
    assert isinstance(repo, Repository)
    assert repo.model is FapiDepsRow


def test_resolve_passes_through_instance() -> None:
    inst = FapiDepsRepo()
    assert resolve_repository(inst) is inst


def test_repository_provider_returns_shared_instance() -> None:
    provide = repository(FapiDepsRow)
    assert provide() is provide()
    assert provide().model is FapiDepsRow
