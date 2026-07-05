"""File-selection and in-memory render plan for the scaffold template tree."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from alchemiq.scaffold.options import ScaffoldOptions, Service

RenderedFile = tuple[str, str]

# (path-needle, feature) - needle ending in "/" matches a path segment, else basename.
_FILE_FEATURE: tuple[tuple[str, str], ...] = (
    ("app.py", "fastapi"),
    ("adapters/http/", "fastapi"),
    ("broker.py", "faststream"),
    ("adapters/messaging/", "faststream"),
    ("docker-compose.yml", "docker"),
    ("Dockerfile", "docker"),
    (".dockerignore", "docker"),
    ("postgres-init.sh", "docker"),
)

# Files that exist in a Postgres and a ClickHouse flavour: ``<stem>_clickhouse.py``
# renders to ``<stem>.py`` for ClickHouse-backed services and is skipped otherwise.
_BACKEND_VARIANT_STEMS: tuple[str, ...] = (
    "domain/models",
    "app",
    "broker",
    "tests/test_models",
    "tests/conftest",
)

_IF = re.compile(r"^(?P<body>.*?)[ \t]*#[ \t]*alchemiq:if(?P<neg>not)?[ \t]+(?P<token>\w+)[ \t]*$")
_BLOCK = re.compile(r"^[ \t]*#[ \t]*alchemiq:block[ \t]+(?P<token>\w+)[ \t]*$")
_ENDBLOCK = re.compile(r"^[ \t]*#[ \t]*alchemiq:endblock[ \t]*$")


def included(relpath: str, opts: ScaffoldOptions, *, nested: bool) -> bool:
    """Return ``True`` when *relpath* should be written given *opts*.

    ``nested=True`` suppresses ``docker-compose.yml`` and ``.env.example``
    inside monorepo service subtrees (the workspace root owns both: services
    are run with ``uv run --env-file ../../.env``).
    """
    base = relpath.rsplit("/", 1)[-1]
    if nested and base in ("docker-compose.yml", ".env.example"):
        return False  # nested monorepo service: root owns compose and env
    for needle, feature in _FILE_FEATURE:
        hit = (
            relpath.startswith(needle) or f"/{needle}" in relpath
            if needle.endswith("/")
            else base == needle
        )
        if hit and not opts.feature(feature):
            return False
    return True


def process_text(text: str, enabled: Callable[[str], bool], subs: dict[str, str]) -> str:
    """Evaluate inline template directives and apply substitutions.

    Handles three marker forms:
    ``# alchemiq:if[not] TOKEN`` - include/exclude the rest of the line;
    ``# alchemiq:block TOKEN`` / ``# alchemiq:endblock`` - include/exclude a
    multi-line block. Substitutions in *subs* are applied last, after all
    directives are resolved.
    """
    trailing_nl = text.endswith("\n")
    out: list[str] = []
    block_stack: list[bool] = []
    for line in text.splitlines():
        mb = _BLOCK.match(line)
        if mb:
            block_stack.append(enabled(mb["token"]))
            continue
        if _ENDBLOCK.match(line):
            if block_stack:
                block_stack.pop()
            continue
        if block_stack and not all(block_stack):
            continue
        mi = _IF.match(line)
        if mi:
            on = enabled(mi["token"])
            keep = (not on) if mi["neg"] else on
            if not keep:
                continue
            line = mi["body"]
        out.append(line)
    result = "\n".join(out)
    if trailing_nl and result:
        result += "\n"
    for key, val in subs.items():
        result = result.replace(key, val)
    return result


TEMPLATES_ROOT = Path(__file__).parent / "templates"


def extras_for(svc: Service, opts: ScaffoldOptions) -> str:
    """Return the comma-separated ``[project.optional-dependencies]`` extras string for *svc*.

    The backend extra (``postgres`` -> asyncpg, ``clickhouse`` -> clickhouse-connect)
    is always included so the generated project pulls its database driver.
    """
    extras: list[str] = []
    if opts.feature("fastapi"):
        extras.append("fastapi")
    if opts.feature("faststream"):
        extras.append("faststream")
    if opts.feature("redis"):
        extras.append("redis")
    extras.append(svc.backend)
    extras.append("migrations")
    return ",".join(extras)


def _subs(svc: Service, opts: ScaffoldOptions) -> dict[str, str]:
    return {
        "__ALCHEMIQ_MODULE__": svc.module,
        "__ALCHEMIQ_DIST__": svc.dist,
        "__ALCHEMIQ_NAME__": svc.name,
        "__ALCHEMIQ_ROOT__": opts.root_name,
        "__ALCHEMIQ_EXTRAS__": extras_for(svc, opts),
        "__ALCHEMIQ_BACKEND__": svc.backend,
        # Monorepo services share the workspace-root .env (they emit none of
        # their own); standalone projects own a local one.
        "__ALCHEMIQ_ENV_FILE__": "../../.env" if opts.monorepo else ".env",
    }


def _render_tree(
    src: Path,
    dest_prefix: str,
    opts: ScaffoldOptions,
    enabled: Callable[[str], bool],
    subs: dict[str, str],
    *,
    nested: bool,
) -> list[RenderedFile]:
    out: list[RenderedFile] = []
    for path in sorted(src.rglob("*.tmpl")):
        rel = path.relative_to(src).as_posix().removesuffix(".tmpl")
        # Backend-specific files first: CH variants render to the plain filename.
        # This must happen before the feature check so that e.g. app_clickhouse.py
        # is judged as app.py (and dropped under --without fastapi).
        backend = subs.get("__ALCHEMIQ_BACKEND__")
        skip = False
        for stem in _BACKEND_VARIANT_STEMS:
            ch = f"{stem}_clickhouse.py"
            pg = f"{stem}.py"
            if rel.endswith(ch):
                if backend != "clickhouse":
                    skip = True  # CH variant not used for a Postgres service
                else:
                    rel = rel[: -len(ch)] + pg  # CH service: rename _clickhouse -> plain
                break
            if rel.endswith(pg) and backend == "clickhouse":
                skip = True  # Postgres variant not used for a ClickHouse service
                break
        if skip:
            continue
        if not included(rel, opts, nested=nested):
            continue
        for key, val in subs.items():
            rel = rel.replace(key, val)
        text = process_text(path.read_text(encoding="utf-8"), enabled, subs)
        out.append((dest_prefix + rel, text))
    return out


def plan(opts: ScaffoldOptions, *, templates_root: Path | None = None) -> tuple[RenderedFile, ...]:
    """Produce the full set of (output-path, text) pairs for *opts*.

    For single-service mode the ``single/`` template tree is rendered directly.
    For monorepo mode the ``monorepo_root/`` tree is rendered first, then each
    service's ``single/`` tree is placed under ``services/<name>/`` with
    ``nested=True`` to suppress redundant compose files.
    """
    root = templates_root or TEMPLATES_ROOT
    if not opts.monorepo:
        svc = opts.services[0]
        files = _render_tree(
            root / "single",
            "",
            opts,
            lambda t: opts.service_enabled(svc, t),
            _subs(svc, opts),
            nested=False,
        )
        return tuple(files)
    pg_databases = " ".join(s.module for s in opts.services if s.backend == "postgres")
    files = _render_tree(
        root / "monorepo_root",
        "",
        opts,
        opts.root_enabled,
        {"__ALCHEMIQ_ROOT__": opts.root_name, "__ALCHEMIQ_PG_DATABASES__": pg_databases},
        nested=False,
    )
    if not pg_databases:  # all-ClickHouse workspace: no Postgres, no init script
        files = [f for f in files if not f[0].endswith("postgres-init.sh")]
    for svc in opts.services:
        files += _render_tree(
            root / "single",
            f"services/{svc.name}/",
            opts,
            lambda t, s=svc: opts.service_enabled(s, t),
            _subs(svc, opts),
            nested=True,
        )
    return tuple(files)
