"""Load and validate [tool.alchemiq] configuration from pyproject.toml."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

from sqlalchemy.engine import URL

from alchemiq.migrations.errors import MigrationConfigError

_ENV_RE = re.compile(r"\$\{([^}]+)\}")


def find_pyproject(start: Path | None = None) -> Path:
    """Search upward from *start* (default: cwd) for pyproject.toml.

    :raises MigrationConfigError: if no pyproject.toml is found in any ancestor directory.
    """
    cur = (start or Path.cwd()).resolve()
    for d in (cur, *cur.parents):
        candidate = d / "pyproject.toml"
        if candidate.is_file():
            return candidate
    raise MigrationConfigError(f"pyproject.toml not found (searched upward from {cur})")


def _interpolate(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    def repl(m: re.Match[str]) -> str:
        name = m.group(1)
        try:
            return os.environ[name]
        except KeyError as e:
            raise MigrationConfigError(f"environment variable {name!r} is not set") from e

    return _ENV_RE.sub(repl, value)


@dataclass(frozen=True)
class PostgresSettings:
    """Parsed [tool.alchemiq.postgres] connection settings."""

    host: str
    database: str
    username: str
    password: str
    port: int = 5432

    @property
    def url(self) -> str:
        """Return an asyncpg DSN string suitable for SQLAlchemy async engines."""
        return URL.create(
            "postgresql+asyncpg",
            username=self.username,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.database,
        ).render_as_string(hide_password=False)


@dataclass(frozen=True)
class ClickHouseSettings:
    """Parsed [tool.alchemiq.clickhouse] connection settings."""

    host: str
    database: str
    username: str
    password: str
    port: int = 8123
    secure: bool = False

    @property
    def client_kwargs(self) -> dict[str, Any]:
        """Return kwargs for the clickhouse-connect async client constructor."""
        return {
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "password": self.password,
            "database": self.database,
            "secure": self.secure,
        }


@dataclass(frozen=True)
class AlchemiqConfig:
    """Resolved alchemiq project configuration.

    :ivar root: Directory that contains pyproject.toml.
    :ivar models: Dotted module paths to import so models register themselves.
    :ivar migrations_dir: Relative path (from root) used as the migrations base directory.
    :ivar postgres: Parsed Postgres settings, or ``None`` if not configured.
    :ivar clickhouse: Parsed ClickHouse settings, or ``None`` if not configured.
    """

    root: Path
    models: tuple[str, ...] = ()
    migrations_dir: str = "migrations"
    postgres: PostgresSettings | None = None
    clickhouse: ClickHouseSettings | None = None


def _parse_postgres(t: dict[str, Any] | None) -> PostgresSettings | None:
    if t is None:
        return None
    try:
        return PostgresSettings(
            host=_interpolate(t["host"]),
            database=_interpolate(t["database"]),
            username=_interpolate(t["username"]),
            password=_interpolate(t["password"]),
            port=int(_interpolate(t.get("port", 5432))),
        )
    except KeyError as e:
        raise MigrationConfigError(f"missing required field {e} in [tool.alchemiq.postgres]") from e


def _parse_clickhouse(t: dict[str, Any] | None) -> ClickHouseSettings | None:
    if t is None:
        return None
    try:
        return ClickHouseSettings(
            host=_interpolate(t["host"]),
            database=_interpolate(t["database"]),
            username=_interpolate(t["username"]),
            password=_interpolate(t["password"]),
            port=int(_interpolate(t.get("port", 8123))),
            secure=bool(t.get("secure", False)),
        )
    except KeyError as e:
        raise MigrationConfigError(
            f"missing required field {e} in [tool.alchemiq.clickhouse]"
        ) from e


def load_config(start: Path | None = None) -> AlchemiqConfig:
    """Read and parse ``[tool.alchemiq]`` from the nearest pyproject.toml.

    Walks up from *start* (default: cwd) to locate pyproject.toml, then
    parses the ``[tool.alchemiq]`` section.  ``${ENV_VAR}`` placeholders in
    string values are expanded from the process environment.

    :param start: directory to begin the upward search; defaults to ``Path.cwd()``.
    :return: a fully resolved ``AlchemiqConfig`` instance.
    :raises MigrationConfigError: if pyproject.toml is not found, the
        ``[tool.alchemiq]`` section is missing, a required field is absent, or a
        referenced environment variable is unset.
    """
    pyproject = find_pyproject(start)
    data = tomllib.loads(pyproject.read_text("utf-8"))
    tool = data.get("tool", {}).get("alchemiq")
    if tool is None:
        raise MigrationConfigError("[tool.alchemiq] section not found in pyproject.toml")
    return AlchemiqConfig(
        root=pyproject.parent,
        models=tuple(tool.get("models", ())),
        migrations_dir=tool.get("migrations_dir", "migrations"),
        postgres=_parse_postgres(tool.get("postgres")),
        clickhouse=_parse_clickhouse(tool.get("clickhouse")),
    )


def import_models(config: AlchemiqConfig) -> None:
    """Import each module listed in ``config.models`` to trigger model registration.

    :param config: the resolved project configuration.
    :raises MigrationConfigError: if a listed module cannot be imported.
    """
    for module in config.models:
        try:
            import_module(module)
        except ImportError as e:
            raise MigrationConfigError(f"cannot import model module {module!r}: {e}") from e
