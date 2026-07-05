from __future__ import annotations

import base64
import uuid
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any


def encode_scalar(value: Any) -> Any:
    """Python value -> JSON-native. Dispatch by runtime type (model-free)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if isinstance(value, Enum):
        return value.value
    return value  # assume already JSON-native (dict/list for jcontains payloads)


def decode_scalar(raw: Any, python_type: type) -> Any:
    """JSON-native -> python value, keyed by the target column's python_type."""
    if python_type is Decimal:
        return Decimal(raw)
    if python_type is datetime:
        return datetime.fromisoformat(raw)
    if python_type is date:
        return date.fromisoformat(raw)
    if python_type is time:
        return time.fromisoformat(raw)
    if python_type is uuid.UUID:
        return uuid.UUID(raw)
    if python_type is bytes:
        return base64.b64decode(raw)
    if isinstance(python_type, type) and issubclass(python_type, Enum):
        return python_type(raw)
    return raw
