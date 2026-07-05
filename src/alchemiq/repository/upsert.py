"""PostgreSQL ``INSERT ... ON CONFLICT`` statement builder for bulk_upsert."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert

from alchemiq.exceptions import ConfigError
from alchemiq.query.queryset import pk_name


def _own_columns(model: type) -> set[str]:
    return set(getattr(model, "__alchemiq_fields__", {}))


def _set_columns(obj: Any) -> set[str]:
    """Own columns actually populated on the instance (by field name)."""
    return _own_columns(type(obj)) & set(obj.__dict__)


def _validate(model: type, cols: Sequence[str], own: set[str], label: str) -> None:
    bad = [c for c in cols if c not in own]
    if bad:
        raise ConfigError(
            f"bulk_upsert {label} references unknown columns {bad} on {model.__name__}"
        )


def build_upsert(
    model: type,
    objs: list[Any],
    *,
    conflict: Sequence[str] | None,
    update_fields: Sequence[str] | None,
    ignore_conflicts: bool,
) -> Any:
    """Build a PG ``INSERT ... ON CONFLICT`` statement for *objs*.

    The value-column set is the union of own columns populated across instances; every
    instance must populate that full set (heterogeneous rows raise ConfigError).
    """
    own = _own_columns(model)

    value_cols: set[str] = set()
    for obj in objs:
        value_cols |= _set_columns(obj)
    for obj in objs:
        missing = value_cols - _set_columns(obj)
        if missing:
            raise ConfigError(
                f"bulk_upsert requires uniform columns; a {type(obj).__name__} "
                f"instance is missing {sorted(missing)}"
            )

    conflict_cols = list(conflict) if conflict is not None else [pk_name(model)]
    _validate(model, conflict_cols, own, "conflict")
    if any(c not in value_cols for c in conflict_cols):
        raise ConfigError(
            f"bulk_upsert conflict columns {conflict_cols} must be set on every instance"
        )

    if update_fields is not None:
        update_cols = list(update_fields)
        _validate(model, update_cols, own, "update_fields")
    else:
        update_cols = [c for c in value_cols if c not in conflict_cols]

    ordered = list(value_cols)
    rows = [{c: getattr(obj, c) for c in ordered} for obj in objs]
    stmt = pg_insert(model).values(rows)
    if ignore_conflicts or not update_cols:
        return stmt.on_conflict_do_nothing(index_elements=conflict_cols)
    return stmt.on_conflict_do_update(
        index_elements=conflict_cols,
        set_={c: stmt.excluded[c] for c in update_cols},
    )
