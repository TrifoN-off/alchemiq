from alchemiq.outbox.publisher import Publisher, PublishError, TransientPublishError


def test_transient_is_a_publish_error():
    assert issubclass(TransientPublishError, PublishError)


def test_publisher_is_runtime_checkable():
    class Good:
        async def publish(self, message): ...

    class Bad:
        pass

    assert isinstance(Good(), Publisher)
    assert not isinstance(Bad(), Publisher)
