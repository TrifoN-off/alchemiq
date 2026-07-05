# Contributing to alchemiq

Thanks for your interest in improving alchemiq. This guide covers the local
setup, the checks every change must pass, and how releases work.

## Development setup

alchemiq uses [uv](https://docs.astral.sh/uv/) for environment and dependency
management, and targets Python 3.12 and newer.

```bash
git clone git@github.com:TrifoN-off/alchemiq.git
cd alchemiq
uv sync --all-extras --group dev
```

## The local gate

Run the full gate before opening a pull request. Sync first, then use
`--no-sync` so the optional extras stay installed.

```bash
uv sync --all-extras --group dev

# Lint, format, types
uv run --no-sync ruff check
uv run --no-sync ruff format --check
uv run --no-sync ty check
uv run --no-sync mypy --follow-imports=silent tests/typing/models.py
uv run --no-sync pyright --project tests/typing

# Tests (run the markers separately)
uv run --no-sync pytest -m unit        --cov=alchemiq --cov-report=
uv run --no-sync pytest -m integration --cov=alchemiq --cov-report= --cov-append

# ClickHouse tests run file by file
export TESTCONTAINERS_RYUK_DISABLED=true
for f in tests/clickhouse/test_*.py; do
  uv run --no-sync pytest "$f" --cov=alchemiq --cov-report= --cov-append -q
done

uv run --no-sync coverage report --fail-under=90

# Docs (warnings are errors)
uv sync --all-extras --group docs
uv run --no-sync sphinx-build -W --keep-going -b html docs docs/_build/html
```

Integration and ClickHouse tests need Docker; they start PostgreSQL and
ClickHouse through testcontainers.

## Commit messages

This project uses [Conventional Commits](https://www.conventionalcommits.org/).
Python Semantic Release derives the version and changelog from them, so the
prefix matters:

| Prefix | Effect (while on 0.x) |
|---|---|
| `fix:` | patch release |
| `feat:` | minor release |
| `feat!:` or `BREAKING CHANGE:` | minor while on 0.x |
| `docs:` `test:` `chore:` `ci:` `refactor:` | no release |

Do not bump the version or edit `CHANGELOG.md` by hand; the release pipeline
owns both.

## Pull requests

1. Branch off `main`.
2. Keep the change focused, and add tests for new behaviour (coverage stays at
   90 or above).
3. Update the matching `docs/guide/` page and docstrings in the same PR.
4. Make sure the local gate is green.
5. Open the PR with a Conventional Commit style title.

## Public API

The public surface is whatever `alchemiq.__all__` (and each integration
subpackage's `__all__`) exports. Adding to it is a `feat:`; changing or removing
from it is a breaking change.
