from datetime import datetime, timezone, timedelta

import pytest

from platform_core.storage.memory_storage import (
    InMemoryStorage,
)

from platform_core.task_queue.persistent_task_manager import (
    PersistentTaskManager,
)

from platform_core.task_queue.task_lifecycle_manager import (
    TaskLifecycleManager,
)

from platform_core.task_queue.retry_controller import (
    RetryController,
)

from platform_core.task_queue.recovery_controller import (
    RecoveryController,
)


class FakeClock:

    def __init__(self):
        self.current = datetime(
            2026, 1, 1, 12, 0, 0,
            tzinfo=timezone.utc,
        )

    def __call__(self):
        return self.current

    def advance(self, seconds):
        self.current += timedelta(seconds=seconds)


@pytest.fixture
def setup():
    storage = InMemoryStorage()

    manager = PersistentTaskManager(storage)

    lifecycle = TaskLifecycleManager(manager)

    clock = FakeClock()

    retry = RetryController(
        manager,
        max_retries=3,
        base_delay_seconds=60,
        max_delay_seconds=3600,
        clock=clock,
    )

    recovery = RecoveryController(
        manager,
        lifecycle,
        retry,
        stale_after_seconds=300,
        clock=clock,
    )

    return (
        storage,
        manager,
        lifecycle,
        retry,
        recovery,
        clock,
    )


def make_running_task(manager, lifecycle):
    task = manager.create_task("example.worker")

    lifecycle.mark_running(task["task_id"])

    return task["task_id"]


def make_stale(manager, task_id, clock, seconds=600):
    data = manager.storage.get(
        manager.STORAGE_KEY
    )

    old_time = (
        clock.current - timedelta(seconds=seconds)
    ).isoformat()

    data["tasks"][task_id]["started_at"] = old_time

    manager.storage.set(
        manager.STORAGE_KEY,
        data,
    )


def test_fresh_running_task_is_not_stale(setup):
    storage, manager, lifecycle, retry, recovery, clock = setup

    task_id = make_running_task(manager, lifecycle)

    assert recovery.is_stale(
        manager.get_task(task_id)
    ) is False


def test_old_running_task_is_stale(setup):
    storage, manager, lifecycle, retry, recovery, clock = setup

    task_id = make_running_task(manager, lifecycle)

    make_stale(manager, task_id, clock)

    assert recovery.is_stale(
        manager.get_task(task_id)
    ) is True


def test_stale_task_is_detected(setup):
    storage, manager, lifecycle, retry, recovery, clock = setup

    task_id = make_running_task(manager, lifecycle)

    make_stale(manager, task_id, clock)

    tasks = recovery.find_stale_tasks()

    assert len(tasks) == 1
    assert tasks[0]["task_id"] == task_id


def test_stale_task_is_recovered(setup):
    storage, manager, lifecycle, retry, recovery, clock = setup

    task_id = make_running_task(manager, lifecycle)

    make_stale(manager, task_id, clock)

    result = recovery.recover_task(task_id)

    assert result["status"] == "RETRY"
    assert result["retry_count"] == 1


def test_fresh_task_is_not_recovered(setup):
    storage, manager, lifecycle, retry, recovery, clock = setup

    task_id = make_running_task(manager, lifecycle)

    result = recovery.recover_task(task_id)

    assert result is None

    assert manager.get_task(
        task_id
    )["status"] == "RUNNING"


def test_recovery_history_is_saved(setup):
    storage, manager, lifecycle, retry, recovery, clock = setup

    task_id = make_running_task(manager, lifecycle)

    make_stale(manager, task_id, clock)

    recovery.recover_task(task_id)

    history = recovery.get_recovery_history(
        task_id
    )

    event_types = [
        event["event_type"]
        for event in history
    ]

    assert "RECOVERY_STARTED" in event_types
    assert "RECOVERY_COMPLETED" in event_types


def test_recovery_report(setup):
    storage, manager, lifecycle, retry, recovery, clock = setup

    task_id = make_running_task(manager, lifecycle)

    make_stale(manager, task_id, clock)

    recovery.recover_task(task_id)

    report = recovery.recovery_report()

    assert report["total_recoveries"] == 1
    assert report["retry_scheduled"] == 1


def test_max_retry_task_goes_to_dead_letter(setup):
    storage, manager, lifecycle, retry, recovery, clock = setup

    task_id = make_running_task(manager, lifecycle)

    data = storage.get(manager.STORAGE_KEY)

    data["tasks"][task_id]["retry_count"] = 3

    storage.set(manager.STORAGE_KEY, data)

    make_stale(manager, task_id, clock)

    result = recovery.recover_task(task_id)

    assert result["status"] == "DEAD_LETTER"


def test_multiple_stale_tasks_recovered(setup):
    storage, manager, lifecycle, retry, recovery, clock = setup

    ids = []

    for _ in range(3):
        task_id = make_running_task(
            manager,
            lifecycle,
        )

        make_stale(manager, task_id, clock)

        ids.append(task_id)

    results = recovery.recover_stale_tasks()

    assert len(results) == 3

    assert all(
        task["status"] == "RETRY"
        for task in results
    )


def test_recovery_limit(setup):
    storage, manager, lifecycle, retry, recovery, clock = setup

    for _ in range(3):
        task_id = make_running_task(
            manager,
            lifecycle,
        )

        make_stale(manager, task_id, clock)

    results = recovery.recover_stale_tasks(
        limit=2
    )

    assert len(results) == 2


def test_already_recovered_task_is_ignored(setup):
    storage, manager, lifecycle, retry, recovery, clock = setup

    task_id = make_running_task(manager, lifecycle)

    make_stale(manager, task_id, clock)

    first = recovery.recover_task(task_id)

    second = recovery.recover_task(task_id)

    assert first["status"] == "RETRY"
    assert second is None


def test_missing_task_raises_error(setup):
    storage, manager, lifecycle, retry, recovery, clock = setup

    with pytest.raises(KeyError):
        recovery.recover_task("missing-task")


def test_invalid_recovery_limit(setup):
    storage, manager, lifecycle, retry, recovery, clock = setup

    with pytest.raises(ValueError):
        recovery.find_stale_tasks(limit=0)


def test_invalid_stale_timeout(setup):
    storage, manager, lifecycle, retry, recovery, clock = setup

    with pytest.raises(ValueError):
        RecoveryController(
            manager,
            lifecycle,
            retry,
            stale_after_seconds=0,
        )


def test_non_running_task_is_ignored(setup):
    storage, manager, lifecycle, retry, recovery, clock = setup

    task = manager.create_task("example.worker")

    assert recovery.recover_task(
        task["task_id"]
    ) is None


def test_recovery_events_are_persisted_in_storage(setup):
    storage, manager, lifecycle, retry, recovery, clock = setup

    task_id = make_running_task(manager, lifecycle)

    make_stale(manager, task_id, clock)

    recovery.recover_task(task_id)

    events = storage.get(
        RecoveryController.RECOVERY_STORAGE_KEY
    )

    assert len(events) == 2
