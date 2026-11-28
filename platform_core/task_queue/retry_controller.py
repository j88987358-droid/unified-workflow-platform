from datetime import datetime, timezone, timedelta

from platform_core.task_queue.task_lifecycle_manager import (
    TaskLifecycleManager,
)


class RetryController:

    def __init__(
        self,
        task_manager,
        max_retries=3,
        base_delay_seconds=60,
        max_delay_seconds=3600,
        clock=None,
    ):
        if task_manager is None:
            raise ValueError("TaskManager is required")

        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")

        if base_delay_seconds <= 0:
            raise ValueError("base delay must be positive")

        if max_delay_seconds <= 0:
            raise ValueError("max delay must be positive")

        self.task_manager = task_manager
        self.lifecycle = TaskLifecycleManager(task_manager)
        self.storage = task_manager.storage
        self.storage_key = task_manager.STORAGE_KEY

        self.max_retries = max_retries
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds

        self.clock = clock or (
            lambda: datetime.now(timezone.utc)
        )

    def _now(self):
        value = self.clock()

        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    def _load(self):
        data = self.storage.get(self.storage_key)

        if not isinstance(data, dict):
            raise ValueError("Invalid task storage")

        return data

    def _save(self, data):
        return self.storage.set(self.storage_key, data)

    def calculate_delay(self, retry_number):
        if retry_number < 1:
            raise ValueError(
                "retry_number must be positive"
            )

        delay = self.base_delay_seconds * (
            2 ** (retry_number - 1)
        )

        return min(delay, self.max_delay_seconds)

    def handle_failure(self, task_id, error=None):
        task = self.task_manager.get_task(task_id)

        if task is None:
            raise KeyError(task_id)

        if task["status"] != "FAILED":
            raise ValueError(
                "Task must be FAILED before retry handling"
            )

        current_retries = task.get("retry_count", 0)

        if current_retries >= self.max_retries:
            return self.lifecycle.move_to_dead_letter(
                task_id,
                details={
                    "reason": "Maximum retries exceeded",
                    "error": error,
                },
            )

        updated = self.lifecycle.schedule_retry(
            task_id,
            details={
                "error": error,
            },
        )

        retry_number = updated["retry_count"]
        delay = self.calculate_delay(retry_number)

        now = self._now()
        next_retry = now + timedelta(seconds=delay)

        def save_retry_metadata(data):
            saved_task = data["tasks"].get(task_id)
            if saved_task is None:
                raise KeyError(task_id)
            saved_task["last_error"] = error
            saved_task["backoff_seconds"] = delay
            saved_task["next_retry_at"] = next_retry.isoformat()
            return saved_task

        self.task_manager.mutate_tasks(save_retry_metadata)
        return self.task_manager.get_task(task_id)

    def get_due_retries(self):
        now = self._now()

        tasks = self.task_manager.list_tasks(
            status="RETRY"
        )

        due = []

        for task in tasks:
            retry_at = task.get("next_retry_at")

            if not retry_at:
                continue

            retry_time = datetime.fromisoformat(
                retry_at
            )

            if retry_time.tzinfo is None:
                retry_time = retry_time.replace(
                    tzinfo=timezone.utc
                )

            if retry_time <= now:
                due.append(task)

        return due

    def claim_due_retry(self, task_id):
        due_ids = {
            task["task_id"]
            for task in self.get_due_retries()
        }

        if task_id not in due_ids:
            return None

        return self.lifecycle.mark_running(task_id)

    def process_due_retries(self):
        results = []

        for task in self.get_due_retries():
            claimed = self.claim_due_retry(
                task["task_id"]
            )

            if claimed is not None:
                results.append(claimed)

        return results
