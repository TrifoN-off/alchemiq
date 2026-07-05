from __future__ import annotations

import compileall
import subprocess
import sys
import tomllib

import pytest

from alchemiq.scaffold.options import build_options
from alchemiq.scaffold.plan import plan
from alchemiq.scaffold.render import render

pytestmark = pytest.mark.integration


def _opts():
    return build_options(
        root="myplatform",
        monorepo=["users-service", "analytics:clickhouse"],
        without=None,
        force=False,
    )


def test_monorepo_structure(tmp_path) -> None:
    dest = tmp_path / "myplatform"
    render(plan(_opts()), dest, force=False)
    for rel in [
        "pyproject.toml",
        "docker-compose.yml",
        "packages/shared/pyproject.toml",
        "packages/shared/src/shared/__init__.py",
        "services/users-service/pyproject.toml",
        "services/users-service/src/users_service/app.py",
        "services/users-service/src/users_service/domain/models.py",
        "services/analytics/src/analytics/domain/models.py",
    ]:
        assert (dest / rel).is_file(), f"missing {rel}"
    # services have no own compose (root owns it); root is a uv workspace
    assert not (dest / "services/users-service/docker-compose.yml").exists()
    root_pp = tomllib.loads((dest / "pyproject.toml").read_text())
    assert root_pp["tool"]["uv"]["workspace"]["members"] == ["services/*", "packages/*"]
    # per-service backend wiring
    ch_models = (dest / "services/analytics/src/analytics/domain/models.py").read_text()
    assert "ClickHouseModel" in ch_models
    pg_pp = tomllib.loads((dest / "services/users-service/pyproject.toml").read_text())
    assert "postgres" in pg_pp["tool"]["alchemiq"]
    # no leftovers
    blob = "\n".join(p.read_text() for p in dest.rglob("*") if p.is_file())
    assert "__ALCHEMIQ_" not in blob and "alchemiq:" not in blob


def test_monorepo_compiles(tmp_path) -> None:
    dest = tmp_path / "myplatform"
    render(plan(_opts()), dest, force=False)
    assert compileall.compile_dir(str(dest), quiet=1)


def test_monorepo_clickhouse_dropped_drops_container(tmp_path) -> None:
    opts = build_options(root="plat", monorepo=["a", "b"], without="clickhouse", force=False)
    dest = tmp_path / "plat"
    render(plan(opts), dest, force=False)
    assert "clickhouse" not in (dest / "docker-compose.yml").read_text()


def test_monorepo_ruff_clean(tmp_path) -> None:
    dest = tmp_path / "myplatform"
    render(plan(_opts()), dest, force=False)
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", str(dest)], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
