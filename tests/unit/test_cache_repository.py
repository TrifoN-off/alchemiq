from __future__ import annotations

import pytest

from alchemiq.cache import reset_cache
from alchemiq.cache.backend import configure_cache
from alchemiq.cache.memory import InMemoryCache
from alchemiq.exceptions import ConfigError
from alchemiq.repository.base import Repository
from tests.unit._cache_models import KItem

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean():
    reset_cache()
    yield
    reset_cache()


def test_resolve_cache_off_by_default() -> None:
    assert Repository(KItem)._resolve_cache() is None


def test_resolve_cache_true_uses_global() -> None:
    backend = InMemoryCache()
    configure_cache(backend=backend)
    assert Repository(KItem, cache=True)._resolve_cache() is backend


def test_resolve_cache_true_without_global_raises() -> None:
    with pytest.raises(ConfigError, match="configure_cache"):
        Repository(KItem, cache=True)._resolve_cache()


def test_resolve_cache_instance_used_directly() -> None:
    backend = InMemoryCache()
    assert Repository(KItem, cache=backend)._resolve_cache() is backend


def test_subclass_class_attr_opt_in() -> None:
    backend = InMemoryCache()
    configure_cache(backend=backend)

    class KRepo(Repository[KItem]):
        cache = True

    assert KRepo()._resolve_cache() is backend
