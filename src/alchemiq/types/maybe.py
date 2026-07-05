"""Maybe[T] - functional option type stored as a nullable column."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from sqlalchemy.types import NullType, TypeDecorator, TypeEngine

from alchemiq.types.base import FieldType

T = TypeVar("T")
U = TypeVar("U")
V = TypeVar("V")


class Maybe(Generic[T], ABC):  # noqa: UP046
    """Functional option type for nullable model columns.

    ``Maybe[T]`` is the annotation used on a model field to declare a nullable
    column whose attribute always holds either :data:`.Some` (a value is present)
    or :data:`.Nothing` (absent / ``NULL``).  Raw assignment of a plain value
    auto-wraps it; ``None`` is coerced to ``Nothing``.

    E.g.::

        class Profile(Model):
            id: PK[int]
            nickname: Maybe[str]

        p = Profile()
        p.nickname = "neo"           # stored as Some("neo")
        p.nickname = Nothing         # stored as Nothing

        label = p.nickname.match(
            some=lambda v: v.upper(),
            nothing=lambda: "anonymous",
        )

    .. note::

        :meth:`.match` is the preferred eliminator - it forces you to handle
        both cases and avoids the ``ValueError`` raised by :meth:`.unwrap` on
        ``Nothing``.

    .. seealso:: :data:`.Some`, :data:`.Nothing`
    """

    @property
    @abstractmethod
    def is_some(self) -> bool:
        """Return ``True`` if this is :class:`.Some`, ``False`` if :data:`.Nothing`."""

    @property
    @abstractmethod
    def is_nothing(self) -> bool:
        """Return ``True`` if this is :data:`.Nothing`, ``False`` if :class:`.Some`."""

    @abstractmethod
    def unwrap(self) -> T:
        """Extract the value from :class:`.Some` or raise ``ValueError`` for :data:`.Nothing`."""

    @abstractmethod
    def unwrap_or(self, default: U) -> T | U:
        """Extract the value from :class:`.Some` or return *default* for :data:`.Nothing`."""

    @abstractmethod
    def map(self, fn: Callable[[T], U]) -> Maybe[U]:
        """Apply *fn* to the value if :class:`.Some`; return :data:`.Nothing` unchanged."""

    @abstractmethod
    def and_then(self, fn: Callable[[T], Maybe[U]]) -> Maybe[U]:
        """Flatmap: apply *fn* (which returns a ``Maybe``) to the value if :class:`.Some`."""

    @abstractmethod
    def or_else(self, fn: Callable[[], Maybe[T]]) -> Maybe[T]:
        """Return ``self`` if :class:`.Some`; call *fn* if :data:`.Nothing`."""

    @abstractmethod
    def match(self, *, some: Callable[[T], U], nothing: Callable[[], V]) -> U | V:
        """Eliminate the ``Maybe``: call *some(value)* if :class:`.Some`, *nothing()* if absent.

        The canonical way to consume a ``Maybe`` without risking an exception.

        E.g.::

            >>> Some("neo").match(some=str.upper, nothing=lambda: "anon")
            'NEO'
            >>> Nothing.match(some=str.upper, nothing=lambda: "anon")
            'anon'

        :param some: callable invoked with the inner value when this is :class:`.Some`.
        :param nothing: callable invoked with no arguments when this is :data:`.Nothing`.
        :return: the result of whichever callable was invoked.
        """


@dataclass(frozen=True)
class Some(Maybe[T]):
    """A :class:`.Maybe` container that holds a value."""

    value: T
    __match_args__ = ("value",)

    @property
    def is_some(self) -> bool:
        """Return True - this is a Some."""
        return True

    @property
    def is_nothing(self) -> bool:
        """Return False - this is a Some, not Nothing."""
        return False

    def unwrap(self) -> T:
        """Return the wrapped value."""
        return self.value

    def unwrap_or(self, default: Any) -> T:
        """Return the wrapped value, ignoring the default."""
        return self.value

    def map(self, fn: Callable[[T], U]) -> Maybe[U]:
        """Apply ``fn`` to the value and wrap the result in ``Some``."""
        return Some(fn(self.value))

    def and_then(self, fn: Callable[[T], Maybe[U]]) -> Maybe[U]:
        """Apply ``fn`` to the value and return its ``Maybe`` result."""
        return fn(self.value)

    def or_else(self, fn: Callable[[], Maybe[T]]) -> Maybe[T]:
        """Return self - value is present, so the fallback is not called."""
        return self

    def match(self, *, some: Callable[[T], U], nothing: Callable[[], V]) -> U | V:
        """Call ``some(value)`` and return its result."""
        return some(self.value)


class _Nothing(Maybe[Any]):
    """The Nothing singleton for the Maybe[T] container."""

    _instance: _Nothing | None = None

    def __new__(cls) -> _Nothing:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def is_some(self) -> bool:
        return False

    @property
    def is_nothing(self) -> bool:
        return True

    def unwrap(self) -> Any:
        raise ValueError("unwrap() called on Nothing")

    def unwrap_or(self, default: U) -> U:
        return default

    def map(self, fn: Callable[[Any], U]) -> Maybe[U]:
        return self

    def and_then(self, fn: Callable[[Any], Maybe[U]]) -> Maybe[U]:
        return self

    def or_else(self, fn: Callable[[], Maybe[Any]]) -> Maybe[Any]:
        return fn()

    def match(self, *, some: Callable[[Any], U], nothing: Callable[[], V]) -> U | V:
        return nothing()

    def __repr__(self) -> str:
        return "Nothing"


Nothing: _Nothing = _Nothing()


class _MaybeType(TypeDecorator[Any]):
    """TypeDecorator that wraps an inner FieldType's column type.

    Bind path: Some(v) -> unwrap v (then inner TypeDecorator transform if any),
               Nothing/None -> None.
    Result path: None -> Nothing, else Some(inner_transform(value)).
    """

    # NullType is required as a class-level placeholder; impl_instance is
    # overridden in __init__ with the real underlying column type.
    impl = NullType
    cache_ok = True

    def __init__(self, inner_field: Any) -> None:
        self._inner_field = inner_field
        # Cache the inner column type once to avoid re-allocating on every row.
        self._inner_col_type = inner_field.column_type()
        # Resolve to the actual storage type when inner is itself a TypeDecorator
        # (e.g. Maybe[Money] -> MinorUnits -> BigInteger).
        if isinstance(self._inner_col_type, TypeDecorator):
            actual_impl = self._inner_col_type.impl_instance
        else:
            actual_impl = self._inner_col_type
        super().__init__()
        # Override impl_instance so SQLAlchemy uses the correct storage type.
        self.impl_instance = actual_impl

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is Nothing or value is None:
            return None
        if isinstance(value, Some):
            raw = value.value
        else:
            raw = value
        # Delegate to inner TypeDecorator if applicable.
        if isinstance(self._inner_col_type, TypeDecorator):
            return self._inner_col_type.process_bind_param(raw, dialect)
        return raw

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return Nothing
        if isinstance(self._inner_col_type, TypeDecorator):
            transformed = self._inner_col_type.process_result_value(value, dialect)
            return Some(transformed)
        return Some(value)


class MaybeField(FieldType[Any]):
    """Field wrapper that makes a column nullable and holds Some/Nothing on the attribute."""

    def __init__(self, inner: FieldType, **kw: Any) -> None:
        from alchemiq.types.base import _MISSING

        super().__init__(
            nullable=True,
            unique=kw.get("unique", False),
            index=kw.get("index", False),
            primary_key=kw.get("primary_key", False),
            default=kw.get("default", _MISSING),
            server_default=kw.get("server_default", None),
            max_length=kw.get("max_length", None),
            onupdate=kw.get("onupdate", None),
        )
        self.inner = inner
        self.python_type = inner.python_type

    def column_type(self) -> TypeEngine[Any]:
        """Return a ``_MaybeType`` wrapping the inner field's column type."""
        return _MaybeType(self.inner)

    def validate(self, value: Any) -> Any:
        """Coerce the value to ``Some``/``Nothing`` and delegate inner validation."""
        if value is Nothing:
            return Nothing
        if isinstance(value, Some):
            return Some(self.inner.validate(value.value))
        if value is None:
            return Nothing
        return Some(self.inner.validate(value))
