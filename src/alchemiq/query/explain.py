"""SQLAlchemy custom clause for EXPLAIN / EXPLAIN ANALYZE (PostgreSQL only)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ClauseElement, Executable


class _Explain(Executable, ClauseElement):
    """Wrap a Select so ``session.execute()`` runs ``EXPLAIN [(ANALYZE[, FORMAT JSON])] <select>``.

    Options are grouped in parentheses when present; e.g.
    ``EXPLAIN (ANALYZE, FORMAT JSON) SELECT ...``.
    """

    inherit_cache = False

    def __init__(self, stmt: Any, *, analyze: bool, fmt: str) -> None:
        self.stmt = stmt
        self.analyze = analyze
        self.fmt = fmt


@compiles(_Explain, "postgresql")
def _compile_explain_pg(element: _Explain, compiler: Any, **kw: Any) -> str:
    opts: list[str] = []
    if element.analyze:
        opts.append("ANALYZE")
    if element.fmt == "json":
        opts.append("FORMAT JSON")
    prefix = f"EXPLAIN ({', '.join(opts)}) " if opts else "EXPLAIN "
    return prefix + compiler.process(element.stmt, **kw)
