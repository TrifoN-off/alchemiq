import alchemiq


def test_query_symbols_exported():
    assert hasattr(alchemiq, "Q")
    assert hasattr(alchemiq, "QuerySet")
    assert hasattr(alchemiq, "ForeignKey")


def test_all_lists_new_symbols():
    for name in ("Q", "QuerySet", "ForeignKey"):
        assert name in alchemiq.__all__
