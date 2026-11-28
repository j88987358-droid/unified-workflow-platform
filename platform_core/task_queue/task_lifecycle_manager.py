from copy import deepcopy
from datetime import datetime, timezone


class TaskLifecycleManager:

    TRANSITIONS = {
        "PENDING": {"RUNNING"},
        "RUNNING": {"SUCCESS", "FAILED"},
        "FAILED": {"RETRY", "DEAD_LETTER"},
        "RETRY": {"RUNNING", "DEAD_LETTER"},
        "SUCCESS": set(),
        "DEAD_LETTER": set(),
    }

    def __init__(self, task_manager):
        if task_manager is None:
            raise ValueError("TaskManager is required")

        self.task_manager = task_manager
        self.storage = task_manager.storage
        self.storage_key = task_manager.STORAGE_KEY

    def _now(self):
        return datetime.now(timezone.utc).isoformat()

    def _load(self):
        data = self.storage.get(self.storage_key)

        if not isinstance(data, dict):
            raise ValueError("Invalid task storage")

        return deepcopy(data)

    def _save(self, data):
        return self.storage.set(self.storage_key, data)

    def transition(self, task_id, new_status, details=None):
        if new_status not in self.TRANSITIONS:
            raise ValueError("Unknown status")

        now = self._now()

        def apply(data):
            task = data["tasks"].get(task_id)
            if task is None:
                raise KeyError(task_id)

            old_status = task["status"]
            if new_status not in self.TRANSITIONS.get(old_status, set()):
                raise ValueError(
                    f"Invalid transition: {old_status} -> {new_status}"
                )

            task["status"] = new_status
            task["updated_at"] = now
            task.setdefault("history", []).append({
                "from_status": old_status,
                "to_status": new_status,
                "timestamp": now,
                "details": deepcopy(details),
            })

            if new_status == "RUNNING":
                task["started_at"] = now
            elif new_status == "SUCCESS":
                task["completed_at"] = now
                if isinstance(details, dict) and "result" in details:
                    task["result"] = deepcopy(details["result"])
            elif new_status == "FAILED":
                task["failed_at"] = now
            elif new_status == "RETRY":
                task["retry_count"] = task.get("retry_count", 0) + 1
                task["last_retry_at"] = now
            elif new_status == "DEAD_LETTER":
                task["dead_letter_at"] = now

            return task

        return self.task_manager.mutate_tasks(apply)

    def mark_running(self, task_id):
        return self.transition(task_id, "RUNNING")

    def mark_success(self, task_id, details=None):
        return self.transition(
            task_id, "SUCCESS", details
        )

    def mark_failed(self, task_id, details=None):
        return self.transition(
            task_id, "FAILED", details
        )

    def schedule_retry(self, task_id, details=None):
        return self.transition(
            task_id, "RETRY", details
        )

    def move_to_dead_letter(self, task_id, details=None):
        return self.transition(
            task_id, "DEAD_LETTER", details
        )

    def get_history(self, task_id):
        task = self.task_manager.get_task(task_id)

        if task is None:
            raise KeyError(task_id)

        return deepcopy(task.get("history", []))
