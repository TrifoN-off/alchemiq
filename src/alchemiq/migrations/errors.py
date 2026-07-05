"""Migration-specific exception hierarchy."""

from __future__ import annotations

from alchemiq.exceptions import PersistenceError


class MigrationError(PersistenceError):
    """A migrations operation failed (config, autogenerate, apply, or rollback)."""


class MigrationConfigError(MigrationError):
    """Missing or invalid [tool.alchemiq] config, or an unresolved ${ENV} reference."""
