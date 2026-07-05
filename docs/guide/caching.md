# Caching

alchemiq provides an optional repository-level cache layer.  When enabled, reads
are served from cache and invalidated automatically on write.  The cache is
fail-open: a backend error is logged but never propagates to the caller.

---

## Installation

The in-process backend ({class}`~alchemiq.InMemoryCache`) is part of the core
package and requires no extra dependencies.  For Redis:

```bash
pip install "alchemiq[redis,postgres]"
```

---

## Configuring a backend

Call {func}`~alchemiq.configure_cache` once at startup, before any repository
uses the cache:

```python
from alchemiq.cache import InMemoryCache, configure_cache

# zero-dependency in-process cache (good for testing and single-process services)
configure_cache(backend=InMemoryCache(default_ttl=120))

# Redis (requires [redis] extra)
configure_cache(url="redis://localhost:6379/0")

# Redis with custom TTL and key namespace
configure_cache(url="redis://localhost:6379/0", default_ttl=300, namespace="myapp")
```

{func}`~alchemiq.reset_cache` clears the global backend - useful in test
teardown:

```python
from alchemiq.cache import reset_cache

reset_cache()
```

---

## The CacheBackend protocol

{class}`~alchemiq.CacheBackend` is a structural (duck-typed) protocol.  Any
object that exposes the five async methods below satisfies it:

| Method | Description |
|---|---|
| ``get(key)`` | Return cached ``str`` or ``None`` on miss/expiry |
| ``set(key, value, *, ttl)`` | Store ``value`` with TTL in seconds |
| ``delete(*keys)`` | Delete one or more keys; no-ops on missing keys |
| ``incr(key)`` | Atomically increment an integer counter, return new value |
| ``scan_delete(match)`` | Delete all keys matching a glob pattern |

Plus two required attributes: ``default_ttl: int`` and ``namespace: str``.

``InMemoryCache`` implements this protocol in pure Python (no extra
dependencies).  ``RedisCache`` is built automatically by ``configure_cache``
when a Redis ``url`` is supplied.

---

## Enabling cache on a repository

Set ``cache = True`` on a ``Repository`` subclass, or pass it at construction time:

```python
from alchemiq import Repository
from alchemiq.cache import configure_cache, InMemoryCache

configure_cache(backend=InMemoryCache(default_ttl=60))

# subclass - attach cache as a class attribute
class UserRepository(Repository[User]):
    cache = True
    cache_ttl = 300   # override default TTL for this model

repo = UserRepository()

# ad-hoc - enable for one instance
repo = Repository(User, cache=True, cache_ttl=120)
```

When ``cache = True`` the repository resolves the backend registered by
``configure_cache``.  You may also pass a ``CacheBackend`` instance directly
(useful in tests):

```python
from alchemiq.cache import InMemoryCache

repo = Repository(User, cache=InMemoryCache(default_ttl=60))
```

### What is cached

| Operation | Cached |
|---|---|
| ``get(pk)`` | Yes - per-object key |
| ``filter(...).all()`` | Yes - version-keyed query key |
| ``filter(...).count()`` | Yes |
| ``filter(...).exists()`` | Yes |
| ``create``, ``update``, ``delete`` | No - invalidates cache |

The cache uses a **version counter per table**.  Any write bumps the counter,
which invalidates all version-keyed query results without a costly scan.

---

## Manual invalidation

```python
# invalidate one object by primary key
await repo.cache_evict(pk=42)

# invalidate all cached results for this model
await repo.cache_clear()
```

``cache_evict`` drops the per-object key and bumps the table version counter.
``cache_clear`` bumps the version counter and scans-deletes all per-object keys
for the model.
