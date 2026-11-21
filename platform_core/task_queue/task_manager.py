from uuid import uuid4
from datetime import datetime, timezone

class TaskManager:
    def __init__(self):
        self.tasks = {}

    def create_task(self, task_type, payload=None, priority=5):
        task_id = str(uuid4())

        task = {
            "task_id": task_id,
            "task_type": task_type,
            "payload": payload or {},
            "priority": priority,
            "status": "PENDING",
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        self.tasks[task_id] = task
        return task

    def get_task(self, task_id):
        return self.tasks.get(task_id)

    def update_status(self, task_id, status):
        if task_id not in self.tasks:
            raise KeyError(task_id)

        allowed = {
            "PENDING", "RUNNING", "SUCCESS", "FAILED"
        }

        if status not in allowed:
            raise ValueError("Invalid task status")

        self.tasks[task_id]["status"] = status
        return self.tasks[task_id]

    def list_tasks(self):
        return list(self.tasks.values())
