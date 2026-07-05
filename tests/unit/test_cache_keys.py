from __future__ import annotations

import pytest

from alchemiq.cache import keys
from alchemiq.query.queryset import QuerySet
from tests.unit._cache_models import KItem  # tiny model defined below

pytestmark = pytest.mark.unit


def test_key_formats() -> None:
    assert keys.version_key("aq", "cache_kitem") == "aq:cache_kitem:ver"
    assert keys.obj_key("aq", "cache_kitem", 7) == "aq:cache_kitem:obj:7"
    assert keys.query_key("aq", "cache_kitem", 3, "abc") == "aq:cache_kitem:q:3:abc"
    assert keys.count_key("aq", "cache_kitem", 3, "abc") == "aq:cache_kitem:cnt:3:abc"
    assert keys.exists_key("aq", "cache_kitem", 3, "abc") == "aq:cache_kitem:ex:3:abc"


def test_fingerprint_is_deterministic() -> None:
    a = QuerySet(KItem).filter(name="x").order_by("id").limit(5)
    b = QuerySet(KItem).filter(name="x").order_by("id").limit(5)
    assert keys.query_fingerprint(a) == keys.query_fingerprint(b)


def test_fingerprint_varies_with_filter_order_and_limit() -> None:
    base = QuerySet(KItem).filter(name="x")
    assert keys.query_fingerprint(base) != keys.query_fingerprint(QuerySet(KItem).filter(name="y"))
    assert keys.query_fingerprint(base.order_by("id")) != keys.query_fingerprint(
        base.order_by("-id")
    )
    assert keys.query_fingerprint(base.limit(1)) != keys.query_fingerprint(base.limit(2))


def test_scalar_fingerprint_ignores_order_limit_offset() -> None:
    base = QuerySet(KItem).filter(name="x")
    assert keys.query_fingerprint(base.order_by("id").limit(5), scalar=True) == (
        keys.query_fingerprint(base, scalar=True)
    )
    assert keys.query_fingerprint(base.offset(10), scalar=True) == keys.query_fingerprint(
        base, scalar=True
    )
    # ...but still varies by filter
    assert keys.query_fingerprint(base, scalar=True) != keys.query_fingerprint(
        QuerySet(KItem).filter(name="y"), scalar=True
    )
