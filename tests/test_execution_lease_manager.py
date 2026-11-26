import threading
import time

import pytest

from platform_core.execution.lease_manager import (
    ExecutionLeaseManager,
)


class MockStorage:

    def __init__(self):
        self.calls = []
        self.heartbeat_event = threading.Event()
        self.lease_valid = True
        self.heartbeat_error = None

    def lease_start(self, task_id, owner, lease_seconds=180):
        self.calls.append(("start", task_id, owner))
        return {"success": True}

    def lease_heartbeat(
        self, task_id, owner, lease_seconds=180
    ):
        self.calls.append(("heartbeat", task_id, owner))

        if self.heartbeat_error:
            raise self.heartbeat_error

        self.heartbeat_event.set()
        return {"success": True}

    def lease_check(self, task_id, owner, lease_seconds=180):
        self.calls.append(("check", task_id, owner))
        return {"success": True, "valid": self.lease_valid}

    def lease_release(self, task_id, owner, lease_seconds=180):
        self.calls.append(("release", task_id, owner))
        return {"success": True}


def test_initialization_requires_storage():
    with pytest.raises(ValueError):
        ExecutionLeaseManager(None)


def test_invalid_lease_duration_rejected():
    with pytest.raises(ValueError):
        ExecutionLeaseManager(
            MockStorage(),
            lease_seconds=20
        )


def test_invalid_heartbeat_interval_rejected():
    with pytest.raises(ValueError):
        ExecutionLeaseManager(
            MockStorage(),
            lease_seconds=60,
            heartbeat_interval=60
        )


def test_start_acquires_lease():
    storage = MockStorage()

    manager = ExecutionLeaseManager(
        storage,
        heartbeat_interval=10
    )

    result = manager.start("task-123")

    assert result["success"] is True
    assert storage.calls[0][0] == "start"

    manager.stop()


def test_heartbeat_runs_in_background():
    storage = MockStorage()

    manager = ExecutionLeaseManager(
        storage,
        lease_seconds=30,
        heartbeat_interval=0.1
    )

    manager.start("task-123")

    try:
        assert storage.heartbeat_event.wait(timeout=2)
    finally:
        manager.stop()

    assert any(
        call[0] == "heartbeat"
        for call in storage.calls
    )


def test_check_valid_lease():
    storage = MockStorage()

    manager = ExecutionLeaseManager(
        storage,
        heartbeat_interval=10
    )

    manager.start("task-123")

    try:
        assert manager.check() is True
    finally:
        manager.stop()


def test_check_rejects_invalid_lease():
    storage = MockStorage()
    storage.lease_valid = False

    manager = ExecutionLeaseManager(
        storage,
        heartbeat_interval=10
    )

    manager.start("task-123")

    try:
        with pytest.raises(RuntimeError):
            manager.check()
    finally:
        manager.stop()


def test_release_stops_heartbeat_and_releases_lease():
    storage = MockStorage()

    manager = ExecutionLeaseManager(
        storage,
        heartbeat_interval=10
    )

    manager.start("task-123")
    result = manager.release()

    assert result["success"] is True

    actions = [call[0] for call in storage.calls]

    assert "start" in actions
    assert "release" in actions


def test_heartbeat_failure_is_reported():
    storage = MockStorage()
    storage.heartbeat_error = RuntimeError("Network failure")

    manager = ExecutionLeaseManager(
        storage,
        lease_seconds=30,
        heartbeat_interval=0.1
    )

    manager.start("task-123")

    assert manager._stop_event.wait(timeout=2)

    with pytest.raises(RuntimeError, match="heartbeat failed"):
        manager.stop()
