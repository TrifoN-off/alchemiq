"""Thin wrappers around Alembic commands for the PostgreSQL migration backend."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from alchemiq.migrations.config import AlchemiqConfig
from alchemiq.migrations.errors import MigrationConfigError

if TYPE_CHECKING:
    from alembic.config import Config

_TEMPLATE = Path(__file__).parent / "_template"


def _versions_dir(config: AlchemiqConfig) -> Path:
    versions = Path(config.root) / config.migrations_dir / "postgres" / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    return versions


def _make_config(config: AlchemiqConfig) -> Config:
    from alembic.config import Config

    if config.postgres is None:
        raise MigrationConfigError("postgres is not configured in [tool.alchemiq.postgres]")
    from alchemiq.migrations.postgres.render import render_item
    from alchemiq.model.registry import metadata

    cfg = Config()
    cfg.set_main_option("script_location", str(_TEMPLATE))
    cfg.set_main_option("version_locations", str(_versions_dir(config)))
    cfg.set_main_option("path_separator", "os")
    cfg.attributes["target_metadata"] = metadata
    cfg.attributes["url"] = config.postgres.url
    cfg.attributes["render_item"] = render_item
    return cfg


def _suppress_empty(context: Any, revision: Any, directives: list[Any]) -> None:
    if directives and directives[0].upgrade_ops.is_empty():
        directives[:] = []
        print("No changes detected")


def makemigrations(config: AlchemiqConfig, message: str | None) -> None:
    """Autogenerate a new Alembic revision by diffing models against the database.

    Prints "No changes detected" and writes no file when the diff is empty.
    """
    from alembic import command

    command.revision(
        _make_config(config),
        message=message or "auto",
        autogenerate=True,
        process_revision_directives=_suppress_empty,
    )


def migrate(config: AlchemiqConfig) -> None:
    """Apply all pending Alembic revisions up to ``head``."""
    from alembic import command

    command.upgrade(_make_config(config), "head")


def rollback(config: AlchemiqConfig) -> None:
    """Revert the most recently applied Alembic revision (downgrade by one step)."""
    from alembic import command

    command.downgrade(_make_config(config), "-1")


def history(config: AlchemiqConfig) -> None:
    """Print the Alembic revision history, marking the current revision."""
    from alembic import command

    command.history(_make_config(config), indicate_current=True)


def showsql(config: AlchemiqConfig) -> None:
    """Print the SQL that would be executed to reach ``head``, without running it."""
    from alembic import command

    command.upgrade(_make_config(config), "head", sql=True)
