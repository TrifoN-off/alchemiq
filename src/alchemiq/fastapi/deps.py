"""FastAPI dependency providers re-exported from :mod:`alchemiq.runtime.providers`.

Use these as FastAPI ``Depends`` targets to inject a :class:`.Repository`,
:class:`.UnitOfWork`, or ``AsyncSession`` scoped to each HTTP request.
"""

from __future__ import annotations

from alchemiq.runtime.providers import (
    db_session,
    repository,
    resolve_repository,
    unit_of_work,
)

__all__ = ["db_session", "repository", "resolve_repository", "unit_of_work"]
