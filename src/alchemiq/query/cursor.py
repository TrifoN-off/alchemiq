"""Keyset (cursor) pagination helpers: encoding, decoding, and seek-predicate construction."""

from __future__ import annotations

import base64
import json
from typing import Any

from sqlalchemy import and_, or_

from alchemiq._internal.wire import decode_scalar, encode_scalar
from alchemiq.exceptions import InvalidCursorError
from alchemiq.query.queryset import pk_name


def _parse_spec(spec: str) -> tuple[str, bool]:
    """Return (field_name, descending)."""
    if spec.startswith("-"):
        return spec[1:], True
    return spec, False


def effective_order(model: type, order: tuple[str, ...]) -> tuple[str, ...]:
    """Deterministic total order: user order + PK tiebreaker (asc) if PK absent."""
    if not order:
        return (pk_name(model),)
    pk = pk_name(model)
    names = {_parse_spec(spec)[0] for spec in order}
    return order if pk in names else (*order, pk)


def reverse_order(order: tuple[str, ...]) -> tuple[str, ...]:
    """Invert every direction specifier in *order* (used for backward pagination)."""
    return tuple(spec[1:] if spec.startswith("-") else f"-{spec}" for spec in order)


def encode_cursor(model: type, order: tuple[str, ...], row: Any) -> str:
    """Encode *row*'s ordering-field values into an opaque urlsafe-base64 cursor token."""
    names = (_parse_spec(s)[0] for s in order)
    payload = [[name, encode_scalar(getattr(row, name))] for name in names]
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(token: str, model: type, order: tuple[str, ...]) -> list[Any]:
    """Decode a cursor token back to a list of typed field values matching *order*.

    :param token: opaque urlsafe-base64 cursor string from ``encode_cursor``.
    :param model: the model class whose field types are used for decoding.
    :param order: the tuple of order specs the cursor was created with.
    :return: list of decoded Python values in the same order as *order*.
    :raises InvalidCursorError: if the token is malformed, mismatches the current
        ordering, or references an unknown field.
    """
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as e:
        raise InvalidCursorError("Malformed cursor token") from e
    if not isinstance(payload, list) or len(payload) != len(order):
        raise InvalidCursorError("Cursor does not match the current ordering")
    fields: dict[str, Any] = getattr(model, "__alchemiq_fields__", {})
    values: list[Any] = []
    for spec, entry in zip(order, payload, strict=True):
        name = _parse_spec(spec)[0]
        if not (isinstance(entry, list) and len(entry) == 2 and entry[0] == name):
            raise InvalidCursorError("Cursor does not match the current ordering")
        if name not in fields:
            raise InvalidCursorError(f"Unknown cursor field {name!r}")
        values.append(decode_scalar(entry[1], fields[name].python_type))
    return values


def build_seek(model: type, order: tuple[str, ...], values: list[Any], *, backward: bool) -> Any:
    """Lexicographic keyset predicate: rows strictly past *values* in travel direction.

    OR_i [ c_1 = v_1 AND ... AND c_{i-1} = v_{i-1} AND c_i OP_i v_i ], OP_i derived per
    column direction, inverted when paging backward.
    """
    names = [_parse_spec(spec)[0] for spec in order]
    descs = [_parse_spec(spec)[1] for spec in order]
    ors: list[Any] = []
    for i, name in enumerate(names):
        col = getattr(model, name)
        gt = descs[i] == backward  # ASC fwd -> '>', DESC fwd -> '<', backward inverts both
        cmp = col > values[i] if gt else col < values[i]
        eq_prefix = [getattr(model, names[j]) == values[j] for j in range(i)]
        ors.append(and_(*eq_prefix, cmp) if eq_prefix else cmp)
    return or_(*ors)
