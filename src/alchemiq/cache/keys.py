"""Cache key constructors and query fingerprinting.

Key schema:
  ``<ns>:<table>:ver``            - table version counter (incremented on writes)
  ``<ns>:<table>:obj:<pk>``       - single-row cache
  ``<ns>:<table>:q:<ver>:<fp>``   - list query cache
  ``<ns>:<table>:cnt:<ver>:<fp>`` - count query cache
  ``<ns>:<table>:ex:<ver>:<fp>``  - exists query cache
"""

from __future__ import annotations

from hashlib import blake2b
from typing import TYPE_CHECKING

from alchemiq.query.serialize import to_bytes

if TYPE_CHECKING:
    from alchemiq.query.queryset import QuerySet


def version_key(ns: str, table: str) -> str:
    """Return the version-counter key for a table (``<ns>:<table>:ver``)."""
    return f"{ns}:{table}:ver"


def obj_key(ns: str, table: str, pk: object) -> str:
    """Return the single-row cache key (``<ns>:<table>:obj:<pk>``)."""
    return f"{ns}:{table}:obj:{pk}"


def query_key(ns: str, table: str, ver: int, fp: str) -> str:
    """Return the list-query cache key (``<ns>:<table>:q:<ver>:<fp>``)."""
    return f"{ns}:{table}:q:{ver}:{fp}"


def count_key(ns: str, table: str, ver: int, fp: str) -> str:
    """Return the count-query cache key (``<ns>:<table>:cnt:<ver>:<fp>``)."""
    return f"{ns}:{table}:cnt:{ver}:{fp}"


def exists_key(ns: str, table: str, ver: int, fp: str) -> str:
    """Return the exists-query cache key (``<ns>:<table>:ex:<ver>:<fp>``)."""
    return f"{ns}:{table}:ex:{ver}:{fp}"


def query_fingerprint(qs: QuerySet, *, scalar: bool = False) -> str:
    """16-byte blake2b digest (32 hex chars) of the query's filter + shape.

    ``scalar`` drops order/limit/offset.
    """
    where_bytes = b"&".join(to_bytes(q) for q in qs._where)
    if scalar:
        shape = repr((qs._distinct, qs._deleted))
    else:
        shape = repr((qs._order, qs._limit, qs._offset, qs._distinct, qs._deleted))
    return blake2b(where_bytes + shape.encode("utf-8"), digest_size=16).hexdigest()
