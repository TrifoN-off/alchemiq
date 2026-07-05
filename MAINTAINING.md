# Maintaining alchemiq

How this repository runs: release automation, CI, versioning policy, and where
things live. For local setup, the test gate, commit conventions, and the
pull-request process, see [CONTRIBUTING.md](CONTRIBUTING.md) - everything there
applies to maintainers too. The one rule that overrides everything else:
**never merge red.**

---

## Releases are automatic

Releases are driven by [Python Semantic Release](https://python-semantic-release.readthedocs.io/)
from Conventional Commits - the version is never bumped by hand. On every push
to `main`, `.github/workflows/release.yml`:

1. runs PSR, which reads the commit history and decides whether a release is
   due (`fix:` -> patch, `feat:` -> minor; see the table in CONTRIBUTING.md);
2. if so: updates `pyproject.toml` / `src/alchemiq/__init__.py` / `CHANGELOG.md`,
   creates the git tag and the GitHub Release, and builds the sdist + wheel
   (the build runs **inside** the PSR Docker container, hence
   `build_command = "python -m pip install build && python -m build"` in
   `[tool.semantic_release]` - do not switch it to a tool that only exists on
   the runner, such as `uv`);
3. publishes to PyPI via Trusted Publishing (OIDC, `id-token: write`) - there
   is no API token to rotate.

The publish step is gated on `steps.release.outputs.released`, so a no-op push
to `main` (docs, chores) does not republish.

Preview what PSR would do without changing anything:

```bash
uv run --no-sync semantic-release version --noop --print
```

`major_on_zero = false` and `allow_zero_version = true` are set: while on
`0.x`, a breaking change bumps the **minor** (`0.1 -> 0.2`) instead of jumping
to `1.0.0`.

Note on tool versions: the workflow pins the PSR **GitHub Action**
(`v9.21.1`) while the dev group locks the PSR **CLI** (`10.x`) for the local
preview command. The config keys used are valid in both majors; when bumping
either, re-check the other.

### Verify a release

```bash
uv venv --python 3.12 /tmp/ve   # the minimum supported version
uv pip install --python /tmp/ve alchemiq
/tmp/ve/bin/python -c "import alchemiq; print(alchemiq.__version__)"
```

Then check that the PyPI page renders the README and that ReadTheDocs built
the new version.

---

## CI

`.github/workflows/ci.yml` runs on every push and pull request: lint + format,
the three type checkers, unit / integration / ClickHouse tests with coverage
`--fail-under=90`, a docs build with warnings-as-errors, and a packaging smoke
test, across Python 3.12 / 3.13 / 3.14.

Known caveat: a single-process `pytest -m clickhouse` run flakes under
Python 3.14 + testcontainers (session-scoped container vs per-test event
loop), so both the local gate and the CI step run those tests file by file
with `TESTCONTAINERS_RYUK_DISABLED=true`. Keep it that way.

---

## Versioning: when to go 1.0

Stay on `0.x` (`Development Status :: 4 - Beta`) while the public API is still
settling - that is the honest signal, and it lets breaking changes ride minor
bumps. When the surface has stopped moving and you are ready to commit to
SemVer guarantees, bump to `1.0.0` and switch the classifier to
`5 - Production/Stable`. That is a deliberate, separate decision - not
something PSR will ever do on its own (`major_on_zero = false`).

---

## Dependencies and Python versions

- The core depends only on SQLAlchemy and Pydantic. Everything else lives
  behind an optional extra - keep it that way: a new heavy dependency belongs
  behind an extra, not in the core.
- Dependency updates: enable Dependabot or Renovate for `pyproject.toml` and
  GitHub Actions. Their `chore(deps)` / `build(deps)` commits do not trigger
  releases.
- When a new CPython ships, extend the `python-version` matrix in `ci.yml`
  (currently `["3.12", "3.13", "3.14"]`) and add the trove classifier.

---

## Documentation

The site is Sphinx (autodoc + MyST + furo), built by ReadTheDocs from
`.readthedocs.yaml` on every push; pull requests get a preview build.

- `sphinx-build -W` means **warnings are errors**; the most common trap is a
  cross-reference role pointing at a non-exported symbol. Docstrings use
  reST/SQLAlchemy style, and `:class:` / `:meth:` / `:func:` roles are used
  only on `__all__`-exported symbols - everything else is plain double
  backticks.
- A behaviour change should update its `docs/guide/` page and the docstring in
  the same PR (CONTRIBUTING.md holds contributors to this too).

---

## Where things live

| Area | Path |
|---|---|
| Public re-exports / `__all__` | `src/alchemiq/__init__.py` |
| Models, field types | `src/alchemiq/model/`, `src/alchemiq/types/` |
| Query (Q / QuerySet) | `src/alchemiq/query/` |
| Repository, Unit of Work | `src/alchemiq/repository/`, `src/alchemiq/runtime/` |
| Integrations | `src/alchemiq/{fastapi,faststream,outbox,cache,clickhouse,health}/` |
| Migrations + unified CLI | `src/alchemiq/migrations/`, `src/alchemiq/cli.py` |
| Scaffolding (`alchemiq init`) | `src/alchemiq/scaffold/` |
| Docs site (Sphinx) | `docs/conf.py`, `docs/index.md`, `docs/guide/`, `docs/reference/` |
| Release automation | `.github/workflows/release.yml`, `[tool.semantic_release]` |
| CI | `.github/workflows/ci.yml` |
