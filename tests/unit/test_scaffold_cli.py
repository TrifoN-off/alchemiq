from __future__ import annotations

import pytest

from alchemiq.scaffold import cli

pytestmark = pytest.mark.unit


def test_parser_single() -> None:
    ns = cli.build_parser().parse_args(["notes"])
    assert ns.root == "notes"
    assert ns.monorepo is None
    assert ns.force is False


def test_parser_monorepo() -> None:
    ns = cli.build_parser().parse_args(["plat", "--monorepo", "a", "b:clickhouse", "--force"])
    assert ns.root == "plat"
    assert ns.monorepo == ["a", "b:clickhouse"]
    assert ns.force is True


def test_main_success_invokes_plan_and_render(monkeypatch, tmp_path, capsys) -> None:
    calls: dict[str, object] = {}
    monkeypatch.setattr(cli, "plan", lambda opts: (("README.md", "x"),))
    monkeypatch.setattr(
        cli, "render", lambda files, dest, force: calls.update(dest=dest, force=force)
    )
    monkeypatch.chdir(tmp_path)
    rc = cli.main(["notes"])
    assert rc == 0
    assert calls["dest"] == tmp_path / "notes"
    assert "cd notes" in capsys.readouterr().out


def test_main_bad_name_returns_2(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    rc = cli.main(["Bad-NAME"])
    assert rc == 2
    assert "invalid name" in capsys.readouterr().err.lower()


def test_main_existing_dir_returns_1(monkeypatch, tmp_path, capsys) -> None:
    def boom(files, dest, force):
        raise FileExistsError("exists")

    monkeypatch.setattr(cli, "plan", lambda opts: (("README.md", "x"),))
    monkeypatch.setattr(cli, "render", boom)
    monkeypatch.chdir(tmp_path)
    rc = cli.main(["notes"])
    assert rc == 1
    assert "exists" in capsys.readouterr().err


def test_next_steps_mentions_compose_and_migrate(tmp_path) -> None:
    from alchemiq.scaffold.options import build_options

    opts = build_options(root="notes", monorepo=None, without=None, force=False)
    text = cli.next_steps(opts, tmp_path / "notes")
    assert "docker compose up" in text
    assert "cp .env.example .env" in text
    assert "uv run --env-file .env alchemiq makemigrations -m init" in text
    assert "uv run --env-file .env alchemiq migrate" in text
    # makemigrations must come before migrate
    assert text.index("makemigrations") < text.index("alchemiq migrate")
    assert "uv run --env-file .env uvicorn notes.app:app --reload" in text
    assert "uv run --env-file .env faststream run notes.broker:app" in text


def test_next_steps_without_docker_skips_compose(tmp_path) -> None:
    from alchemiq.scaffold.options import build_options

    opts = build_options(root="notes", monorepo=None, without="docker", force=False)
    text = cli.next_steps(opts, tmp_path / "notes")
    assert "docker compose up" not in text
    assert "cp .env.example .env" in text  # env step stays


def test_next_steps_without_features_skips_their_commands(tmp_path) -> None:
    from alchemiq.scaffold.options import build_options

    opts = build_options(root="notes", monorepo=None, without="fastapi,faststream", force=False)
    text = cli.next_steps(opts, tmp_path / "notes")
    assert "uvicorn" not in text
    assert "faststream" not in text


def test_next_steps_monorepo(tmp_path) -> None:
    from alchemiq.scaffold.options import build_options

    opts = build_options(root="myplatform", monorepo=["svc-a", "svc-b"], without=None, force=False)
    text = cli.next_steps(opts, tmp_path / "myplatform")
    assert "cd myplatform" in text
    assert "uv sync --all-packages" in text
    assert "cp .env.example .env" in text
    assert "services/<name>" in text
    assert "uv run --env-file ../../.env alchemiq makemigrations -m init" in text
    assert "uv run --env-file ../../.env alchemiq migrate" in text
    # monorepo branch must NOT emit the single-service uvicorn line
    assert "uvicorn" not in text
