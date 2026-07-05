"""Parse and validate ``alchemiq init`` CLI arguments into typed option objects."""

from __future__ import annotations

import re
from dataclasses import dataclass

_NAME_RE = re.compile(r"^[a-z][a-z0-9]*([-_][a-z0-9]+)*$")
WITHOUT_TOKENS: frozenset[str] = frozenset(
    {"fastapi", "faststream", "redis", "clickhouse", "docker"}
)
BACKENDS: frozenset[str] = frozenset({"postgres", "clickhouse"})


class ScaffoldError(Exception):
    """A user-facing scaffolding error (bad name, unknown flag, conflicting options)."""


@dataclass(frozen=True)
class Service:
    """A single service with its resolved name and backend."""

    name: str
    backend: str

    @property
    def module(self) -> str:
        """Python import-safe name: hyphens replaced with underscores."""
        return self.name.replace("-", "_")

    @property
    def dist(self) -> str:
        """Distribution (PyPI-style) name, identical to ``name``."""
        return self.name


def parse_service(token: str) -> Service:
    """Parse a ``NAME[:backend]`` token into a ``Service``.

    The backend defaults to ``postgres`` when omitted. Raises
    ``ScaffoldError`` for unknown backends or invalid names.
    """
    name, sep, backend = token.partition(":")
    backend = backend or "postgres"
    if sep and backend not in BACKENDS:
        raise ScaffoldError(
            f"unknown backend {backend!r} in {token!r} (choose: {', '.join(sorted(BACKENDS))})"
        )
    if not _NAME_RE.match(name):
        raise ScaffoldError(
            f"invalid name {name!r}: use lowercase letters/digits with - or _ separators"
        )
    return Service(name=name, backend=backend)


@dataclass(frozen=True)
class ScaffoldOptions:
    """Validated, immutable scaffold configuration produced by ``build_options``."""

    root_name: str
    monorepo: bool
    services: tuple[Service, ...]
    without: frozenset[str]
    force: bool

    def feature(self, token: str) -> bool:
        """Return ``True`` when *token* was not excluded via ``--without``."""
        return token not in self.without

    def infra(self, token: str) -> bool:
        """Return ``True`` when the infrastructure service *token* should be included.

        ``redis`` is always on; ``rabbitmq`` follows ``faststream``; ``postgres`` /
        ``clickhouse`` are on only when at least one service uses that backend.
        """
        if token in self.without:
            return False
        if token == "redis":
            return True
        if token == "rabbitmq":
            return self.feature("faststream")
        if token in ("postgres", "clickhouse"):
            return any(s.backend == token for s in self.services)
        return self.feature(token)

    def root_enabled(self, token: str) -> bool:
        """Return ``True`` when *token* should be active in the monorepo workspace root.

        Routes infra tokens (``postgres``, ``clickhouse``, ``redis``, ``rabbitmq``) through
        ``infra``; ``monorepo`` reflects the layout; all other tokens through ``feature``.
        """
        if token in ("postgres", "clickhouse", "redis", "rabbitmq"):
            return self.infra(token)
        if token == "monorepo":
            return self.monorepo
        return self.feature(token)

    def service_enabled(self, svc: Service, token: str) -> bool:
        """Return ``True`` when *token* should be active for the given *svc*.

        Backend tokens (``postgres``, ``clickhouse``) match only if *svc* uses that backend;
        ``rabbitmq`` follows ``faststream``; ``monorepo`` reflects the layout; all other
        tokens follow ``feature``.
        """
        if token in ("postgres", "clickhouse"):
            return svc.backend == token
        if token == "redis":
            return self.feature("redis")
        if token == "rabbitmq":
            return self.feature("faststream")
        if token == "monorepo":
            return self.monorepo
        return self.feature(token)


def _parse_without(without: str | None) -> frozenset[str]:
    if not without:
        return frozenset()
    tokens = {t.strip() for t in without.split(",") if t.strip()}
    unknown = tokens - WITHOUT_TOKENS
    if unknown:
        raise ScaffoldError(
            f"unknown --without token(s): {', '.join(sorted(unknown))} "
            f"(choose: {', '.join(sorted(WITHOUT_TOKENS))})"
        )
    return frozenset(tokens)


def build_options(
    *, root: str, monorepo: list[str] | None, without: str | None, force: bool
) -> ScaffoldOptions:
    """Build and validate a ``ScaffoldOptions`` from raw CLI arguments.

    For single-service mode *root* is ``NAME[:backend]``; for monorepo mode
    *root* is the workspace name (no ``:backend`` suffix) and *monorepo* lists
    each ``NAME[:backend]`` service. Raises ``ScaffoldError`` on any
    validation failure (unknown tokens, duplicate names, conflicting flags).
    """
    drop = _parse_without(without)
    if monorepo is not None:
        if not monorepo:
            raise ScaffoldError("--monorepo needs at least one service name")
        root_svc = parse_service(root)
        if ":" in root:
            raise ScaffoldError("monorepo root name must not carry a :backend suffix")
        services = tuple(parse_service(t) for t in monorepo)
        names = [s.name for s in services]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ScaffoldError(f"duplicate service name(s): {', '.join(sorted(dupes))}")
        opts = ScaffoldOptions(root_svc.name, True, services, drop, force)
    else:
        svc = parse_service(root)
        opts = ScaffoldOptions(svc.name, False, (svc,), drop, force)
    if "clickhouse" in drop and any(s.backend == "clickhouse" for s in opts.services):
        raise ScaffoldError("--without clickhouse conflicts with a :clickhouse service")
    return opts
