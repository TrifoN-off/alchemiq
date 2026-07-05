from alchemiq.query import Q


def test_and_nests_as_connector_node():
    combined = Q(a=1) & Q(b=2)
    assert combined.connector == Q.AND
    assert combined.children == [Q(a=1), Q(b=2)]


def test_or_nests_as_connector_node():
    combined = Q(a=1) | Q(b=2)
    assert combined.connector == Q.OR
    assert combined.children == [Q(a=1), Q(b=2)]


def test_invert_sets_negated_on_copy():
    base = Q(a=1)
    negated = ~base
    assert negated.negated is True
    assert base.negated is False  # original untouched (immutability)
    assert negated.children == base.children


def test_combinators_do_not_mutate_operands():
    a, b = Q(a=1), Q(b=2)
    _ = a & b
    assert a.children == [("a", 1)]
    assert b.children == [("b", 2)]
