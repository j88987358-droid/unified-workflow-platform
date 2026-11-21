from datetime import datetime, timezone

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

from platform_core.plugin_system.worker_manager import (
    WorkerManager,
)

from platform_core.contracts.base_worker import BaseWorker

from platform_core.execution.execution_engine import (
    ExecutionEngine,
)


class FakeClock:

    def __init__(self):
        self.current = datetime(
            2026, 1, 1, 12, 0, 0,
            tzinfo=timezone.utc,
        )

    def __call__(self):
        return self.current


class DemoWorker(BaseWorker):

    name = "demo.worker"

    def initialize(self, context):
        self.initialized = True

    def execute(self, task):
        return {
            "message": "Task executed",
            "task_id": task["task_id"],
        }

    def health_check(self):
        return True


class FailingWorker(BaseWorker):

    name = "failing.worker"

    def initialize(self, context):
        self.initialized = True

    def execute(self, task):
        raise RuntimeError("Temporary worker failure")

    def health_check(self):
        return True


@pytest.fixture
def setup():
    storage = InMemoryStorage()

    task_manager = PersistentTaskManager(storage)

    lifecycle = TaskLifecycleManager(task_manager)

    clock = FakeClock()

    retry = RetryController(
        task_manager,
        max_retries=3,
        base_delay_seconds=60,
        max_delay_seconds=3600,
        clock=clock,
    )

    worker_manager = WorkerManager()

    worker_manager.register(
        "demo.worker",
        DemoWorker(),
    )

    worker_manager.register(
        "failing.worker",
        FailingWorker(),
    )

    engine = ExecutionEngine(
        task_manager,
        lifecycle,
        retry,
        worker_manager,
    )

    return (
        task_manager,
        lifecycle,
        retry,
        worker_manager,
        engine,
    )


def test_successful_worker_execution(setup):
    manager, lifecycle, retry, workers, engine = setup

    task = manager.create_task(
        "demo.worker",
        payload={
            "worker_id": "demo.worker",
        },
    )

    result = engine.execute_task(task["task_id"])

    assert result["status"] == "SUCCESS"


def test_worker_is_started_automatically(setup):
    manager, lifecycle, retry, workers, engine = setup

    task = manager.create_task(
        "demo.worker",
        payload={
            "worker_id": "demo.worker",
        },
    )

    engine.execute_task(task["task_id"])

    assert workers.status["demo.worker"] == "READY"


def test_success_result_is_saved(setup):
    manager, lifecycle, retry, workers, engine = setup

    task = manager.create_task(
        "demo.worker",
        payload={
            "worker_id": "demo.worker",
        },
    )

    result = engine.execute_task(task["task_id"])

    history = lifecycle.get_history(task["task_id"])

    assert result["status"] == "SUCCESS"

    assert history[-1]["to_status"] == "SUCCESS"


def test_worker_failure_schedules_retry(setup):
    manager, lifecycle, retry, workers, engine = setup

    task = manager.create_task(
        "failing.worker",
        payload={
            "worker_id": "failing.worker",
        },
    )

    result = engine.execute_task(task["task_id"])

    assert result["status"] == "RETRY"

    assert result["retry_count"] == 1


def test_retry_metadata_saved_after_failure(setup):
    manager, lifecycle, retry, workers, engine = setup

    task = manager.create_task(
        "failing.worker",
        payload={
            "worker_id": "failing.worker",
        },
    )

    result = engine.execute_task(task["task_id"])

    assert result["last_error"] is not None

    assert result["next_retry_at"] is not None


def test_retry_worker_execution(setup):
    manager, lifecycle, retry, workers, engine = setup

    task = manager.create_task(
        "demo.worker",
        payload={
            "worker_id": "demo.worker",
        },
    )

    lifecycle.mark_running(task["task_id"])

    lifecycle.mark_failed(
        task["task_id"],
        "Temporary failure",
    )

    retry.handle_failure(task["task_id"])

    retry.clock.current = (
        datetime(2026, 1, 1, 12, 2, 0,
                 tzinfo=timezone.utc)
    )

    results = engine.process_due_retries()

    assert len(results) == 1

    assert results[0]["status"] == "SUCCESS"


def test_retry_worker_failure_is_rescheduled(setup):
    manager, lifecycle, retry, workers, engine = setup

    task = manager.create_task(
        "failing.worker",
        payload={
            "worker_id": "failing.worker",
        },
    )

    engine.execute_task(task["task_id"])

    retry.clock.current = (
        datetime(2026, 1, 1, 12, 2, 0,
                 tzinfo=timezone.utc)
    )

    results = engine.process_due_retries()

    assert len(results) == 1

    assert results[0]["status"] == "RETRY"

    assert results[0]["retry_count"] == 2


def test_unknown_worker_goes_to_retry(setup):
    manager, lifecycle, retry, workers, engine = setup

    task = manager.create_task(
        "unknown.worker",
        payload={
            "worker_id": "unknown.worker",
        },
    )

    result = engine.execute_task(task["task_id"])

    assert result["status"] == "RETRY"


def test_missing_task_raises_error(setup):
    manager, lifecycle, retry, workers, engine = setup

    with pytest.raises(KeyError):
        engine.execute_task("missing-task")


def test_pending_queue_processing(setup):
    manager, lifecycle, retry, workers, engine = setup

    manager.create_task(
        "demo.worker",
        payload={
            "worker_id": "demo.worker",
        },
    )

    manager.create_task(
        "demo.worker",
        payload={
            "worker_id": "demo.worker",
        },
    )

    results = engine.process_pending_tasks()

    assert len(results) == 2

    assert all(
        task["status"] == "SUCCESS"
        for task in results
    )


def test_max_task_limit(setup):
    manager, lifecycle, retry, workers, engine = setup

    for _ in range(3):
        manager.create_task(
            "demo.worker",
            payload={
                "worker_id": "demo.worker",
            },
        )

    results = engine.process_pending_tasks(
        max_tasks=2
    )

    assert len(results) == 2


def test_invalid_max_task_limit(setup):
    manager, lifecycle, retry, workers, engine = setup

    with pytest.raises(ValueError):
        engine.process_pending_tasks(max_tasks=0)


def test_worker_failure_does_not_mark_success(setup):
    manager, lifecycle, retry, workers, engine = setup

    task = manager.create_task(
        "failing.worker",
        payload={
            "worker_id": "failing.worker",
        },
    )

    result = engine.execute_task(task["task_id"])

    assert result["status"] != "SUCCESS"


def test_successful_tasks_are_removed_from_pending(setup):
    manager, lifecycle, retry, workers, engine = setup

    task = manager.create_task(
        "demo.worker",
        payload={
            "worker_id": "demo.worker",
        },
    )

    engine.execute_task(task["task_id"])

    assert manager.get_next_pending_task() is None
