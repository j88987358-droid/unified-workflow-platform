import pytest

from platform_core.storage.memory_storage import InMemoryStorage
from platform_core.task_queue.persistent_task_manager import (
    PersistentTaskManager,
)
from platform_core.task_queue.task_lifecycle_manager import (
    TaskLifecycleManager,
)


@pytest.fixture
def setup():
    storage = InMemoryStorage()
    manager = PersistentTaskManager(storage)
    lifecycle = TaskLifecycleManager(manager)

    task = manager.create_task("example.worker")

    return manager, lifecycle, task["task_id"]


def test_pending_to_running(setup):
    manager, lifecycle, task_id = setup

    task = lifecycle.mark_running(task_id)

    assert task["status"] == "RUNNING"
    assert task["started_at"] is not None


def test_running_to_success(setup):
    manager, lifecycle, task_id = setup

    lifecycle.mark_running(task_id)
    task = lifecycle.mark_success(task_id)

    assert task["status"] == "SUCCESS"
    assert task["completed_at"] is not None


def test_running_to_failed(setup):
    manager, lifecycle, task_id = setup

    lifecycle.mark_running(task_id)
    task = lifecycle.mark_failed(task_id, "Test error")

    assert task["status"] == "FAILED"
    assert task["failed_at"] is not None


def test_failed_to_retry(setup):
    manager, lifecycle, task_id = setup

    lifecycle.mark_running(task_id)
    lifecycle.mark_failed(task_id)
    task = lifecycle.schedule_retry(task_id)

    assert task["status"] == "RETRY"
    assert task["retry_count"] == 1


def test_retry_to_running(setup):
    manager, lifecycle, task_id = setup

    lifecycle.mark_running(task_id)
    lifecycle.mark_failed(task_id)
    lifecycle.schedule_retry(task_id)

    task = lifecycle.mark_running(task_id)

    assert task["status"] == "RUNNING"


def test_failed_to_dead_letter(setup):
    manager, lifecycle, task_id = setup

    lifecycle.mark_running(task_id)
    lifecycle.mark_failed(task_id)

    task = lifecycle.move_to_dead_letter(task_id)

    assert task["status"] == "DEAD_LETTER"
    assert task["dead_letter_at"] is not None


def test_invalid_transition_rejected(setup):
    manager, lifecycle, task_id = setup

    with pytest.raises(ValueError):
        lifecycle.mark_success(task_id)


def test_success_is_terminal(setup):
    manager, lifecycle, task_id = setup

    lifecycle.mark_running(task_id)
    lifecycle.mark_success(task_id)

    with pytest.raises(ValueError):
        lifecycle.mark_running(task_id)


def test_history_tracking(setup):
    manager, lifecycle, task_id = setup

    lifecycle.mark_running(task_id)
    lifecycle.mark_success(task_id)

    history = lifecycle.get_history(task_id)

    assert len(history) == 2
    assert history[0]["to_status"] == "RUNNING"
    assert history[1]["to_status"] == "SUCCESS"


def test_history_persists_after_manager_recreation(setup):
    manager, lifecycle, task_id = setup

    lifecycle.mark_running(task_id)
    lifecycle.mark_failed(task_id)

    new_manager = PersistentTaskManager(manager.storage)
    new_lifecycle = TaskLifecycleManager(new_manager)

    history = new_lifecycle.get_history(task_id)

    assert len(history) == 2
    assert history[-1]["to_status"] == "FAILED"


def test_missing_task_rejected(setup):
    manager, lifecycle, task_id = setup

    with pytest.raises(KeyError):
        lifecycle.mark_running("missing-task")


def test_retry_count_increments(setup):
    manager, lifecycle, task_id = setup

    lifecycle.mark_running(task_id)
    lifecycle.mark_failed(task_id)
    lifecycle.schedule_retry(task_id)
    lifecycle.mark_running(task_id)
    lifecycle.mark_failed(task_id)
    task = lifecycle.schedule_retry(task_id)

    assert task["retry_count"] == 2
