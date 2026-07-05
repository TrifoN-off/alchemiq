"""FastStream dependency providers re-exported from :mod:`alchemiq.runtime.providers`.

Use these as FastStream ``Depends`` targets to inject a :class:`.Repository`,
:class:`.UnitOfWork`, or ``AsyncSession`` scoped to each consumed message.
"""

from __future__ import annotations

from alchemiq.runtime.providers import db_session, repository, unit_of_work

__all__ = ["db_session", "repository", "unit_of_work"]
