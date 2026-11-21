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

    task = manager.create_task("example.worker")

    return (
        manager,
        lifecycle,
        retry,
        clock,
        task["task_id"],
    )


def fail_task(manager, lifecycle, task_id):
    status = manager.get_task(task_id)["status"]

    if status in ("PENDING", "RETRY"):
        lifecycle.mark_running(task_id)

    elif status != "RUNNING":
        raise ValueError(
            f"Unexpected status: {status}"
        )

    lifecycle.mark_failed(
        task_id,
        "Temporary error",
    )


def test_first_retry_scheduled(setup):
    manager, lifecycle, retry, clock, task_id = setup

    fail_task(manager, lifecycle, task_id)

    task = retry.handle_failure(
        task_id,
        "Network error",
    )

    assert task["status"] == "RETRY"
    assert task["retry_count"] == 1
    assert task["backoff_seconds"] == 60


def test_second_retry_uses_exponential_backoff(setup):
    manager, lifecycle, retry, clock, task_id = setup

    fail_task(manager, lifecycle, task_id)
    retry.handle_failure(task_id)

    fail_task(manager, lifecycle, task_id)

    task = retry.handle_failure(task_id)

    assert task["retry_count"] == 2
    assert task["backoff_seconds"] == 120


def test_third_retry_uses_four_minutes(setup):
    manager, lifecycle, retry, clock, task_id = setup

    for _ in range(3):
        fail_task(manager, lifecycle, task_id)

        task = retry.handle_failure(task_id)

    assert task["status"] == "RETRY"
    assert task["retry_count"] == 3
    assert task["backoff_seconds"] == 240


def test_maximum_delay_is_capped(setup):
    manager, lifecycle, retry, clock, task_id = setup

    assert retry.calculate_delay(10) == 3600


def test_retry_not_due_immediately(setup):
    manager, lifecycle, retry, clock, task_id = setup

    fail_task(manager, lifecycle, task_id)
    retry.handle_failure(task_id)

    assert retry.get_due_retries() == []


def test_retry_becomes_due_after_delay(setup):
    manager, lifecycle, retry, clock, task_id = setup

    fail_task(manager, lifecycle, task_id)
    retry.handle_failure(task_id)

    clock.advance(60)

    due = retry.get_due_retries()

    assert len(due) == 1
    assert due[0]["task_id"] == task_id


def test_due_retry_can_be_claimed(setup):
    manager, lifecycle, retry, clock, task_id = setup

    fail_task(manager, lifecycle, task_id)
    retry.handle_failure(task_id)

    clock.advance(60)

    task = retry.claim_due_retry(task_id)

    assert task["status"] == "RUNNING"


def test_early_retry_cannot_be_claimed(setup):
    manager, lifecycle, retry, clock, task_id = setup

    fail_task(manager, lifecycle, task_id)
    retry.handle_failure(task_id)

    assert retry.claim_due_retry(task_id) is None


def test_retry_history_is_recorded(setup):
    manager, lifecycle, retry, clock, task_id = setup

    fail_task(manager, lifecycle, task_id)
    retry.handle_failure(task_id)

    history = lifecycle.get_history(task_id)

    assert any(
        item["to_status"] == "RETRY"
        for item in history
    )


def test_maximum_retries_moves_task_to_dead_letter(setup):
    manager, lifecycle, retry, clock, task_id = setup

    for _ in range(3):
        fail_task(manager, lifecycle, task_id)

        retry.handle_failure(task_id)

        if manager.get_task(task_id)["status"] == "RETRY":
            lifecycle.mark_running(task_id)

    lifecycle.mark_failed(task_id)

    task = retry.handle_failure(task_id)

    assert task["status"] == "DEAD_LETTER"


def test_retry_metadata_is_saved(setup):
    manager, lifecycle, retry, clock, task_id = setup

    fail_task(manager, lifecycle, task_id)

    task = retry.handle_failure(
        task_id,
        "Temporary API failure",
    )

    assert task["last_error"] == "Temporary API failure"
    assert task["next_retry_at"] is not None


def test_due_retry_processing(setup):
    manager, lifecycle, retry, clock, task_id = setup

    fail_task(manager, lifecycle, task_id)
    retry.handle_failure(task_id)

    clock.advance(60)

    results = retry.process_due_retries()

    assert len(results) == 1
    assert results[0]["status"] == "RUNNING"


def test_missing_task_raises_error(setup):
    manager, lifecycle, retry, clock, task_id = setup

    with pytest.raises(KeyError):
        retry.handle_failure("missing-task")


def test_non_failed_task_rejected(setup):
    manager, lifecycle, retry, clock, task_id = setup

    with pytest.raises(ValueError):
        retry.handle_failure(task_id)


def test_invalid_retry_number_rejected(setup):
    manager, lifecycle, retry, clock, task_id = setup

    with pytest.raises(ValueError):
        retry.calculate_delay(0)
