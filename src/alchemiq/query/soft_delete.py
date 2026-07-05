"""Soft-delete predicates, deleted-mode constants, and ``version_of`` accessor."""

from __future__ import annotations

from typing import Any, Final, Literal

from alchemiq.exceptions import ConfigError

EXCLUDE: Final = "exclude"
INCLUDE: Final = "include"
ONLY: Final = "only"

DeletedMode = Literal["exclude", "include", "only"]


def is_soft_delete(model: type) -> bool:
    """Return True if *model* was declared with ``Meta.soft_delete = True``."""
    meta = getattr(model, "__alchemiq_meta__", None)
    return bool(meta is not None and meta.soft_delete)


def is_versioned(model: type) -> bool:
    """Return True if *model* was declared with ``Meta.versioned = True``."""
    meta = getattr(model, "__alchemiq_meta__", None)
    return bool(meta is not None and meta.versioned)


def version_of(obj: Any) -> int:
    """Return the optimistic-lock ``_version`` counter of a versioned model instance.

    Read this value before an update to pass as ``expected_version`` for
    optimistic concurrency control.

    E.g.::

        user = await repo.get(id=1)
        version = version_of(user)
        await repo.update(1, expected_version=version, name="Ada")

    :param obj: a model instance whose class has ``Meta.versioned = True``.
    :return: the current ``_version`` integer.
    :raises ConfigError: if the model was not declared with ``Meta.versioned = True``.

    .. seealso:: :meth:`.Repository.update` - accepts ``expected_version``.
    """
    if not is_versioned(type(obj)):
        raise ConfigError(f"{type(obj).__name__} is not versioned; version_of() is unavailable")
    return obj._version


def deleted_predicate(model: type, mode: DeletedMode) -> Any | None:
    """Return the deleted_at SQL clause for *mode*, or None if no filter applies."""
    if mode == INCLUDE or not is_soft_delete(model):
        return None
    column = model.deleted_at  # ty: ignore[unresolved-attribute]
    return column.is_(None) if mode == EXCLUDE else column.is_not(None)
