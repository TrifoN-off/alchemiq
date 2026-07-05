from __future__ import annotations

import pytest

from alchemiq.migrations import cli

pytestmark = pytest.mark.integration

_PYPROJECT = """
[tool.alchemiq]
models = ["tests.integration._migration_models"]

[tool.alchemiq.postgres]
host = "${MIGTEST_PGHOST}"
port = "${MIGTEST_PGPORT}"
database = "${MIGTEST_PGDB}"
username = "${MIGTEST_PGUSER}"
password = "${MIGTEST_PGPASS}"
"""


def test_cli_makemigrations_then_migrate(pg_container, tmp_path, monkeypatch) -> None:
    from sqlalchemy.engine import make_url

    u = make_url(pg_container.get_connection_url())
    monkeypatch.setenv("MIGTEST_PGHOST", str(u.host))
    monkeypatch.setenv("MIGTEST_PGPORT", str(u.port))
    monkeypatch.setenv("MIGTEST_PGDB", str(u.database))
    monkeypatch.setenv("MIGTEST_PGUSER", str(u.username))
    monkeypatch.setenv("MIGTEST_PGPASS", str(u.password))
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT, "utf-8")
    monkeypatch.chdir(tmp_path)

    assert cli.main(["makemigrations", "-m", "init", "--db", "postgres"]) == 0
    versions = list((tmp_path / "migrations" / "postgres" / "versions").glob("*.py"))
    assert versions
    assert cli.main(["migrate", "--db", "postgres"]) == 0
    try:
        pass  # post-migrate assertions go here
    finally:
        # Roll back to leave the shared pg_container DB in a clean state for other
        # migration tests that run in the same session (alembic_version cleared).
        cli.main(["rollback", "--db", "postgres"])
