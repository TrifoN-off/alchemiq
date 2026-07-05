from __future__ import annotations

import pytest

from alchemiq import cli

pytestmark = pytest.mark.unit


def test_init_routes_to_scaffold(monkeypatch) -> None:
    seen: dict[str, object] = {}
    import alchemiq.scaffold.cli as scaffold_cli

    monkeypatch.setattr(scaffold_cli, "main", lambda argv: seen.setdefault("argv", argv) and 0)

    def fail_migrations(argv=None):  # must not be called
        raise AssertionError("migrations CLI should not run for init")

    import alchemiq.migrations.cli as migrations_cli

    monkeypatch.setattr(migrations_cli, "main", fail_migrations)
    rc = cli.main(["init", "notes", "--force"])
    assert rc == 0
    assert seen["argv"] == ["notes", "--force"]


def test_non_init_delegates_to_migrations(monkeypatch) -> None:
    seen: dict[str, object] = {}
    import alchemiq.migrations.cli as migrations_cli

    monkeypatch.setattr(
        migrations_cli, "main", lambda argv=None: seen.setdefault("argv", argv) and 0
    )
    rc = cli.main(["migrate", "--db", "postgres"])
    assert rc == 0
    assert seen["argv"] == ["migrate", "--db", "postgres"]


def test_empty_argv_delegates_to_migrations(monkeypatch) -> None:
    seen: dict[str, object] = {}
    import alchemiq.migrations.cli as migrations_cli

    monkeypatch.setattr(
        migrations_cli, "main", lambda argv=None: seen.setdefault("argv", argv) or 7
    )
    rc = cli.main([])
    assert rc == 7
    assert seen["argv"] == []
