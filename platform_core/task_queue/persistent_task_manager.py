from copy import deepcopy
from datetime import datetime, timezone
import threading
from uuid import uuid4


class PersistentTaskManager:
    """Persistent task collection manager.

    Storage adapters with ``atomic_update`` serialize mutations at the adapter
    boundary. Adapters without it receive process-local serialization only.
    """

    STORAGE_KEY = "task_queue:tasks"

    ALLOWED_STATUSES = {
        "PENDING",
        "RUNNING",
        "SUCCESS",
        "FAILED",
        "RETRY",
        "DEAD_LETTER",
    }

    _locks_guard = threading.Lock()
    _locks = {}

    def __init__(self, storage):
        if storage is None:
            raise ValueError("Storage is required")

        self.storage = storage
        with self._locks_guard:
            self._lock = self._locks.setdefault(id(storage), threading.RLock())

        atomic_update = getattr(self.storage, "atomic_update", None)
        if callable(atomic_update):
            atomic_update(
                self.STORAGE_KEY,
                lambda current: current if isinstance(current, dict) else self._empty_state(),
            )
        elif self.storage.get(self.STORAGE_KEY) is None:
            with self._lock:
                if self.storage.get(self.STORAGE_KEY) is None:
                    self.storage.set(self.STORAGE_KEY, self._empty_state())

    def _empty_state(self):
        return {"tasks": {}, "idempotency": {}}

    def _load(self):
        data = self.storage.get(self.STORAGE_KEY)
        if not isinstance(data, dict):
            return self._empty_state()
        data.setdefault("tasks", {})
        data.setdefault("idempotency", {})
        return deepcopy(data)

    def _save(self, data):
        return self.storage.set(self.STORAGE_KEY, data)

    def mutate_tasks(self, mutator):
        """Run a task-collection mutation and return the mutator's result."""
        if not callable(mutator):
            raise TypeError("mutator must be callable")
        result = {}

        def apply(data):
            if not isinstance(data, dict):
                data = self._empty_state()
            data.setdefault("tasks", {})
            data.setdefault("idempotency", {})
            result["value"] = mutator(data)
            return data

        atomic_update = getattr(self.storage, "atomic_update", None)
        if callable(atomic_update):
            atomic_update(self.STORAGE_KEY, apply)
        else:
            with self._lock:
                data = self._load()
                result["value"] = mutator(data)
                self._save(data)

        return deepcopy(result.get("value"))

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

        now = datetime.now(timezone.utc).isoformat()

        def create(data):
            if idempotency_key is not None:
                existing_id = data["idempotency"].get(idempotency_key)
                existing = data["tasks"].get(existing_id) if existing_id else None
                if existing:
                    return existing

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
            return task

        return self.mutate_tasks(create)

    def get_task(self, task_id):
        data = self._load()
        task = data["tasks"].get(task_id)
        return deepcopy(task) if task else None

    def update_status(self, task_id, status):
        if status not in self.ALLOWED_STATUSES:
            raise ValueError("Invalid task status")

        now = datetime.now(timezone.utc).isoformat()

        def update(data):
            if task_id not in data["tasks"]:
                raise KeyError(task_id)
            task = data["tasks"][task_id]
            task["status"] = status
            task["updated_at"] = now
            return task

        return self.mutate_tasks(update)

    def list_tasks(self, status=None):
        data = self._load()
        tasks = list(data["tasks"].values())
        if status is not None:
            tasks = [task for task in tasks if task["status"] == status]
        tasks.sort(key=lambda task: (task["priority"], task["created_at"]))
        return deepcopy(tasks)

    def get_next_pending_task(self):
        pending = self.list_tasks(status="PENDING")
        return pending[0] if pending else None

    def delete_task(self, task_id):
        def delete(data):
            task = data["tasks"].pop(task_id, None)
            if task is None:
                return False
            key = task.get("idempotency_key")
            if key is not None:
                data["idempotency"].pop(key, None)
            return True

        return bool(self.mutate_tasks(delete))
