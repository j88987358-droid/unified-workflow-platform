def test_thread_start_failure_releases_acquired_lease(monkeypatch):
    storage = MockStorage()

    manager = ExecutionLeaseManager(
        storage,
        lease_seconds=60,
        heartbeat_interval=10,
    )

    class FailingThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise RuntimeError("Thread startup failed")

    monkeypatch.setattr(
        "platform_core.execution.lease_manager.threading.Thread",
        FailingThread,
    )

    with pytest.raises(
        RuntimeError,
        match="Thread startup failed",
    ):
        manager.start("task-123")

    actions = [call[0] for call in storage.calls]

    assert "start" in actions
    assert "release" in actions
    assert manager._started is False
