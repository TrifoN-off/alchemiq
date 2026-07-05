from __future__ import annotations

from pathlib import Path

import pytest

from alchemiq.scaffold.options import build_options
from alchemiq.scaffold.plan import extras_for, included, plan, process_text

pytestmark = pytest.mark.unit


def _opts(**kw):
    base = dict(root="notes", monorepo=None, without=None, force=False)
    base.update(kw)
    return build_options(**base)


def test_included_keeps_neutral_files() -> None:
    o = _opts()
    assert included("src/notes/config.py", o, nested=False) is True
    assert included("src/notes/domain/models.py", o, nested=False) is True


def test_included_drops_fastapi_files_when_without() -> None:
    o = _opts(without="fastapi")
    assert included("src/notes/app.py", o, nested=False) is False
    assert included("src/notes/adapters/http/__init__.py", o, nested=False) is False
    assert included("src/notes/broker.py", o, nested=False) is True


def test_included_drops_faststream_files_when_without() -> None:
    o = _opts(without="faststream")
    assert included("src/notes/broker.py", o, nested=False) is False
    assert included("src/notes/adapters/messaging/__init__.py", o, nested=False) is False


def test_included_drops_docker_files_when_without() -> None:
    o = _opts(without="docker")
    assert included("docker-compose.yml", o, nested=False) is False
    assert included("Dockerfile", o, nested=False) is False


def test_included_nested_drops_compose_keeps_dockerfile() -> None:
    o = _opts()
    assert included("docker-compose.yml", o, nested=True) is False
    assert included("Dockerfile", o, nested=True) is True


def test_process_text_substitutes_placeholders() -> None:
    out = process_text(
        "package = __ALCHEMIQ_MODULE__\ndist = __ALCHEMIQ_DIST__\n",
        lambda t: True,
        {"__ALCHEMIQ_MODULE__": "users_service", "__ALCHEMIQ_DIST__": "users-service"},
    )
    assert "package = users_service" in out
    assert "dist = users-service" in out


def test_process_text_if_marker_keeps_and_strips() -> None:
    text = "always = 1\nfast = 1  # alchemiq:if fastapi\nmsg = 1  # alchemiq:if faststream\n"
    out = process_text(text, lambda t: t == "fastapi", {})
    assert "always = 1" in out
    assert "fast = 1" in out
    assert "# alchemiq:if" not in out  # marker stripped from kept line
    assert "msg = 1" not in out  # faststream disabled -> dropped


def test_process_text_ifnot_marker() -> None:
    text = "x = 1  # alchemiq:ifnot redis\n"
    assert "x = 1" in process_text(text, lambda t: False, {})  # redis off -> keep
    assert "x = 1" not in process_text(text, lambda t: True, {})  # redis on -> drop


def test_process_text_block_marker() -> None:
    text = "head\n# alchemiq:block clickhouse\nch1\nch2\n# alchemiq:endblock\ntail\n"
    on = process_text(text, lambda t: True, {})
    assert "ch1" in on and "ch2" in on and "head" in on and "tail" in on
    assert "alchemiq:block" not in on
    off = process_text(text, lambda t: False, {})
    assert "ch1" not in off and "ch2" not in off
    assert "head" in off and "tail" in off


def test_process_text_preserves_trailing_newline() -> None:
    assert process_text("a\n", lambda t: True, {}).endswith("\n")
    assert not process_text("a", lambda t: True, {}).endswith("\n")


def test_extras_full() -> None:
    o = _opts()
    assert extras_for(o.services[0], o) == "fastapi,faststream,redis,postgres,migrations"


def test_extras_clickhouse_service() -> None:
    o = build_options(root="ev:clickhouse", monorepo=None, without=None, force=False)
    extras = extras_for(o.services[0], o)
    assert "clickhouse" in extras and "fastapi" in extras
    assert "postgres" not in extras  # CH backend does not pull asyncpg


def test_extras_drops_without() -> None:
    o = _opts(without="faststream,redis")
    extras = extras_for(o.services[0], o)
    assert "faststream" not in extras
    assert "redis" not in extras
    assert "fastapi" in extras and "migrations" in extras
    assert "postgres" in extras  # backend driver extra always present


def _fixture_templates(tmp_path) -> Path:
    root = tmp_path / "templates"
    single = root / "single" / "src" / "__ALCHEMIQ_MODULE__"
    single.mkdir(parents=True)
    (root / "single" / "pyproject.toml.tmpl").write_text(
        'name = "__ALCHEMIQ_DIST__"\ndeps = "alchemiq[__ALCHEMIQ_EXTRAS__]"\n', "utf-8"
    )
    (single / "config.py.tmpl").write_text("MOD = '__ALCHEMIQ_MODULE__'\n", "utf-8")
    (root / "single" / "broker.py.tmpl").write_text("broker = 1\n", "utf-8")
    mono = root / "monorepo_root"
    (mono / "packages" / "shared").mkdir(parents=True)
    (mono / "pyproject.toml.tmpl").write_text('root = "__ALCHEMIQ_ROOT__"\n', "utf-8")
    return root


def test_plan_single(tmp_path) -> None:
    o = build_options(root="notes", monorepo=None, without=None, force=False)
    files = dict(plan(o, templates_root=_fixture_templates(tmp_path)))
    assert (
        files["pyproject.toml"]
        == 'name = "notes"\ndeps = "alchemiq[fastapi,faststream,redis,postgres,migrations]"\n'
    )
    assert files["src/notes/config.py"] == "MOD = 'notes'\n"
    assert "broker.py" in files  # faststream on by default


def test_plan_single_without_faststream_drops_broker(tmp_path) -> None:
    o = build_options(root="notes", monorepo=None, without="faststream", force=False)
    files = dict(plan(o, templates_root=_fixture_templates(tmp_path)))
    assert "broker.py" not in files


def test_plan_monorepo_renders_root_and_each_service(tmp_path) -> None:
    o = build_options(root="plat", monorepo=["a", "b"], without=None, force=False)
    files = dict(plan(o, templates_root=_fixture_templates(tmp_path)))
    assert files["pyproject.toml"] == 'root = "plat"\n'
    assert "services/a/src/a/config.py" in files
    assert "services/b/src/b/config.py" in files
    assert "services/a/pyproject.toml" in files


def test_plan_clickhouse_service_uses_ch_model(tmp_path) -> None:
    # Extend the fixture from _fixture_templates with both model variants.
    root = _fixture_templates(tmp_path)
    dom = root / "single" / "src" / "__ALCHEMIQ_MODULE__" / "domain"
    dom.mkdir(parents=True, exist_ok=True)
    (dom / "models.py.tmpl").write_text("PG = 1\n", "utf-8")
    (dom / "models_clickhouse.py.tmpl").write_text("CH = 1\n", "utf-8")
    o_pg = build_options(root="a", monorepo=None, without=None, force=False)
    o_ch = build_options(root="a:clickhouse", monorepo=None, without=None, force=False)
    pg = dict(plan(o_pg, templates_root=root))
    ch = dict(plan(o_ch, templates_root=root))
    assert pg["src/a/domain/models.py"] == "PG = 1\n"
    assert "src/a/domain/models_clickhouse.py" not in pg
    assert ch["src/a/domain/models.py"] == "CH = 1\n"
    assert "src/a/domain/models_clickhouse.py" not in ch


# --- Real-template plans (default TEMPLATES_ROOT) ---


def test_plan_clickhouse_without_fastapi_faststream_drops_app_and_broker(tmp_path) -> None:
    # The CH variants (app_clickhouse.py, broker_clickhouse.py) must be judged
    # by their post-rename names, so --without drops them too.
    o = build_options(
        root="ev:clickhouse", monorepo=None, without="fastapi,faststream", force=False
    )
    files = dict(plan(o))
    from alchemiq.scaffold.render import render

    render(files.items(), tmp_path / "ev", force=False)
    names = set(files)
    assert not any(p.endswith("app.py") for p in names)
    assert not any(p.endswith("broker.py") for p in names)
    assert not any("_clickhouse" in p for p in names)
    assert not (tmp_path / "ev" / "src" / "ev" / "app.py").exists()
    assert not (tmp_path / "ev" / "src" / "ev" / "broker.py").exists()
    pyproject = files["pyproject.toml"]
    assert "fastapi" not in pyproject
    assert "faststream" not in pyproject
    assert "alchemiq[redis,clickhouse,migrations]" in pyproject


def test_plan_clickhouse_service_gets_ch_tests() -> None:
    o = build_options(root="ev:clickhouse", monorepo=None, without=None, force=False)
    files = dict(plan(o))
    assert "Event" in files["tests/test_models.py"]
    assert "Note" not in files["tests/test_models.py"]
    assert "configure_clickhouse" in files["tests/conftest.py"]
    assert "TEST_DATABASE_DSN" not in files["tests/conftest.py"]
    assert not any("_clickhouse" in p for p in files)


def test_plan_postgres_service_gets_pg_tests() -> None:
    o = build_options(root="notes", monorepo=None, without=None, force=False)
    files = dict(plan(o))
    assert "Note" in files["tests/test_models.py"]
    assert "TEST_DATABASE_DSN" in files["tests/conftest.py"]
    assert not any("_clickhouse" in p for p in files)


def test_plan_emits_dockerignore_gated_on_docker() -> None:
    o = build_options(root="notes", monorepo=None, without=None, force=False)
    assert ".dockerignore" in dict(plan(o))
    o2 = build_options(root="notes", monorepo=None, without="docker", force=False)
    files = dict(plan(o2))
    assert ".dockerignore" not in files
    assert "Dockerfile" not in files


def test_plan_monorepo_postgres_init_script() -> None:
    o = build_options(
        root="plat", monorepo=["users-svc", "analytics:clickhouse"], without=None, force=False
    )
    files = dict(plan(o))
    script = files["docker/postgres-init.sh"]
    assert "users_svc" in script  # one DB per Postgres-backed service
    assert "analytics" not in script  # CH services get no Postgres DB
    assert "users_svc" in files["services/users-svc/pyproject.toml"]
    # Compose mounts the script; per-service pyproject pins its own database.
    assert "postgres-init.sh" in files["docker-compose.yml"]
    assert 'database = "users_svc"' in files["services/users-svc/pyproject.toml"]


def test_plan_all_clickhouse_monorepo_has_no_postgres_bits() -> None:
    o = build_options(root="plat", monorepo=["a:clickhouse"], without=None, force=False)
    files = dict(plan(o))
    assert "docker/postgres-init.sh" not in files
    compose = files["docker-compose.yml"]
    assert "postgres:" not in compose
    assert "clickhouse:" in compose


def test_plan_no_placeholder_leaks_in_rendered_output() -> None:
    for opts in (
        build_options(root="notes", monorepo=None, without=None, force=False),
        build_options(root="ev:clickhouse", monorepo=None, without=None, force=False),
        build_options(root="plat", monorepo=["a", "b:clickhouse"], without=None, force=False),
    ):
        for path, text in plan(opts):
            assert "__ALCHEMIQ_" not in path
            assert "__ALCHEMIQ_" not in text, path
            assert "alchemiq:block" not in text, path
            assert "alchemiq:endblock" not in text, path
            assert "alchemiq:if" not in text, path


def test_plan_monorepo_service_has_no_own_env_or_compose() -> None:
    opts = build_options(
        root="plat", monorepo=["api", "events:clickhouse"], without=None, force=False
    )
    paths = {p for p, _ in plan(opts)}
    assert ".env.example" in paths  # the workspace root owns the env file
    assert not any(p.startswith("services/") and p.endswith(".env.example") for p in paths)
    assert not any(p.startswith("services/") and p.endswith("docker-compose.yml") for p in paths)
