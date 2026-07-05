import pytest

from alchemiq.types import Maybe, Nothing, Some


def test_some_unwrap():
    assert Some(5).unwrap() == 5
    assert Some(5).is_some is True


def test_nothing_unwrap_raises():
    with pytest.raises(ValueError):
        Nothing.unwrap()
    assert Nothing.is_nothing is True


def test_unwrap_or():
    assert Some(1).unwrap_or(0) == 1
    assert Nothing.unwrap_or(0) == 0


def test_map_and_then():
    assert Some(2).map(lambda x: x + 1) == Some(3)
    assert Nothing.map(lambda x: x + 1) is Nothing
    assert Some(2).and_then(lambda x: Some(x * 2)) == Some(4)


def test_pattern_matching():
    def describe(m: Maybe[int]) -> str:
        match m:
            case Some(v):
                return f"some {v}"
            case _ if m is Nothing:
                return "nothing"
        return "?"

    assert describe(Some(7)) == "some 7"
    assert describe(Nothing) == "nothing"


def test_some_is_frozen():
    import dataclasses

    with pytest.raises(dataclasses.FrozenInstanceError):
        Some(1).value = 2  # type: ignore[misc]


def test_or_else_some_returns_self():
    s = Some(42)
    result = s.or_else(lambda: Some(0))
    assert result is s


def test_or_else_nothing_calls_fn():
    fallback = Some(99)
    result = Nothing.or_else(lambda: fallback)
    assert result is fallback


def test_nothing_and_then_returns_nothing():
    result = Nothing.and_then(lambda x: Some(x * 2))
    assert result is Nothing


def test_nothing_is_singleton():
    from alchemiq.types.maybe import _Nothing

    instance1 = _Nothing()
    instance2 = _Nothing()
    assert instance1 is instance2
    assert instance1 is Nothing


def test_some_is_nothing_is_false():
    assert Some(1).is_nothing is False


def test_nothing_is_some_is_false():
    assert Nothing.is_some is False


def test_nothing_repr():
    assert repr(Nothing) == "Nothing"


def test_maybe_type_bind_raw_value():
    """process_bind_param accepts a raw (unwrapped) value - the else branch (line 165)."""
    from alchemiq.types.maybe import _MaybeType
    from alchemiq.types.strings import Email

    mt = _MaybeType(Email())
    # Passing a plain string (not Some/Nothing) hits the else: raw = value branch.
    assert mt.process_bind_param("a@b.com", None) == "a@b.com"
