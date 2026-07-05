from __future__ import annotations

import compileall
import os
import subprocess
import sys
import tomllib

import pytest

from alchemiq.scaffold.options import build_options
from alchemiq.scaffold.plan import plan
from alchemiq.scaffold.render import render

pytestmark = pytest.mark.integration


def _render(opts, dest):
    render(plan(opts), dest, force=False)


def test_single_pg_structure(tmp_path) -> None:
    opts = build_options(root="notes", monorepo=None, without=None, force=False)
    dest = tmp_path / "notes"
    _render(opts, dest)
    for rel in [
        "pyproject.toml",
        "docker-compose.yml",
        "Dockerfile",
        ".env.example",
        ".gitignore",
        "README.md",
        "src/notes/__init__.py",
        "src/notes/config.py",
        "src/notes/app.py",
        "src/notes/broker.py",
        "src/notes/domain/__init__.py",
        "src/notes/domain/models.py",
        "src/notes/repositories/__init__.py",
        "src/notes/services/__init__.py",
        "src/notes/use_cases/__init__.py",
        "src/notes/adapters/__init__.py",
        "src/notes/adapters/http/__init__.py",
        "src/notes/adapters/messaging/__init__.py",
        "tests/conftest.py",
        "tests/test_models.py",
    ]:
        assert (dest / rel).is_file(), f"missing {rel}"
    # no leftover markers/placeholders/suffixes
    blob = "\n".join(p.read_text() for p in dest.rglob("*") if p.is_file())
    assert "__ALCHEMIQ_" not in blob
    assert "alchemiq:if" not in blob and "alchemiq:block" not in blob
    assert not list(dest.rglob("*.tmpl"))


def test_single_generated_python_compiles(tmp_path) -> None:
    opts = build_options(root="notes", monorepo=None, without=None, force=False)
    dest = tmp_path / "notes"
    _render(opts, dest)
    assert compileall.compile_dir(str(dest), quiet=1)


def test_single_base_model_imports_under_alchemiq(tmp_path) -> None:
    opts = build_options(root="notes", monorepo=None, without=None, force=False)
    dest = tmp_path / "notes"
    _render(opts, dest)
    code = "import sys; sys.path.insert(0, r'%s'); import notes.domain.models" % (dest / "src")
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_single_pyproject_and_alchemiq_config(tmp_path, monkeypatch) -> None:
    opts = build_options(root="notes", monorepo=None, without=None, force=False)
    dest = tmp_path / "notes"
    _render(opts, dest)
    data = tomllib.loads((dest / "pyproject.toml").read_text())
    assert data["project"]["dependencies"] == [
        "alchemiq[fastapi,faststream,redis,postgres,migrations]>=0.1",
        "uvicorn>=0.30",
        "faststream[rabbit,cli]>=0.5",
    ]
    assert data["project"]["requires-python"] == ">=3.12"
    assert data["tool"]["alchemiq"]["models"] == ["notes.domain.models"]
    assert "postgres" in data["tool"]["alchemiq"]
    assert "clickhouse" not in data["tool"]["alchemiq"]
    # [tool.alchemiq] parses via the real loader once env vars are present
    from alchemiq.migrations.config import load_config

    for k, v in {
        "POSTGRES_HOST": "h",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "d",
        "POSTGRES_USER": "u",
        "POSTGRES_PASSWORD": "p",
    }.items():
        monkeypatch.setenv(k, v)
    cfg = load_config(start=dest)
    assert cfg.postgres is not None and cfg.postgres.database == "d"


def test_single_without_faststream_drops_messaging(tmp_path) -> None:
    opts = build_options(root="notes", monorepo=None, without="faststream", force=False)
    dest = tmp_path / "notes"
    _render(opts, dest)
    assert not (dest / "src/notes/broker.py").exists()
    assert not (dest / "src/notes/adapters/messaging/__init__.py").exists()
    assert (dest / "src/notes/app.py").exists()
    data = tomllib.loads((dest / "pyproject.toml").read_text())
    assert "faststream" not in data["project"]["dependencies"][0]
    assert "rabbitmq" not in (dest / "docker-compose.yml").read_text()


def test_single_ruff_clean(tmp_path) -> None:
    opts = build_options(root="notes", monorepo=None, without=None, force=False)
    dest = tmp_path / "notes"
    _render(opts, dest)
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", str(dest)], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_single_app_and_broker_import(tmp_path) -> None:
    opts = build_options(root="notes", monorepo=None, without=None, force=False)
    dest = tmp_path / "notes"
    _render(opts, dest)
    env = {
        **os.environ,
        "POSTGRES_HOST": "h",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "d",
        "POSTGRES_USER": "u",
        "POSTGRES_PASSWORD": "p",
    }
    for mod in ("notes.app", "notes.broker"):
        src_path = str(dest / "src")
        code = f"import sys; sys.path.insert(0, r'{src_path}'); import {mod}"
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
        assert proc.returncode == 0, f"{mod}: {proc.stderr}"
