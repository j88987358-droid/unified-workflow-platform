from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4


class PersistentTaskManager:

    STORAGE_KEY = "task_queue:tasks"

    ALLOWED_STATUSES = {
        "PENDING",
        "RUNNING",
        "SUCCESS",
        "FAILED",
        "RETRY",
        "DEAD_LETTER",
    }

    def __init__(self, storage):
        if storage is None:
            raise ValueError("Storage is required")

        self.storage = storage

        if self.storage.get(self.STORAGE_KEY) is None:
            self.storage.set(self.STORAGE_KEY, {
                "tasks": {},
                "idempotency": {},
            })

    def _load(self):
        data = self.storage.get(self.STORAGE_KEY)

        if not isinstance(data, dict):
            return {
                "tasks": {},
                "idempotency": {},
            }

        return deepcopy(data)

    def _save(self, data):
        return self.storage.set(
            self.STORAGE_KEY,
            data,
        )

    def create_task(
        self,
        task_type,
        payload=None,
        priority=5,
        idempotency_key=None,
    ):
        if not isinstance(task_type, str) or not task_type:
            raise ValueError("task_type is required")

        if not isinstance(priority, int):
            raise ValueError("priority must be an integer")

        data = self._load()

        if idempotency_key is not None:
            existing_id = data["idempotency"].get(
                idempotency_key
            )

            if existing_id:
                existing = data["tasks"].get(existing_id)

                if existing:
                    return deepcopy(existing)

        now = datetime.now(timezone.utc).isoformat()
        task_id = str(uuid4())

        task = {
            "task_id": task_id,
            "task_type": task_type,
            "payload": deepcopy(payload or {}),
            "priority": priority,
            "status": "PENDING",
            "retry_count": 0,
            "created_at": now,
            "updated_at": now,
            "idempotency_key": idempotency_key,
        }

        data["tasks"][task_id] = task

        if idempotency_key is not None:
            data["idempotency"][idempotency_key] = task_id

        self._save(data)

        return deepcopy(task)

    def get_task(self, task_id):
        data = self._load()
        task = data["tasks"].get(task_id)

        return deepcopy(task) if task else None

    def update_status(self, task_id, status):
        if status not in self.ALLOWED_STATUSES:
            raise ValueError("Invalid task status")

        data = self._load()

        if task_id not in data["tasks"]:
            raise KeyError(task_id)

        task = data["tasks"][task_id]
        task["status"] = status
        task["updated_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        self._save(data)

        return deepcopy(task)

    def list_tasks(self, status=None):
        data = self._load()
        tasks = list(data["tasks"].values())

        if status is not None:
            tasks = [
                task for task in tasks
                if task["status"] == status
            ]

        tasks.sort(
            key=lambda task: (
                task["priority"],
                task["created_at"],
            )
        )

        return deepcopy(tasks)

    def get_next_pending_task(self):
        pending = self.list_tasks(status="PENDING")

        return pending[0] if pending else None

    def delete_task(self, task_id):
        data = self._load()

        task = data["tasks"].pop(task_id, None)

        if task is None:
            return False

        key = task.get("idempotency_key")

        if key is not None:
            data["idempotency"].pop(key, None)

        self._save(data)

        return True
