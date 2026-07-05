import pytest

from alchemiq.types import Nothing, Some


def test_some_match_calls_some_branch_with_unwrapped_value():
    assert Some(5).match(some=lambda v: v * 2, nothing=lambda: -1) == 10


def test_nothing_match_calls_nothing_branch():
    assert Nothing.match(some=lambda v: v * 2, nothing=lambda: -1) == -1


def test_match_branches_may_return_different_types():
    assert Some("ab").match(some=len, nothing=lambda: "none") == 2
    assert Nothing.match(some=len, nothing=lambda: "none") == "none"


def test_some_branch_receives_the_value():
    seen: list[int] = []
    Some(42).match(some=seen.append, nothing=lambda: None)
    assert seen == [42]


def test_match_rejects_positional_args():
    with pytest.raises(TypeError):
        Some(1).match(lambda v: v, lambda: 0)
