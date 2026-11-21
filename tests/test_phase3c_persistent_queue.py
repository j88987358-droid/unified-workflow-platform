import pytest

from platform_core.storage.memory_storage import InMemoryStorage
from platform_core.task_queue.persistent_task_manager import (
    PersistentTaskManager,
)


@pytest.fixture
def storage():
    return InMemoryStorage()


@pytest.fixture
def manager(storage):
    return PersistentTaskManager(storage)


def test_create_task(manager):
    task = manager.create_task("example.worker", {"value": 10})

    assert task["task_type"] == "example.worker"
    assert task["status"] == "PENDING"


def test_task_is_retrievable(manager):
    task = manager.create_task("example.worker")

    saved = manager.get_task(task["task_id"])

    assert saved["task_id"] == task["task_id"]


def test_storage_survives_manager_recreation(storage):
    first = PersistentTaskManager(storage)

    task = first.create_task(
        "example.worker",
        {"value": 25},
    )

    second = PersistentTaskManager(storage)

    saved = second.get_task(task["task_id"])

    assert saved is not None
    assert saved["payload"]["value"] == 25


def test_status_persistence(storage):
    first = PersistentTaskManager(storage)

    task = first.create_task("example.worker")

    first.update_status(task["task_id"], "SUCCESS")

    second = PersistentTaskManager(storage)

    saved = second.get_task(task["task_id"])

    assert saved["status"] == "SUCCESS"


def test_duplicate_idempotency_key(manager):
    first = manager.create_task(
        "example.worker",
        {"value": 1},
        idempotency_key="job-001",
    )

    second = manager.create_task(
        "example.worker",
        {"value": 2},
        idempotency_key="job-001",
    )

    assert first["task_id"] == second["task_id"]
    assert len(manager.list_tasks()) == 1


def test_priority_order(manager):
    manager.create_task("low", priority=10)
    manager.create_task("high", priority=1)

    tasks = manager.list_tasks()

    assert tasks[0]["task_type"] == "high"


def test_pending_task_retrieval(manager):
    manager.create_task("first", priority=5)
    manager.create_task("second", priority=1)

    task = manager.get_next_pending_task()

    assert task["task_type"] == "second"


def test_invalid_status_rejected(manager):
    task = manager.create_task("example.worker")

    with pytest.raises(ValueError):
        manager.update_status(
            task["task_id"],
            "UNKNOWN",
        )


def test_missing_task_raises_key_error(manager):
    with pytest.raises(KeyError):
        manager.update_status("missing-id", "SUCCESS")


def test_delete_task(manager):
    task = manager.create_task("example.worker")

    assert manager.delete_task(task["task_id"]) is True
    assert manager.get_task(task["task_id"]) is None
