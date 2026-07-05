from __future__ import annotations

import pytest

from alchemiq.scaffold.options import (
    BACKENDS,
    ScaffoldError,
    build_options,
    parse_service,
)

pytestmark = pytest.mark.unit


def test_parse_service_default_backend() -> None:
    svc = parse_service("users-service")
    assert svc.name == "users-service"
    assert svc.backend == "postgres"
    assert svc.module == "users_service"
    assert svc.dist == "users-service"


def test_parse_service_clickhouse_suffix() -> None:
    assert parse_service("analytics:clickhouse").backend == "clickhouse"


def test_parse_service_rejects_unknown_backend() -> None:
    with pytest.raises(ScaffoldError):
        parse_service("svc:mysql")


@pytest.mark.parametrize("bad", ["", "1svc", "Svc", "a--b", "svc.x", "svc/x", "-svc"])
def test_parse_service_rejects_bad_name(bad: str) -> None:
    with pytest.raises(ScaffoldError):
        parse_service(bad)


def test_single_options() -> None:
    opts = build_options(root="notes", monorepo=None, without=None, force=False)
    assert opts.monorepo is False
    assert opts.root_name == "notes"
    assert [s.name for s in opts.services] == ["notes"]
    assert opts.services[0].backend == "postgres"


def test_single_clickhouse() -> None:
    opts = build_options(root="events:clickhouse", monorepo=None, without=None, force=False)
    assert opts.root_name == "events"
    assert opts.services[0].backend == "clickhouse"


def test_monorepo_options() -> None:
    opts = build_options(
        root="myplatform",
        monorepo=["users-service", "analytics:clickhouse"],
        without=None,
        force=False,
    )
    assert opts.monorepo is True
    assert opts.root_name == "myplatform"
    assert [(s.name, s.backend) for s in opts.services] == [
        ("users-service", "postgres"),
        ("analytics", "clickhouse"),
    ]


def test_monorepo_requires_services() -> None:
    with pytest.raises(ScaffoldError):
        build_options(root="x", monorepo=[], without=None, force=False)


def test_monorepo_rejects_duplicate_service_names() -> None:
    with pytest.raises(ScaffoldError):
        build_options(root="x", monorepo=["a", "a"], without=None, force=False)


def test_without_parsing_and_unknown_token() -> None:
    opts = build_options(root="n", monorepo=None, without="faststream, docker", force=False)
    assert opts.without == frozenset({"faststream", "docker"})
    assert opts.feature("faststream") is False
    assert opts.feature("fastapi") is True
    with pytest.raises(ScaffoldError):
        build_options(root="n", monorepo=None, without="bogus", force=False)


def test_without_clickhouse_conflicts_with_ch_service() -> None:
    with pytest.raises(ScaffoldError):
        build_options(root="p", monorepo=["a:clickhouse"], without="clickhouse", force=False)


def test_infra_single_postgres_defaults() -> None:
    opts = build_options(root="n", monorepo=None, without=None, force=False)
    assert opts.infra("postgres") is True
    assert opts.infra("clickhouse") is False  # single PG service: no CH container
    assert opts.infra("redis") is True
    assert opts.infra("rabbitmq") is True


def test_infra_monorepo_clickhouse_follows_service_backends() -> None:
    all_pg = build_options(root="p", monorepo=["a", "b"], without=None, force=False)
    assert all_pg.infra("clickhouse") is False  # no CH service -> no CH container
    mixed = build_options(root="p", monorepo=["a", "b:clickhouse"], without=None, force=False)
    assert mixed.infra("clickhouse") is True
    all_ch = build_options(root="p", monorepo=["a:clickhouse"], without=None, force=False)
    assert all_ch.infra("postgres") is False  # and vice versa


def test_infra_respects_without() -> None:
    opts = build_options(root="n", monorepo=None, without="redis,faststream", force=False)
    assert opts.infra("redis") is False
    assert opts.infra("rabbitmq") is False  # rabbitmq tracks faststream


def test_service_enabled_scopes_backend_per_service() -> None:
    opts = build_options(root="p", monorepo=["a", "b:clickhouse"], without=None, force=False)
    a, b = opts.services
    assert opts.service_enabled(a, "postgres") is True
    assert opts.service_enabled(a, "clickhouse") is False
    assert opts.service_enabled(b, "postgres") is False
    assert opts.service_enabled(b, "clickhouse") is True
    assert opts.service_enabled(a, "redis") is True


def test_monorepo_token_reflects_layout() -> None:
    single = build_options(root="n", monorepo=None, without=None, force=False)
    assert single.service_enabled(single.services[0], "monorepo") is False
    assert single.root_enabled("monorepo") is False
    mono = build_options(root="p", monorepo=["a"], without=None, force=False)
    assert mono.service_enabled(mono.services[0], "monorepo") is True
    assert mono.root_enabled("monorepo") is True


def test_backends_constant() -> None:
    assert BACKENDS == frozenset({"postgres", "clickhouse"})
