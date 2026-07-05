"""Alchemiq exception hierarchy: all library-specific errors live here."""

from __future__ import annotations


class AlchemiqError(Exception):
    """Root of all Alchemiq exceptions."""


class ConfigError(AlchemiqError):
    """Invalid model/field declaration, or a missing optional dependency."""


class ValidationError(AlchemiqError):
    """Eager field validation failure (on assignment or construction)."""

    def __init__(
        self,
        *,
        reason: str,
        field: str | None = None,
        value: object = None,
        model: str | None = None,
        errors: list[ValidationError] | None = None,
    ) -> None:
        self.reason = reason
        self.field = field
        self.value = value
        self.model = model
        self.errors: list[ValidationError] = errors or []
        super().__init__(self._render())

    def _render(self) -> str:
        if self.errors:
            return f"{len(self.errors)} validation errors for {self.model or '?'}: " + "; ".join(
                e._render() for e in self.errors
            )
        loc = f"{self.model + '.' if self.model else ''}{self.field or '?'}"
        return f"{loc}: {self.reason} (got {self.value!r})"

    @classmethod
    def aggregate(
        cls, errors: list[ValidationError], *, model: str | None = None
    ) -> ValidationError:
        """Collapse a list of errors into one; returns the single error unchanged when len == 1."""
        if len(errors) == 1:
            return errors[0]
        return cls(reason="multiple errors", model=model, errors=list(errors))


class QueryError(AlchemiqError):
    """Invalid query: bad field, operator, or value at build/compile time."""


class UnknownFieldError(QueryError):
    """Referenced field or traversal path does not exist on the model."""


class UnknownOperatorError(QueryError):
    """Unknown lookup suffix (operator)."""


class DeserializationError(QueryError):
    """Malformed Q wire payload."""


class DisallowedFieldError(QueryError):
    """Field/path rejected by the deserialization whitelist (security)."""


class InvalidCursorError(QueryError):
    """Malformed, tampered, or stale pagination cursor."""


class PersistenceError(AlchemiqError):
    """Runtime data-access failure (engine, session, repository, loading)."""


class EngineNotConfiguredError(PersistenceError):
    """A repository/UnitOfWork was used before alchemiq.configure(dsn)."""


class NotFoundError(PersistenceError):
    """Expected exactly one row but found none."""


class MultipleResultsFound(PersistenceError):
    """Expected at most one row but found several."""


class ConcurrentModificationError(PersistenceError):
    """Optimistic-lock conflict: the row was modified since it was read."""


class RelationNotLoaded(PersistenceError):
    """Accessed a relationship that was not eager-loaded (no implicit lazy IO)."""


class ClickHouseError(PersistenceError):
    """ClickHouse IO failure (connection, query, insert, DDL)."""


class ClickHouseNotConfiguredError(ClickHouseError):
    """A ClickHouse operation was used before configure_clickhouse()."""


class UnsupportedOperationError(ClickHouseError):
    """The operation is not supported by ClickHouse (e.g. row UPDATE/DELETE)."""
