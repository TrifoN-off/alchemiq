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


def test_clickhouse_service(tmp_path) -> None:
    opts = build_options(root="events:clickhouse", monorepo=None, without=None, force=False)
    dest = tmp_path / "events"
    render(plan(opts), dest, force=False)
    models = (dest / "src/events/domain/models.py").read_text()
    assert "ClickHouseModel" in models
    assert not (dest / "src/events/domain/models_clickhouse.py").exists()
    data = tomllib.loads((dest / "pyproject.toml").read_text())
    assert "clickhouse" in data["project"]["dependencies"][0]
    assert "clickhouse" in data["tool"]["alchemiq"]
    assert "postgres" not in data["tool"]["alchemiq"]
    assert compileall.compile_dir(str(dest), quiet=1)
    code = "import sys; sys.path.insert(0, r'%s'); import events.domain.models" % (dest / "src")
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_clickhouse_no_variant_files_in_output(tmp_path) -> None:
    """Rendered tree must not contain app_clickhouse.py or broker_clickhouse.py."""
    opts = build_options(root="events:clickhouse", monorepo=None, without=None, force=False)
    dest = tmp_path / "events"
    render(plan(opts), dest, force=False)
    assert not (dest / "src/events/app_clickhouse.py").exists()
    assert not (dest / "src/events/broker_clickhouse.py").exists()
    # The plain names must exist (renamed from _clickhouse variants)
    assert (dest / "src/events/app.py").exists()
    assert (dest / "src/events/broker.py").exists()


def test_clickhouse_ruff_clean(tmp_path) -> None:
    opts = build_options(root="events:clickhouse", monorepo=None, without=None, force=False)
    dest = tmp_path / "events"
    render(plan(opts), dest, force=False)
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", str(dest)], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_clickhouse_app_and_broker_import(tmp_path) -> None:
    """I1 regression: ClickHouse app/broker must boot without AttributeError."""
    opts = build_options(root="events:clickhouse", monorepo=None, without=None, force=False)
    dest = tmp_path / "events"
    render(plan(opts), dest, force=False)
    env = {
        **os.environ,
        "CLICKHOUSE_HOST": "h",
        "CLICKHOUSE_PORT": "8123",
        "CLICKHOUSE_DB": "d",
        "CLICKHOUSE_USER": "u",
        "CLICKHOUSE_PASSWORD": "p",
    }
    for mod in ("events.app", "events.broker"):
        src_path = str(dest / "src")
        code = f"import sys; sys.path.insert(0, r'{src_path}'); import {mod}"
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
        assert proc.returncode == 0, f"{mod}: {proc.stderr}"
