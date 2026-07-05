from __future__ import annotations

from pathlib import Path

import pytest

from alchemiq.migrations.config import (
    AlchemiqConfig,
    ClickHouseSettings,
    PostgresSettings,
    find_pyproject,
    import_models,
    load_config,
)
from alchemiq.migrations.errors import MigrationConfigError

pytestmark = pytest.mark.unit


def test_postgres_url_encodes_password() -> None:
    s = PostgresSettings(host="h", database="db", username="u", password="p@ss/w", port=6000)
    assert s.url == "postgresql+asyncpg://u:p%40ss%2Fw@h:6000/db"


def test_clickhouse_client_kwargs_passthrough() -> None:
    s = ClickHouseSettings(host="h", database="db", username="u", password="x", port=8123)
    assert s.client_kwargs == {
        "host": "h",
        "port": 8123,
        "username": "u",
        "password": "x",
        "database": "db",
        "secure": False,
    }


_PYPROJECT = """
[tool.alchemiq]
models = ["myapp.models"]

[tool.alchemiq.postgres]
host = "${MIGTEST_DB_HOST}"
port = "${MIGTEST_DB_PORT}"
database = "app"
username = "u"
password = "secret"

[tool.alchemiq.clickhouse]
host = "ch"
database = "analytics"
username = "u"
password = "x"
secure = true
"""


def _write_project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT, "utf-8")
    return tmp_path


def test_load_config_interpolates_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MIGTEST_DB_HOST", "dbhost")
    monkeypatch.setenv("MIGTEST_DB_PORT", "6432")
    cfg = load_config(_write_project(tmp_path))
    assert cfg.models == ("myapp.models",)
    assert cfg.migrations_dir == "migrations"
    assert cfg.postgres is not None
    assert cfg.postgres.host == "dbhost"
    assert cfg.postgres.port == 6432  # coerced to int from env str
    assert cfg.clickhouse is not None
    assert cfg.clickhouse.secure is True


def test_missing_env_var_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MIGTEST_DB_HOST", raising=False)
    monkeypatch.setenv("MIGTEST_DB_PORT", "6432")
    with pytest.raises(MigrationConfigError, match="MIGTEST_DB_HOST"):
        load_config(_write_project(tmp_path))


def test_missing_subtable_means_not_configured(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.alchemiq]\nmodels = []\n\n[tool.alchemiq.postgres]\n"
        'host="h"\ndatabase="d"\nusername="u"\npassword="p"\n',
        "utf-8",
    )
    cfg = load_config(tmp_path)
    assert cfg.postgres is not None
    assert cfg.clickhouse is None  # no [tool.alchemiq.clickhouse] => None


def test_no_tool_section_raises(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", "utf-8")
    with pytest.raises(MigrationConfigError, match=r"\[tool.alchemiq\]"):
        load_config(tmp_path)


def test_find_pyproject_walks_up(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.alchemiq]\n", "utf-8")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert find_pyproject(nested) == tmp_path / "pyproject.toml"


def test_postgres_missing_required_field_raises(tmp_path: Path) -> None:
    # [tool.alchemiq.postgres] present but missing 'host' -> MigrationConfigError
    (tmp_path / "pyproject.toml").write_text(
        '[tool.alchemiq]\n\n[tool.alchemiq.postgres]\ndatabase="d"\nusername="u"\npassword="p"\n',
        "utf-8",
    )
    with pytest.raises(MigrationConfigError, match="host"):
        load_config(tmp_path)


def test_import_models_wraps_import_error() -> None:
    cfg = AlchemiqConfig(root=Path("."), models=("no.such.module",))
    with pytest.raises(MigrationConfigError, match="no.such.module"):
        import_models(cfg)


def test_find_pyproject_raises_when_not_found(tmp_path: Path) -> None:
    # Start from a fresh dir with no pyproject.toml in any parent.
    # Use an isolated sub-tree to avoid picking up the real project pyproject.toml.
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    with pytest.raises(MigrationConfigError, match="pyproject.toml not found"):
        find_pyproject(isolated)


def test_parse_postgres_none_returns_none(tmp_path: Path) -> None:
    """When [tool.alchemiq.postgres] is absent, config.postgres is None."""
    (tmp_path / "pyproject.toml").write_text("[tool.alchemiq]\nmodels = []\n", "utf-8")
    cfg = load_config(tmp_path)
    assert cfg.postgres is None


def test_clickhouse_missing_required_field_raises(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.alchemiq]\n\n[tool.alchemiq.clickhouse]\nhost="h"\nusername="u"\npassword="p"\n',
        "utf-8",
    )
    with pytest.raises(MigrationConfigError, match="database"):
        load_config(tmp_path)
