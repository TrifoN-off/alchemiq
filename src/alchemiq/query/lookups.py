"""Field lookup operators and key-parsing used by the Q compiler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

SCALAR = "scalar"
LIST = "list"
PAIR = "pair"
BOOL = "bool"
TEXT = "text"
RAW = "raw"


def escape_like(value: str) -> str:
    """Escape LIKE wildcards so user input matches literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _contains(c: Any, v: str) -> Any:
    return c.like(f"%{escape_like(v)}%", escape="\\")


def _icontains(c: Any, v: str) -> Any:
    return c.ilike(f"%{escape_like(v)}%", escape="\\")


def _startswith(c: Any, v: str) -> Any:
    return c.like(f"{escape_like(v)}%", escape="\\")


def _endswith(c: Any, v: str) -> Any:
    return c.like(f"%{escape_like(v)}", escape="\\")


LOOKUPS: dict[str, Callable[[Any, Any], Any]] = {
    "exact": lambda c, v: c == v,
    "ne": lambda c, v: c != v,
    "gt": lambda c, v: c > v,
    "gte": lambda c, v: c >= v,
    "lt": lambda c, v: c < v,
    "lte": lambda c, v: c <= v,
    "in": lambda c, v: c.in_(v),
    "nin": lambda c, v: c.not_in(v),
    "isnull": lambda c, v: c.is_(None) if v else c.is_not(None),
    "contains": _contains,
    "icontains": _icontains,
    "startswith": _startswith,
    "endswith": _endswith,
    "range": lambda c, v: c.between(v[0], v[1]),
    "jcontains": lambda c, v: c.op("@>")(v),
}

VALUE_KIND: dict[str, str] = {
    "exact": SCALAR,
    "ne": SCALAR,
    "gt": SCALAR,
    "gte": SCALAR,
    "lt": SCALAR,
    "lte": SCALAR,
    "in": LIST,
    "nin": LIST,
    "isnull": BOOL,
    "contains": TEXT,
    "icontains": TEXT,
    "startswith": TEXT,
    "endswith": TEXT,
    "range": PAIR,
    "jcontains": RAW,
}


def parse_key(key: str) -> tuple[list[str], str]:
    """Split 'a__b__op' -> (['a', 'b'], 'op'). Unknown trailing suffix ⇒ exact."""
    parts = key.split("__")
    if len(parts) > 1 and parts[-1] in LOOKUPS:
        return parts[:-1], parts[-1]
    return parts, "exact"
