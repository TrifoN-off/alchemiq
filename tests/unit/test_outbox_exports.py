def test_relay_surface_is_exported_from_top_level():
    from alchemiq import (  # noqa: F401
        OutboxMessage,
        Publisher,
        PublishError,
        Relay,
        TransientPublishError,
    )

    assert issubclass(TransientPublishError, PublishError)
    assert all(
        name in __import__("alchemiq").__all__
        for name in ("Relay", "Publisher", "OutboxMessage", "PublishError", "TransientPublishError")
    )


def test_importing_alchemiq_does_not_require_the_outbox_extra():
    import subprocess
    import sys

    # Fresh interpreter: pytest imports test_outbox_taskiq.py at COLLECTION time
    # (pulling alchemiq.outbox.taskiq into sys.modules), so an in-process check is
    # polluted. A subprocess proves `import alchemiq` alone never imports the adapter.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import alchemiq, sys; "
            "assert 'alchemiq.outbox.taskiq' not in sys.modules, "
            "'import alchemiq pulled in the taskiq adapter'",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
