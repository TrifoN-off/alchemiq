import alchemiq


def test_core_surface_exported():
    for name in (
        "configure",
        "dispose",
        "create_all",
        "drop_all",
        "UnitOfWork",
        "Repository",
        "Page",
        "Model",
        "Field",
        "ForeignKey",
        "Q",
        "QuerySet",
    ):
        assert hasattr(alchemiq, name), name
        assert name in alchemiq.__all__, name
