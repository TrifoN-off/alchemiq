"""Serialization and deserialization of ``Q`` objects to JSON-safe structures and bytes."""

from __future__ import annotations

import base64
import json
from typing import Any

from alchemiq._internal.wire import decode_scalar, encode_scalar
from alchemiq.exceptions import (
    DeserializationError,
    DisallowedFieldError,
    UnknownOperatorError,
)
from alchemiq.query.lookups import BOOL, LIST, PAIR, RAW, TEXT, VALUE_KIND, parse_key
from alchemiq.query.q import Q

_CONN_CODE = {Q.AND: 0, Q.OR: 1}
_CODE_CONN = {0: Q.AND, 1: Q.OR}


def to_data(q: Q) -> list[Any]:
    """Compact tree: node [conn, neg, children]; leaf [key, value]."""
    children: list[Any] = []
    for child in q.children:
        if isinstance(child, Q):
            children.append(to_data(child))
        else:
            key, value = child
            _path, op = parse_key(key)
            children.append([key, _encode_value(op, value)])
    return [_CONN_CODE[q.connector], int(q.negated), children]


def _encode_value(op: str, value: Any) -> Any:
    kind = VALUE_KIND.get(op)
    if kind in (LIST, PAIR):
        return [encode_scalar(v) for v in value]
    if kind in (BOOL, TEXT, RAW):
        return value
    return encode_scalar(value)


def from_data(
    data: Any, model: type, allow: set[str] | None = None, deny: set[str] | None = None
) -> Q:
    """Reconstruct a ``Q`` from a ``to_data`` payload, validating fields against *model*.

    :param data: nested list produced by ``to_data``.
    :param model: model class used to validate field names and resolve Python types.
    :param allow: explicit allow-list of field paths; required to permit traversal fields.
    :param deny: optional deny-list of field paths.
    :raises DeserializationError: if the payload structure is invalid or JSON is malformed.
    :raises DisallowedFieldError: if a field is denied, absent from the allow-list, or unknown.
    :raises UnknownOperatorError: if the payload contains an unrecognised lookup operator.
    """
    if not (isinstance(data, list) and len(data) == 3 and isinstance(data[2], list)):
        raise DeserializationError(f"Malformed Q node: {data!r}")
    conn_code, neg, raw_children = data
    if conn_code not in _CODE_CONN:
        raise DeserializationError(f"Bad connector code {conn_code!r}")
    q = Q()
    q.connector = _CODE_CONN[conn_code]
    q.negated = bool(neg)
    children: list[Any] = []
    for raw in raw_children:
        if not isinstance(raw, list) or not raw:
            raise DeserializationError(f"Malformed child: {raw!r}")
        if isinstance(raw[0], str):  # leaf [key, value]
            children.append(_decode_leaf(raw, model, allow, deny))
        else:  # nested node
            children.append(from_data(raw, model, allow, deny))
    q.children = children
    return q


def _decode_leaf(
    raw: list[Any], model: type, allow: set[str] | None, deny: set[str] | None
) -> tuple[str, Any]:
    if len(raw) != 2:
        raise DeserializationError(f"Malformed leaf: {raw!r}")
    key, value = raw
    _path, op = parse_key(key)
    if op not in VALUE_KIND:
        raise UnknownOperatorError(f"Unknown operator in {key!r}")
    field = "__".join(_path)
    python_type = _check_and_resolve(field, model, allow, deny)
    return key, _decode_value(op, value, python_type)


def _check_and_resolve(
    field: str, model: type, allow: set[str] | None, deny: set[str] | None
) -> type:
    """Whitelist check + resolve terminal python_type (own columns + opt-in traversal)."""
    path = field.split("__")

    if deny and field in deny:
        raise DisallowedFieldError(f"Field {field!r} is denied")

    if allow is not None:
        if field not in allow:
            raise DisallowedFieldError(f"Field {field!r} not in allow-list")
    elif len(path) > 1:
        # Default policy: traversal must be explicitly allow-listed.
        raise DisallowedFieldError(
            f"Relationship traversal {field!r} not permitted by default; add it to allow"
        )

    current = model
    for segment in path[:-1]:
        rels: dict[str, Any] = getattr(current, "__alchemiq_relationships__", {})
        rel = rels.get(segment)
        if rel is None:
            raise DisallowedFieldError(f"Unknown relationship {segment!r} on {current.__name__}")
        current = rel.target

    fields: dict[str, Any] = getattr(current, "__alchemiq_fields__", {})
    terminal = path[-1]
    if terminal not in fields:
        raise DisallowedFieldError(f"Field {terminal!r} not permitted on {current.__name__}")
    return fields[terminal].python_type


def _decode_value(op: str, value: Any, python_type: type) -> Any:
    kind = VALUE_KIND.get(op)
    if kind in (LIST, PAIR):
        if not isinstance(value, list):
            raise DeserializationError(
                f"Operator {op!r} expects a list value, got {type(value).__name__}"
            )
        if kind == PAIR and len(value) != 2:
            raise DeserializationError(
                f"Operator {op!r} expects a 2-element value, got {len(value)}"
            )
        decoded = [decode_scalar(v, python_type) for v in value]
        return tuple(decoded) if kind == PAIR else decoded
    if kind in (BOOL, TEXT, RAW):
        return value
    return decode_scalar(value, python_type)


def to_bytes(q: Q) -> bytes:
    """Serialize Q to compact UTF-8 JSON bytes."""
    return json.dumps(to_data(q), separators=(",", ":")).encode("utf-8")


def to_base64(q: Q) -> str:
    """Serialize Q to urlsafe base64 string."""
    return base64.urlsafe_b64encode(to_bytes(q)).decode("ascii")


def from_bytes(
    data: bytes, model: type, allow: set[str] | None = None, deny: set[str] | None = None
) -> Q:
    """Deserialize Q from JSON bytes."""
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise DeserializationError("Invalid JSON payload") from e
    return from_data(parsed, model, allow, deny)


def from_base64(
    s: str, model: type, allow: set[str] | None = None, deny: set[str] | None = None
) -> Q:
    """Deserialize Q from urlsafe base64 string."""
    try:
        data = base64.urlsafe_b64decode(s.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as e:
        raise DeserializationError("Invalid base64 payload") from e
    return from_bytes(data, model, allow, deny)
