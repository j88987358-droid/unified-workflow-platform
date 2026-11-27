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


def test_initialization_creates_storage_schema(storage):
    manager = PersistentTaskManager(storage)

    data = storage.get(manager.STORAGE_KEY)

    assert isinstance(data, dict)
    assert "tasks" in data
    assert "idempotency" in data


def test_create_task_persists_task(manager, storage):
    task = manager.create_task(
        task_type="demo_worker",
        payload={"message": "hello"},
        priority=1,
    )

    saved = storage.get(manager.STORAGE_KEY)

    assert task["task_id"] in saved["tasks"]
    assert task["status"] == "PENDING"
    assert task["priority"] == 1
    assert task["payload"]["message"] == "hello"


def test_task_survives_manager_reinitialization(storage):
    manager1 = PersistentTaskManager(storage)

    task = manager1.create_task(
        task_type="demo_worker",
        payload={"value": 123},
    )

    manager2 = PersistentTaskManager(storage)

    restored = manager2.get_task(task["task_id"])

    assert restored is not None
    assert restored["task_id"] == task["task_id"]
    assert restored["payload"]["value"] == 123


def test_get_missing_task_returns_none(manager):
    assert manager.get_task("missing-task") is None


def test_update_task_status(manager):
    task = manager.create_task("demo_worker")

    updated = manager.update_status(
        task["task_id"],
        "RUNNING",
    )

    assert updated["status"] == "RUNNING"

    saved = manager.get_task(task["task_id"])

    assert saved["status"] == "RUNNING"


def test_invalid_status_is_rejected(manager):
    task = manager.create_task("demo_worker")

    with pytest.raises(ValueError, match="Invalid task status"):
        manager.update_status(
            task["task_id"],
            "UNKNOWN",
        )


def test_list_tasks_filters_and_sorts_by_priority(manager):
    task1 = manager.create_task(
        "worker_a",
        priority=5,
    )

    task2 = manager.create_task(
        "worker_b",
        priority=1,
    )

    task3 = manager.create_task(
        "worker_c",
        priority=3,
    )

    tasks = manager.list_tasks()

    priorities = [
        task["priority"]
        for task in tasks
    ]

    assert priorities == [1, 3, 5]

    manager.update_status(
        task2["task_id"],
        "RUNNING",
    )

    pending = manager.list_tasks(
        status="PENDING"
    )

    pending_ids = [
        task["task_id"]
        for task in pending
    ]

    assert task1["task_id"] in pending_ids
    assert task3["task_id"] in pending_ids
    assert task2["task_id"] not in pending_ids


def test_get_next_pending_task_returns_highest_priority(manager):
    manager.create_task(
        "worker_a",
        priority=5,
    )

    highest = manager.create_task(
        "worker_b",
        priority=1,
    )

    manager.create_task(
        "worker_c",
        priority=3,
    )

    next_task = manager.get_next_pending_task()

    assert next_task["task_id"] == highest["task_id"]


def test_get_next_pending_task_returns_none_when_empty(manager):
    assert manager.get_next_pending_task() is None


def test_idempotency_prevents_duplicate_tasks(manager):
    first = manager.create_task(
        task_type="demo_worker",
        payload={"message": "hello"},
        idempotency_key="request-001",
    )

    second = manager.create_task(
        task_type="demo_worker",
        payload={"message": "different"},
        idempotency_key="request-001",
    )

    assert first["task_id"] == second["task_id"]

    tasks = manager.list_tasks()

    assert len(tasks) == 1


def test_delete_task_removes_task_and_idempotency_key(manager):
    task = manager.create_task(
        task_type="demo_worker",
        idempotency_key="request-delete",
    )

    deleted = manager.delete_task(
        task["task_id"]
    )

    assert deleted is True
    assert manager.get_task(task["task_id"]) is None

    # The same idempotency key can be used again
    new_task = manager.create_task(
        task_type="demo_worker",
        idempotency_key="request-delete",
    )

    assert new_task["task_id"] != task["task_id"]


def test_delete_missing_task_returns_false(manager):
    assert manager.delete_task("missing-task") is False


def test_returned_task_does_not_modify_stored_payload(manager):
    task = manager.create_task(
        task_type="demo_worker",
        payload={
            "nested": {
                "value": 100
            }
        },
    )

    task["payload"]["nested"]["value"] = 999

    saved = manager.get_task(task["task_id"])

    assert saved["payload"]["nested"]["value"] == 100
