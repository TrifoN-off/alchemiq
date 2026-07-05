from pathlib import Path

import pytest

from alchemiq.migrations import cli
from alchemiq.migrations.config import AlchemiqConfig, PostgresSettings
from alchemiq.migrations.errors import MigrationConfigError

pytestmark = pytest.mark.unit


def _cfg(*, pg: bool = True, ch: bool = False) -> AlchemiqConfig:
    return AlchemiqConfig(
        root=Path("/tmp"),
        models=(),
        postgres=PostgresSettings("h", "d", "u", "p") if pg else None,
        clickhouse=None,  # ch handled separately in CH tests
    )


def test_parser_makemigrations_message_and_db() -> None:
    ns = cli.build_parser().parse_args(["makemigrations", "-m", "init", "--db", "postgres"])
    assert ns.command == "makemigrations"
    assert ns.message == "init"
    assert ns.db == "postgres"


def test_parser_defaults_db_none() -> None:
    ns = cli.build_parser().parse_args(["migrate"])
    assert ns.command == "migrate"
    assert ns.db is None


def test_main_dispatches_pg_migrate(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli, "load_config", lambda start=None: _cfg(pg=True))
    monkeypatch.setattr(cli, "import_models", lambda cfg: None)
    monkeypatch.setattr(cli, "_pg_migrate", lambda cfg: calls.append("pg.migrate"))
    rc = cli.main(["migrate", "--db", "postgres"])
    assert rc == 0
    assert calls == ["pg.migrate"]


def test_main_no_db_runs_only_configured(monkeypatch, capsys) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli, "load_config", lambda start=None: _cfg(pg=True, ch=False))
    monkeypatch.setattr(cli, "import_models", lambda cfg: None)
    monkeypatch.setattr(cli, "_pg_migrate", lambda cfg: calls.append("pg"))
    monkeypatch.setattr(cli, "_ch_migrate", lambda cfg: calls.append("ch"))
    rc = cli.main(["migrate"])  # no --db
    assert rc == 0
    assert calls == ["pg"]  # CH not configured => skipped
    err = capsys.readouterr().err
    assert "clickhouse" in err


def test_main_requested_db_not_configured_errors(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_config", lambda start=None: _cfg(pg=True, ch=False))
    monkeypatch.setattr(cli, "import_models", lambda cfg: None)
    rc = cli.main(["migrate", "--db", "clickhouse"])
    assert rc != 0
    assert "clickhouse" in capsys.readouterr().err.lower()


def test_missing_extra_message(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_config", lambda start=None: _cfg(pg=True))
    monkeypatch.setattr(cli, "import_models", lambda cfg: None)

    def boom(cfg):
        raise ImportError("No module named 'alembic'")

    monkeypatch.setattr(cli, "_pg_migrate", boom)
    rc = cli.main(["migrate", "--db", "postgres"])
    assert rc != 0
    assert "alchemiq[migrations]" in capsys.readouterr().err


def test_missing_asyncpg_message_names_postgres_extra(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_config", lambda start=None: _cfg(pg=True))
    monkeypatch.setattr(cli, "import_models", lambda cfg: None)

    def boom(cfg):
        raise ModuleNotFoundError("No module named 'asyncpg'", name="asyncpg")

    monkeypatch.setattr(cli, "_pg_migrate", boom)
    rc = cli.main(["migrate", "--db", "postgres"])
    assert rc != 0
    assert "alchemiq[postgres]" in capsys.readouterr().err


def test_missing_aiohttp_message_names_clickhouse_extra(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_config", lambda start=None: _ch_cfg())
    monkeypatch.setattr(cli, "import_models", lambda cfg: None)

    def boom(cfg):
        # clickhouse-connect re-raises a plain ImportError (no .name) for aiohttp.
        raise ImportError(
            "Async support requires aiohttp. Install with: pip install clickhouse-connect[async]"
        )

    monkeypatch.setattr(cli, "_ch_migrate", boom)
    rc = cli.main(["migrate", "--db", "clickhouse"])
    assert rc != 0
    assert "alchemiq[clickhouse]" in capsys.readouterr().err


def test_missing_unknown_module_falls_back_to_db_extras(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_config", lambda start=None: _cfg(pg=True))
    monkeypatch.setattr(cli, "import_models", lambda cfg: None)

    def boom(cfg):
        raise ModuleNotFoundError("No module named 'mystery'", name="mystery")

    monkeypatch.setattr(cli, "_pg_migrate", boom)
    rc = cli.main(["migrate", "--db", "postgres"])
    assert rc != 0
    assert "alchemiq[postgres,migrations]" in capsys.readouterr().err


def test_import_models_config_error_returns_2(monkeypatch, capsys) -> None:
    def raise_config_error(cfg: AlchemiqConfig) -> None:
        raise MigrationConfigError("boom")

    monkeypatch.setattr(cli, "load_config", lambda start=None: _cfg(pg=True))
    monkeypatch.setattr(cli, "import_models", raise_config_error)
    rc = cli.main(["migrate", "--db", "postgres"])
    assert rc == 2
    assert "boom" in capsys.readouterr().err


def test_main_load_config_unexpected_exception_returns_2(monkeypatch, capsys) -> None:
    def boom(start=None):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(cli, "load_config", boom)
    rc = cli.main(["migrate", "--db", "postgres"])
    assert rc == 2
    assert "unexpected" in capsys.readouterr().err


def test_main_no_db_configured_returns_2(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_config", lambda start=None: _cfg(pg=False, ch=False))
    monkeypatch.setattr(cli, "import_models", lambda cfg: None)
    rc = cli.main(["migrate"])
    assert rc == 2
    assert "no database configured" in capsys.readouterr().err.lower()


def test_main_pg_history_dispatch(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli, "load_config", lambda start=None: _cfg(pg=True))
    monkeypatch.setattr(cli, "import_models", lambda cfg: None)
    monkeypatch.setattr(cli, "_pg_history", lambda cfg: calls.append("pg.history"))
    rc = cli.main(["history", "--db", "postgres"])
    assert rc == 0
    assert calls == ["pg.history"]


def test_main_pg_showsql_dispatch(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli, "load_config", lambda start=None: _cfg(pg=True))
    monkeypatch.setattr(cli, "import_models", lambda cfg: None)
    monkeypatch.setattr(cli, "_pg_showsql", lambda cfg: calls.append("pg.showsql"))
    rc = cli.main(["showsql", "--db", "postgres"])
    assert rc == 0
    assert calls == ["pg.showsql"]


def test_main_pg_makemigrations_dispatch(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli, "load_config", lambda start=None: _cfg(pg=True))
    monkeypatch.setattr(cli, "import_models", lambda cfg: None)
    monkeypatch.setattr(cli, "_pg_makemigrations", lambda cfg, msg: calls.append(("pg.make", msg)))
    rc = cli.main(["makemigrations", "-m", "v1", "--db", "postgres"])
    assert rc == 0
    assert calls == [("pg.make", "v1")]


def _ch_cfg() -> AlchemiqConfig:
    from alchemiq.migrations.config import ClickHouseSettings

    return AlchemiqConfig(
        root=Path("/tmp"),
        models=(),
        postgres=None,
        clickhouse=ClickHouseSettings("h", "d", "u", "p"),
    )


def test_main_ch_makemigrations_dispatch(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli, "load_config", lambda start=None: _ch_cfg())
    monkeypatch.setattr(cli, "import_models", lambda cfg: None)
    monkeypatch.setattr(cli, "_ch_makemigrations", lambda cfg, msg: calls.append(("ch.make", msg)))
    rc = cli.main(["makemigrations", "-m", "v1", "--db", "clickhouse"])
    assert rc == 0
    assert calls == [("ch.make", "v1")]


def test_main_ch_migrate_dispatch(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli, "load_config", lambda start=None: _ch_cfg())
    monkeypatch.setattr(cli, "import_models", lambda cfg: None)
    monkeypatch.setattr(cli, "_ch_migrate", lambda cfg: calls.append("ch.migrate"))
    rc = cli.main(["migrate", "--db", "clickhouse"])
    assert rc == 0
    assert calls == ["ch.migrate"]


def test_main_ch_rollback_dispatch(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli, "load_config", lambda start=None: _ch_cfg())
    monkeypatch.setattr(cli, "import_models", lambda cfg: None)
    monkeypatch.setattr(cli, "_ch_rollback", lambda cfg: calls.append("ch.rollback"))
    rc = cli.main(["rollback", "--db", "clickhouse"])
    assert rc == 0
    assert calls == ["ch.rollback"]


def test_main_ch_history_dispatch(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli, "load_config", lambda start=None: _ch_cfg())
    monkeypatch.setattr(cli, "import_models", lambda cfg: None)
    monkeypatch.setattr(cli, "_ch_history", lambda cfg: calls.append("ch.history"))
    rc = cli.main(["history", "--db", "clickhouse"])
    assert rc == 0
    assert calls == ["ch.history"]


def test_main_ch_showsql_dispatch(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli, "load_config", lambda start=None: _ch_cfg())
    monkeypatch.setattr(cli, "import_models", lambda cfg: None)
    monkeypatch.setattr(cli, "_ch_showsql", lambda cfg: calls.append("ch.showsql"))
    rc = cli.main(["showsql", "--db", "clickhouse"])
    assert rc == 0
    assert calls == ["ch.showsql"]


def test_main_run_one_generic_exception_returns_1(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_config", lambda start=None: _cfg(pg=True))
    monkeypatch.setattr(cli, "import_models", lambda cfg: None)

    def boom(cfg: AlchemiqConfig) -> None:
        raise ValueError("something broke")

    monkeypatch.setattr(cli, "_pg_migrate", boom)
    rc = cli.main(["migrate", "--db", "postgres"])
    assert rc == 1
    assert "something broke" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Direct handler tests - cover the real function bodies (import + delegate).
# ---------------------------------------------------------------------------


def test_pg_history_function_delegates_to_backend(monkeypatch) -> None:
    from alchemiq.migrations.postgres import backend

    calls: list[str] = []
    monkeypatch.setattr(backend, "history", lambda cfg: calls.append("history"))
    cli._pg_history(_cfg(pg=True))
    assert calls == ["history"]


def test_pg_showsql_function_delegates_to_backend(monkeypatch) -> None:
    from alchemiq.migrations.postgres import backend

    calls: list[str] = []
    monkeypatch.setattr(backend, "showsql", lambda cfg: calls.append("showsql"))
    cli._pg_showsql(_cfg(pg=True))
    assert calls == ["showsql"]


def test_ch_makemigrations_function_runs_coroutine(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    from alchemiq.migrations.clickhouse import runner

    cfg = _ch_cfg()
    mock_fn = AsyncMock()
    monkeypatch.setattr(runner, "makemigrations", mock_fn)
    cli._ch_makemigrations(cfg, "v1")
    mock_fn.assert_called_once_with(cfg, "v1")


def test_ch_migrate_function_runs_coroutine(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    from alchemiq.migrations.clickhouse import runner

    cfg = _ch_cfg()
    mock_fn = AsyncMock()
    monkeypatch.setattr(runner, "migrate", mock_fn)
    cli._ch_migrate(cfg)
    mock_fn.assert_called_once_with(cfg)


def test_ch_rollback_function_runs_coroutine(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    from alchemiq.migrations.clickhouse import runner

    cfg = _ch_cfg()
    mock_fn = AsyncMock()
    monkeypatch.setattr(runner, "rollback", mock_fn)
    cli._ch_rollback(cfg)
    mock_fn.assert_called_once_with(cfg)


def test_ch_history_function_runs_coroutine(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    from alchemiq.migrations.clickhouse import runner

    cfg = _ch_cfg()
    mock_fn = AsyncMock()
    monkeypatch.setattr(runner, "history_command", mock_fn)
    cli._ch_history(cfg)
    mock_fn.assert_called_once_with(cfg)


def test_ch_showsql_function_runs_coroutine(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    from alchemiq.migrations.clickhouse import runner

    cfg = _ch_cfg()
    mock_fn = AsyncMock()
    monkeypatch.setattr(runner, "showsql", mock_fn)
    cli._ch_showsql(cfg)
    mock_fn.assert_called_once_with(cfg)


# ---------------------------------------------------------------------------
# CH dispatch must configure the process-global client from
# [tool.alchemiq.clickhouse] before the runner, and dispose it after.
# ---------------------------------------------------------------------------


def test_main_ch_configures_client_before_runner_and_disposes_after(monkeypatch) -> None:
    from alchemiq.clickhouse import connection
    from alchemiq.migrations.clickhouse import runner

    events: list[object] = []
    monkeypatch.setattr(cli, "load_config", lambda start=None: _ch_cfg())
    monkeypatch.setattr(cli, "import_models", lambda cfg: None)
    monkeypatch.setattr(connection, "is_clickhouse_configured", lambda: False)
    monkeypatch.setattr(
        connection, "configure_clickhouse", lambda **kw: events.append(("configure", kw))
    )

    async def fake_dispose() -> None:
        events.append("dispose")

    async def fake_migrate(cfg) -> None:
        events.append("run")

    monkeypatch.setattr(connection, "dispose_clickhouse", fake_dispose)
    monkeypatch.setattr(runner, "migrate", fake_migrate)

    rc = cli.main(["migrate", "--db", "clickhouse"])
    assert rc == 0
    expected_kwargs = _ch_cfg().clickhouse.client_kwargs
    assert events == [("configure", expected_kwargs), "run", "dispose"]


def test_main_ch_dispose_runs_even_when_runner_fails(monkeypatch, capsys) -> None:
    from alchemiq.clickhouse import connection
    from alchemiq.migrations.clickhouse import runner

    events: list[object] = []
    monkeypatch.setattr(cli, "load_config", lambda start=None: _ch_cfg())
    monkeypatch.setattr(cli, "import_models", lambda cfg: None)
    monkeypatch.setattr(connection, "is_clickhouse_configured", lambda: False)
    monkeypatch.setattr(connection, "configure_clickhouse", lambda **kw: events.append("configure"))

    async def fake_dispose() -> None:
        events.append("dispose")

    async def fake_migrate(cfg) -> None:
        raise ValueError("runner blew up")

    monkeypatch.setattr(connection, "dispose_clickhouse", fake_dispose)
    monkeypatch.setattr(runner, "migrate", fake_migrate)

    rc = cli.main(["migrate", "--db", "clickhouse"])
    assert rc == 1
    assert events == ["configure", "dispose"]
    assert "runner blew up" in capsys.readouterr().err


def test_main_ch_preserves_existing_in_process_configuration(monkeypatch) -> None:
    from alchemiq.clickhouse import connection
    from alchemiq.migrations.clickhouse import runner

    events: list[object] = []
    monkeypatch.setattr(cli, "load_config", lambda start=None: _ch_cfg())
    monkeypatch.setattr(cli, "import_models", lambda cfg: None)
    monkeypatch.setattr(connection, "is_clickhouse_configured", lambda: True)
    monkeypatch.setattr(connection, "configure_clickhouse", lambda **kw: events.append("configure"))

    async def fake_dispose() -> None:
        events.append("dispose")

    async def fake_migrate(cfg) -> None:
        events.append("run")

    monkeypatch.setattr(connection, "dispose_clickhouse", fake_dispose)
    monkeypatch.setattr(runner, "migrate", fake_migrate)

    rc = cli.main(["migrate", "--db", "clickhouse"])
    assert rc == 0
    assert events == ["run"]  # existing config is neither clobbered nor disposed
