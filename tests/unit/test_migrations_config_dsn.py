"""[tool.alchemiq.postgres] dsn key: parsing, interpolation, normalization, conflicts."""

from __future__ import annotations

import pytest

from alchemiq.migrations.config import load_config
from alchemiq.migrations.errors import MigrationConfigError


def _write(tmp_path, postgres_block: str):
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.alchemiq]\nmodels = []\n\n[tool.alchemiq.postgres]\n{postgres_block}",
        "utf-8",
    )


def test_dsn_key_is_used_verbatim(tmp_path) -> None:
    _write(tmp_path, 'dsn = "sqlite+aiosqlite:///./dev.db"')
    cfg = load_config(tmp_path)
    assert cfg.postgres is not None
    assert cfg.postgres.url == "sqlite+aiosqlite:///./dev.db"


def test_driverless_dsn_is_normalized(tmp_path) -> None:
    _write(tmp_path, 'dsn = "sqlite:///./dev.db"')
    assert load_config(tmp_path).postgres.url == "sqlite+aiosqlite:///./dev.db"


def test_dsn_env_interpolation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MIG_DSN", "sqlite+aiosqlite:///./x.db")
    _write(tmp_path, 'dsn = "${MIG_DSN}"')
    assert load_config(tmp_path).postgres.url == "sqlite+aiosqlite:///./x.db"


def test_dsn_and_host_together_raise(tmp_path) -> None:
    _write(tmp_path, 'dsn = "sqlite:///x.db"\nhost = "h"')
    with pytest.raises(MigrationConfigError, match="either dsn or"):
        load_config(tmp_path)


def test_quartet_still_works(tmp_path) -> None:
    _write(tmp_path, 'host = "h"\ndatabase = "d"\nusername = "u"\npassword = "p"')
    url = load_config(tmp_path).postgres.url
    assert url.startswith("postgresql+asyncpg://u:p@h:5432/d")
