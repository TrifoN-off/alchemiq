import pytest

from alchemiq.exceptions import (
    AlchemiqError,
    EngineNotConfiguredError,
    MultipleResultsFound,
    NotFoundError,
    PersistenceError,
    RelationNotLoaded,
)


def test_persistence_error_is_alchemiq_error():
    assert issubclass(PersistenceError, AlchemiqError)


@pytest.mark.parametrize(
    "exc",
    [EngineNotConfiguredError, NotFoundError, MultipleResultsFound, RelationNotLoaded],
)
def test_subclasses_are_persistence_errors(exc):
    assert issubclass(exc, PersistenceError)
    with pytest.raises(PersistenceError):
        raise exc("boom")
