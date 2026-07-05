"""Session-level soft-delete filtering for relationship loads and traversal joins.

The ``QuerySet`` compiler puts ``deleted_at IS NULL`` on the *root* model only.
Relationship loads (``select_related`` / ``prefetch_related``) and traversal-join
targets are compiled by SQLAlchemy itself, so tombstones would leak through them.
This module closes that gap with the canonical SQLAlchemy global-criteria recipe:
a ``do_orm_execute`` listener that attaches ``with_loader_criteria`` for every
registered soft-delete model to each top-level ORM SELECT.

The listener is bound to :class:`AlchemiqSession` - the sync session class used
under alchemiq's ``AsyncSession`` - so user-owned native sessions are never
affected. ``QuerySet`` stamps its deleted-mode into the statement's execution
options; ``with_deleted()`` / ``only_deleted()`` therefore disable the criteria
for the whole statement, relationship loads included.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

from alchemiq.query.soft_delete import EXCLUDE

DELETED_MODE_OPTION = "alchemiq_deleted"

_criteria_cache: tuple[int, tuple[Any, ...]] = (0, ())


class AlchemiqSession(Session):
    """Sync ``Session`` subclass carrying alchemiq's soft-delete listener."""


def _soft_delete_criteria() -> tuple[Any, ...]:
    """Return cached ``with_loader_criteria`` options for all soft-delete models."""
    global _criteria_cache
    from alchemiq.model.registry import mapper_registry
    from alchemiq.query.soft_delete import is_soft_delete

    mappers = mapper_registry.mappers
    if _criteria_cache[0] != len(mappers):
        _criteria_cache = (
            len(mappers),
            tuple(
                with_loader_criteria(
                    mapper.class_,
                    mapper.class_.deleted_at.is_(None),
                    include_aliases=True,
                )
                for mapper in mappers
                if is_soft_delete(mapper.class_)
            ),
        )
    return _criteria_cache[1]


@event.listens_for(AlchemiqSession, "do_orm_execute")
def _apply_soft_delete_criteria(state: Any) -> None:
    # Loader queries (column/relationship loads) are skipped: propagate_to_loaders
    # already carries the criteria down from the top-level statement.
    if not state.is_select or state.is_column_load or state.is_relationship_load:
        return
    if state.execution_options.get(DELETED_MODE_OPTION, EXCLUDE) != EXCLUDE:
        return
    options = _soft_delete_criteria()
    if options:
        state.statement = state.statement.options(*options)
