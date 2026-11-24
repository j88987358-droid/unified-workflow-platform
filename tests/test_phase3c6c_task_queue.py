from platform_core.task_queue.persistent_task_manager import (
    PersistentTaskManager
)


class FakeStorage:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value

    def delete(self, key):
        self.data.pop(key, None)


def test_task_creation():
    storage = FakeStorage()
    manager = PersistentTaskManager(storage)

    task = manager.create_task(
        task_type="test_worker",
        payload={"message": "hello"}
    )

    assert task["task_type"] == "test_worker"
    assert task["status"] == "PENDING"
    assert manager.get_task(task["task_id"]) is not None


def test_task_status_update():
    storage = FakeStorage()
    manager = PersistentTaskManager(storage)

    task = manager.create_task("test_worker")

    manager.update_status(
        task["task_id"],
        "RUNNING"
    )

    manager.update_status(
        task["task_id"],
        "SUCCESS"
    )

    result = manager.get_task(task["task_id"])

    assert result["status"] == "SUCCESS"


def test_idempotency():
    storage = FakeStorage()
    manager = PersistentTaskManager(storage)

    first = manager.create_task(
        "test_worker",
        idempotency_key="unique-test-key"
    )

    second = manager.create_task(
        "test_worker",
        idempotency_key="unique-test-key"
    )

    assert first["task_id"] == second["task_id"]


def test_priority_ordering():
    storage = FakeStorage()
    manager = PersistentTaskManager(storage)

    manager.create_task("low", priority=10)
    manager.create_task("high", priority=1)
    manager.create_task("medium", priority=5)

    tasks = manager.list_tasks()

    assert tasks[0]["priority"] == 1
    assert tasks[1]["priority"] == 5
    assert tasks[2]["priority"] == 10


def test_next_pending_task():
    storage = FakeStorage()
    manager = PersistentTaskManager(storage)

    manager.create_task("low", priority=10)
    manager.create_task("high", priority=1)

    task = manager.get_next_pending_task()

    assert task["priority"] == 1


def test_delete_task():
    storage = FakeStorage()
    manager = PersistentTaskManager(storage)

    task = manager.create_task(
        "test_worker",
        idempotency_key="delete-test"
    )

    assert manager.delete_task(task["task_id"])
    assert manager.get_task(task["task_id"]) is None
    assert manager.delete_task(task["task_id"]) is False


def test_independent_managers_share_storage():
    storage = FakeStorage()

    manager_a = PersistentTaskManager(storage)
    manager_b = PersistentTaskManager(storage)

    task = manager_a.create_task(
        "shared_worker",
        payload={"source": "manager_a"}
    )

    result = manager_b.get_task(task["task_id"])

    assert result is not None
    assert result["payload"]["source"] == "manager_a"


def test_invalid_status():
    storage = FakeStorage()
    manager = PersistentTaskManager(storage)

    task = manager.create_task("test_worker")

    try:
        manager.update_status(
            task["task_id"],
            "INVALID"
        )
        assert False, "Expected ValueError"
    except ValueError:
        pass


def test_missing_task():
    storage = FakeStorage()
    manager = PersistentTaskManager(storage)

    assert manager.get_task("missing-task") is None
