import pytest

from alchemiq.exceptions import (
    AlchemiqError,
    DeserializationError,
    DisallowedFieldError,
    QueryError,
    UnknownFieldError,
    UnknownOperatorError,
)


def test_query_error_is_alchemiq_error():
    assert issubclass(QueryError, AlchemiqError)


@pytest.mark.parametrize(
    "exc",
    [UnknownFieldError, UnknownOperatorError, DeserializationError, DisallowedFieldError],
)
def test_subclasses_are_query_errors(exc):
    assert issubclass(exc, QueryError)
    with pytest.raises(QueryError):
        raise exc("boom")
