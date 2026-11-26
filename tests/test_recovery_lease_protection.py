from datetime import datetime, timezone

from platform_core.task_queue.recovery_controller import RecoveryController


class FakeStorage:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value


class FakeTaskManager:
    def __init__(self, tasks):
        self.tasks = {
            task["task_id"]: task
            for task in tasks
        }
        self.storage = FakeStorage()

    def get_task(self, task_id):
        return self.tasks.get(task_id)

    def list_tasks(self, status=None):
        tasks = list(self.tasks.values())

        if status is not None:
            tasks = [
                task for task in tasks
                if task["status"] == status
            ]

        return tasks


class FakeLifecycleManager:
    def __init__(self, task_manager):
        self.task_manager = task_manager
        self.failed_tasks = []

    def mark_failed(self, task_id, details=None):
        self.failed_tasks.append(task_id)

        task = self.task_manager.get_task(task_id)
        task["status"] = "FAILED"

        return task


class FakeRetryController:
    def __init__(self):
        self.handled_tasks = []

    def handle_failure(self, task_id, error=None):
        self.handled_tasks.append(task_id)

        return {
            "task_id": task_id,
            "handled": True,
        }


def make_controller(task):
    now = datetime(
        2026, 11, 26, 12, 0, 0,
        tzinfo=timezone.utc
    )

    task_manager = FakeTaskManager([task])
    lifecycle = FakeLifecycleManager(task_manager)
    retry = FakeRetryController()

    controller = RecoveryController(
        task_manager=task_manager,
        lifecycle_manager=lifecycle,
        retry_controller=retry,
        stale_after_seconds=900,
        clock=lambda: now,
    )

    return (
        controller,
        task_manager,
        lifecycle,
        retry,
        now,
    )


def make_stale_task(**extra):
    task = {
        "task_id": "task-001",
        "status": "RUNNING",
        "started_at": "2026-11-26T11:30:00+00:00",
        "updated_at": "2026-11-26T11:30:00+00:00",
    }

    task.update(extra)

    return task


# TEST 1:
# Active and unexpired lease must not be considered stale.

def test_active_unexpired_lease_is_not_stale():
    task = make_stale_task(
        lease_status="ACTIVE",
        lease_owner="runner-1",
        lease_expires_at="2026-11-26T12:05:00+00:00",
    )

    controller, *_ = make_controller(task)

    assert controller.is_stale(task) is False


# TEST 2:
# Expired lease should allow stale task recovery.

def test_expired_lease_allows_stale_recovery():
    task = make_stale_task(
        lease_status="ACTIVE",
        lease_owner="runner-1",
        lease_expires_at="2026-11-26T11:55:00+00:00",
    )

    controller, *_ = make_controller(task)

    assert controller.is_stale(task) is True


# TEST 3:
# Active lease without expiry must be protected.

def test_active_lease_without_expiry_is_protected():
    task = make_stale_task(
        lease_status="ACTIVE",
        lease_owner="runner-1",
    )

    controller, *_ = make_controller(task)

    assert controller.is_stale(task) is False


# TEST 4:
# Invalid lease expiry must fail safely.

def test_active_lease_with_invalid_expiry_is_protected():
    task = make_stale_task(
        lease_status="ACTIVE",
        lease_owner="runner-1",
        lease_expires_at="INVALID_DATE",
    )

    controller, *_ = make_controller(task)

    assert controller.is_stale(task) is False


# TEST 5:
# Released lease must not block recovery.

def test_released_lease_does_not_block_recovery():
    task = make_stale_task(
        lease_status="RELEASED",
    )

    controller, *_ = make_controller(task)

    assert controller.is_stale(task) is True


# TEST 6:
# Task without lease metadata should use normal stale detection.

def test_task_without_lease_can_be_recovered():
    task = make_stale_task()

    controller, *_ = make_controller(task)

    assert controller.is_stale(task) is True


# TEST 7:
# Active lease must prevent recover_task from failing the task.

def test_active_lease_prevents_recover_task():
    task = make_stale_task(
        lease_status="ACTIVE",
        lease_owner="runner-1",
        lease_expires_at="2026-11-26T12:05:00+00:00",
    )

    (
        controller,
        task_manager,
        lifecycle,
        retry,
        _,
    ) = make_controller(task)

    result = controller.recover_task("task-001")

    assert result is None

    assert (
        task_manager.get_task("task-001")["status"]
        == "RUNNING"
    )

    assert lifecycle.failed_tasks == []
    assert retry.handled_tasks == []
