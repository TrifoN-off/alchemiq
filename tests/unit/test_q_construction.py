from alchemiq.query import Q


def test_single_lookup_becomes_one_child():
    q = Q(age__gte=18)
    assert q.children == [("age__gte", 18)]
    assert q.connector == Q.AND
    assert q.negated is False


def test_multiple_kwargs_are_anded_children():
    q = Q(age__gte=18, name="neo")
    assert ("age__gte", 18) in q.children
    assert ("name", "neo") in q.children
    assert len(q.children) == 2
    assert q.connector == Q.AND


def test_empty_q():
    q = Q()
    assert q.children == []
    assert q.negated is False


def test_equality_and_repr_by_value():
    assert Q(a=1) == Q(a=1)
    assert Q(a=1) != Q(a=2)
    assert "a" in repr(Q(a=1))
