"""Entry point for ``alchemiq init``: parses arguments, plans, and renders the scaffold."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from alchemiq.scaffold.options import ScaffoldError, ScaffoldOptions, build_options
from alchemiq.scaffold.plan import plan
from alchemiq.scaffold.render import render


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for ``alchemiq init``."""
    parser = argparse.ArgumentParser(
        prog="alchemiq init", description="scaffold an alchemiq project"
    )
    parser.add_argument("root", help="project/service name (single) or workspace root (monorepo)")
    parser.add_argument(
        "--monorepo",
        nargs="+",
        metavar="SERVICE",
        default=None,
        help="create a monorepo with these services (name[:clickhouse])",
    )
    parser.add_argument(
        "--without", default=None, help="comma list: fastapi,faststream,redis,clickhouse,docker"
    )
    parser.add_argument("--force", action="store_true", help="write into a non-empty directory")
    return parser


def next_steps(opts: ScaffoldOptions, dest: Path) -> str:
    """Return the post-scaffold next-steps instructions (printed by ``main``)."""
    lines = [f"Created {dest.name}/. Next:", f"  cd {dest.name}"]
    lines.append("  uv sync --all-packages" if opts.monorepo else "  uv sync")
    lines.append("  cp .env.example .env            # commands below load it via --env-file")
    if opts.feature("docker"):
        infra = [n for n in ("postgres", "clickhouse", "rabbitmq", "redis") if opts.infra(n)]
        lines.append(f"  docker compose up -d            # {' + '.join(infra)}")
    if opts.monorepo:
        lines.append("  # then per service, from the workspace root:")
        lines.append("  cd services/<name>")
        lines.append("  uv run --env-file ../../.env alchemiq makemigrations -m init")
        lines.append("  uv run --env-file ../../.env alchemiq migrate")
    else:
        run = "uv run --env-file .env"
        module = opts.services[0].module
        lines.append(f"  {run} alchemiq makemigrations -m init")
        lines.append(f"  {run} alchemiq migrate")
        if opts.feature("fastapi"):
            lines.append(f"  {run} uvicorn {module}.app:app --reload")
        if opts.feature("faststream"):
            lines.append(f"  {run} faststream run {module}.broker:app   # broker consumer")
    lines.append("Then fill the layers - each package __init__ documents what goes there.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run ``alchemiq init`` and return an exit code.

    Returns ``0`` on success, ``1`` when the destination directory is non-empty
    (pass ``--force`` to overwrite), or ``2`` for invalid arguments.
    """
    ns = build_parser().parse_args(argv)
    try:
        opts = build_options(root=ns.root, monorepo=ns.monorepo, without=ns.without, force=ns.force)
    except ScaffoldError as e:
        print(str(e), file=sys.stderr)
        return 2
    dest = Path.cwd() / opts.root_name
    try:
        render(plan(opts), dest, force=opts.force)
    except FileExistsError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(next_steps(opts, dest))
    return 0
