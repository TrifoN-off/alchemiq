from alchemiq.exceptions import AlchemiqError, ConfigError, ValidationError


def test_validation_error_carries_context() -> None:
    err = ValidationError(reason="not an email", field="email", value="bad", model="User")
    assert err.field == "email"
    assert err.value == "bad"
    assert err.model == "User"
    assert "email" in str(err)
    assert isinstance(err, AlchemiqError)


def test_aggregate_collects_children() -> None:
    children = [
        ValidationError(reason="r1", field="a", value=1),
        ValidationError(reason="r2", field="b", value=2),
    ]
    agg = ValidationError.aggregate(children, model="User")
    assert agg.errors == children
    assert agg.model == "User"
    assert "2" in str(agg)  # mentions count


def test_aggregate_single_child_is_passthrough() -> None:
    child = ValidationError(reason="r", field="a", value=1)
    assert ValidationError.aggregate([child], model="User") is child


def test_config_error_is_alchemiq_error() -> None:
    assert issubclass(ConfigError, AlchemiqError)
