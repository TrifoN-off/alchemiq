from __future__ import annotations

import pytest

from alchemiq.cache.memory import InMemoryCache
from alchemiq.query.queryset import QuerySet
from tests.unit._cache_models import KItem

pytestmark = pytest.mark.unit


def test_clone_propagates_cache_fields() -> None:
    cache = InMemoryCache()
    qs = QuerySet(KItem, cache=cache, cache_ttl=99)
    cloned = qs.filter(name="x").order_by("id").limit(3)
    assert cloned._cache is cache
    assert cloned._cache_ttl == 99


def test_should_cache_rows_bypass_conditions() -> None:
    cache = InMemoryCache()
    assert QuerySet(KItem, cache=cache)._should_cache_rows() is True
    assert QuerySet(KItem)._should_cache_rows() is False  # no cache
    assert QuerySet(KItem, cache=cache).only("name")._should_cache_rows() is False  # projection
    # select_related/prefetch_related also bypass (needs a relation; covered in integration)


def test_bare_queryset_has_no_cache() -> None:
    qs = QuerySet(KItem)
    assert qs._cache is None
    assert qs._cache_ttl is None
