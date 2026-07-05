"""Top-level CLI entry point: dispatches ``alchemiq init`` and migration sub-commands."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Route ``init`` to the scaffolder; delegate every other command to the migrations CLI."""
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] == "init":
        from alchemiq.scaffold.cli import main as scaffold_main

        return scaffold_main(args[1:])
    from alchemiq.migrations.cli import main as migrations_main

    return migrations_main(args)
