"""End-to-end migration smoke on a file-based SQLite DB (subprocess CLI runs)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_PYPROJECT = """
[tool.alchemiq]
models = ["${SMIG_MODELS}"]

[tool.alchemiq.postgres]
dsn = "sqlite+aiosqlite:///./smig.db"
"""


def _cli(tmp_path: Path, models_module: str, *args: str) -> subprocess.CompletedProcess:
    env = os.environ | {
        "SMIG_MODELS": models_module,
        "PYTHONPATH": f"{REPO_ROOT / 'src'}{os.pathsep}{REPO_ROOT}",
    }
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from alchemiq.migrations import cli; sys.exit(cli.main(sys.argv[1:]))",
            *args,
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )


def test_makemigrations_migrate_alter_rollback(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT, "utf-8")
    v1, v2 = "tests.sqlite._mig_models_v1", "tests.sqlite._mig_models_v2"

    r = _cli(tmp_path, v1, "makemigrations", "-m", "init", "--db", "postgres")
    assert r.returncode == 0, r.stderr
    r = _cli(tmp_path, v1, "migrate", "--db", "postgres")
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "smig.db").is_file()

    r = _cli(tmp_path, v2, "makemigrations", "-m", "widen", "--db", "postgres")
    assert r.returncode == 0, r.stderr
    versions = list((tmp_path / "migrations" / "postgres" / "versions").glob("*.py"))
    assert len(versions) == 2
    # Alembic's default filename template embeds a random 12-hex rev id, so
    # sorting the glob results does not deterministically put "widen" last -
    # pick it by its "-m widen" slug instead.
    # render_as_batch proof: the ALTER revision uses a batch block.
    widen = next(p for p in versions if p.stem.endswith("_widen"))
    assert "batch_alter_table" in widen.read_text("utf-8")

    r = _cli(tmp_path, v2, "migrate", "--db", "postgres")
    assert r.returncode == 0, r.stderr
    r = _cli(tmp_path, v2, "rollback", "--db", "postgres")
    assert r.returncode == 0, r.stderr
