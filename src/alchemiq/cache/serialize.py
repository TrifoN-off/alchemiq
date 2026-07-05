"""JSON serialization helpers for cached model instances and scalar values.

Password/Encrypted fields are always excluded from serialized output.
"""

from __future__ import annotations

import json
from typing import Any

from alchemiq.model.serialization import from_dict, to_dict
from alchemiq.types.special import Encrypted
from alchemiq.types.strings import Password


def secret_fields(model: type) -> frozenset[str]:
    """Field names that must never reach the cache (Password/Encrypted). Memoized on the model."""
    cached: frozenset[str] | None = getattr(model, "__alchemiq_cache_exclude__", None)
    if cached is not None:
        return cached
    fields: dict[str, Any] = model.__alchemiq_fields__  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    result = frozenset(n for n, f in fields.items() if isinstance(f, (Password, Encrypted)))
    model.__alchemiq_cache_exclude__ = result  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    return result


def encode_row(instance: Any) -> str:
    """Serialize a model instance to a JSON string, excluding secret fields."""
    model = type(instance)
    return json.dumps(to_dict(instance, mode="json", exclude=secret_fields(model)))


def decode_row(model: type, s: str) -> Any:
    """Deserialize a JSON string back into a model instance."""
    return from_dict(model, json.loads(s))


def encode_rows(rows: list[Any]) -> str:
    """Serialize a list of model instances to a JSON string, excluding secret fields."""
    out = [to_dict(r, mode="json", exclude=secret_fields(type(r))) for r in rows]
    return json.dumps(out)


def decode_rows(model: type, s: str) -> list[Any]:
    """Deserialize a JSON string back into a list of model instances."""
    return [from_dict(model, d) for d in json.loads(s)]


def encode_int(n: int) -> str:
    """Encode an integer as a string for cache storage."""
    return str(n)


def decode_int(s: str) -> int:
    """Decode a cached integer string."""
    return int(s)


def encode_bool(b: bool) -> str:
    """Encode a boolean as ``"1"`` or ``"0"`` for cache storage."""
    return "1" if b else "0"


def decode_bool(s: str) -> bool:
    """Decode a cached boolean string (``"1"`` -> ``True``, anything else -> ``False``)."""
    return s == "1"
