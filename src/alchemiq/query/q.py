"""Q predicate: composable filter expression used by QuerySet and Repository."""

from __future__ import annotations

from typing import Any


class Q:
    """Django-style boolean predicate tree of ``(field__op, value)`` leaves.

    Combine predicates with ``&`` (AND), ``|`` (OR), and ``~`` (NOT). Pass to
    :meth:`.QuerySet.filter` / :meth:`.Repository.filter` for type-safe filtering.

    Supported lookup suffixes: ``__eq`` (default), ``__ne``, ``__lt``,
    ``__lte``, ``__gt``, ``__gte``, ``__in``, ``__not_in``, ``__isnull``,
    ``__contains``, ``__icontains``, ``__startswith``, ``__endswith``.

    E.g.::

        >>> q1 = Q(status="active") & Q(age__gte=18)
        >>> q2 = ~Q(role__in=["admin", "staff"])

        >>> q_or = Q(role="admin") | Q(role="staff")
        >>> q_or.connector
        'OR'

        >>> neg = ~Q(deleted=True)
        >>> neg.negated
        True

    Pass the composed predicate to ``filter()`` for execution::

        active_adults = await (
            Repository(User)
            .filter(Q(status="active") & Q(age__gte=18))
            .all()
        )
    """

    AND = "AND"
    OR = "OR"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.children: list[Any] = [*args, *kwargs.items()]
        self.connector: str = self.AND
        self.negated: bool = False

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Q):
            return NotImplemented
        return (
            self.children == other.children
            and self.connector == other.connector
            and self.negated == other.negated
        )

    def __hash__(self) -> int:
        return hash((tuple(map(repr, self.children)), self.connector, self.negated))

    def __repr__(self) -> str:
        parts: list[str] = []
        for c in self.children:
            if isinstance(c, tuple):
                parts.append(f"{c[0]}={c[1]!r}")
            else:
                parts.append(repr(c))
        prefix = "NOT " if self.negated else ""
        return f"<Q {prefix}{self.connector}({', '.join(parts)})>"

    def _combine(self, other: Q, connector: str) -> Q:
        if not isinstance(other, Q):
            raise TypeError(f"Cannot combine Q with {type(other).__name__}")
        combined = Q(self, other)
        combined.connector = connector
        return combined

    def __and__(self, other: Q) -> Q:
        return self._combine(other, self.AND)

    def __or__(self, other: Q) -> Q:
        return self._combine(other, self.OR)

    def __invert__(self) -> Q:
        clone = Q(*self.children)
        clone.connector = self.connector
        clone.negated = not self.negated
        return clone

    def to_data(self) -> list[Any]:
        """Serialize this ``Q`` to a compact, JSON-safe nested list."""
        from alchemiq.query.serialize import to_data

        return to_data(self)

    @classmethod
    def from_data(
        cls,
        data: Any,
        model: type,
        allow: set[str] | None = None,
        deny: set[str] | None = None,
    ) -> Q:
        """Deserialize a ``Q`` from a :meth:`.Q.to_data` payload, validating fields against *model*.

        :param data: nested list produced by :meth:`.Q.to_data`.
        :param model: model class used to validate field names and resolve Python types.
        :param allow: explicit allow-list of field paths; required to permit traversal fields.
        :param deny: optional deny-list of field paths.
        :raises DeserializationError: if the payload structure is invalid.
        :raises DisallowedFieldError: if a field is denied or not in the allow-list.
        :raises UnknownOperatorError: if the payload contains an unrecognised lookup operator.
        """
        from alchemiq.query.serialize import from_data

        return from_data(data, model, allow, deny)

    def to_bytes(self) -> bytes:
        """Serialize this ``Q`` to compact UTF-8 JSON bytes."""
        from alchemiq.query.serialize import to_bytes

        return to_bytes(self)

    def to_base64(self) -> str:
        """Serialize this ``Q`` to a urlsafe base64 string."""
        from alchemiq.query.serialize import to_base64

        return to_base64(self)

    @classmethod
    def from_bytes(
        cls, data: bytes, model: type, allow: set[str] | None = None, deny: set[str] | None = None
    ) -> Q:
        """Deserialize a ``Q`` from UTF-8 JSON bytes produced by :meth:`to_bytes`."""
        from alchemiq.query.serialize import from_bytes

        return from_bytes(data, model, allow, deny)

    @classmethod
    def from_base64(
        cls, s: str, model: type, allow: set[str] | None = None, deny: set[str] | None = None
    ) -> Q:
        """Deserialize a ``Q`` from a urlsafe base64 string produced by :meth:`to_base64`."""
        from alchemiq.query.serialize import from_base64

        return from_base64(s, model, allow, deny)
