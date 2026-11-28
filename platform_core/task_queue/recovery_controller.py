from copy import deepcopy
from datetime import datetime, timezone


class RecoveryController:

    RECOVERY_STORAGE_KEY = "task_queue:recovery_events"

    def __init__(
        self,
        task_manager,
        lifecycle_manager,
        retry_controller,
        stale_after_seconds=900,
        clock=None,
        lease_storage=None,
    ):
        if task_manager is None:
            raise ValueError("TaskManager is required")

        if lifecycle_manager is None:
            raise ValueError("LifecycleManager is required")

        if retry_controller is None:
            raise ValueError("RetryController is required")

        if stale_after_seconds <= 0:
            raise ValueError(
                "stale_after_seconds must be positive"
            )

        self.task_manager = task_manager
        self.lifecycle = lifecycle_manager
        self.retry_controller = retry_controller
        self.storage = task_manager.storage
        self.lease_storage = lease_storage

        self.stale_after_seconds = stale_after_seconds

        self.clock = clock or (
            lambda: datetime.now(timezone.utc)
        )

        if self.storage.get(
            self.RECOVERY_STORAGE_KEY
        ) is None:
            self.storage.set(
                self.RECOVERY_STORAGE_KEY,
                [],
            )

    def _now(self):
        value = self.clock()

        if value.tzinfo is None:
            value = value.replace(
                tzinfo=timezone.utc
            )

        return value.astimezone(timezone.utc)

    def _parse_datetime(self, value):
        if not value:
            return None

        try:
            parsed = datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )

            if parsed.tzinfo is None:
                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

            return parsed.astimezone(
                timezone.utc
            )

        except (ValueError, TypeError, AttributeError):
            return None

    def has_active_lease(self, task):
        """Use the lease backend as authority when it is available.

        Backend errors or malformed responses fail closed: recovery must not
        assume a lease is absent when its state cannot be verified.
        """
        if self.lease_storage is not None:
            inspect = getattr(self.lease_storage, "lease_inspect", None)
            if not callable(inspect):
                return True
            try:
                result = inspect(task.get("task_id"))
            except Exception:
                return True
            if not isinstance(result, dict) or result.get("success") is not True:
                return True
            if not isinstance(result.get("active"), bool):
                return True
            return result["active"]

        if task.get("lease_status") != "ACTIVE":
            return False

        lease_expires_at = self._parse_datetime(task.get("lease_expires_at"))
        if lease_expires_at is None:
            return True
        return lease_expires_at > self._now()

    def _record_event(
        self,
        task_id,
        event_type,
        details=None,
    ):
        event = {
            "task_id": task_id,
            "event_type": event_type,
            "timestamp": self._now().isoformat(),
            "details": deepcopy(details or {}),
        }

        atomic_update = getattr(self.storage, "atomic_update", None)
        if callable(atomic_update):
            def append_event(events):
                if not isinstance(events, list):
                    events = []
                events.append(event)
                return events
            atomic_update(self.RECOVERY_STORAGE_KEY, append_event)
        else:
            events = self.storage.get(self.RECOVERY_STORAGE_KEY)
            if not isinstance(events, list):
                events = []
            events.append(event)
            self.storage.set(self.RECOVERY_STORAGE_KEY, events)

        return event

    def get_recovery_history(self, task_id=None):
        events = self.storage.get(
            self.RECOVERY_STORAGE_KEY
        )

        if not isinstance(events, list):
            return []

        if task_id is not None:
            events = [
                event for event in events
                if event["task_id"] == task_id
            ]

        return deepcopy(events)

    def is_stale(self, task):
        if task.get("status") != "RUNNING":
            return False

        # Never recover a task with an active lease.
        if self.has_active_lease(task):
            return False

        started_at = self._parse_datetime(
            task.get("started_at")
            or task.get("updated_at")
        )

        if started_at is None:
            return False

        age = self._now() - started_at

        return age.total_seconds() >= (
            self.stale_after_seconds
        )

    def find_stale_tasks(self, limit=100):
        if limit < 1:
            raise ValueError(
                "limit must be positive"
            )

        running_tasks = self.task_manager.list_tasks(
            status="RUNNING"
        )

        stale_tasks = [
            task for task in running_tasks
            if self.is_stale(task)
        ]

        return stale_tasks[:limit]

    def recover_task(self, task_id):
        task = self.task_manager.get_task(task_id)

        if task is None:
            raise KeyError(task_id)

        if task.get("status") != "RUNNING":
            return None

        # Recheck lease immediately before recovery.
        if self.has_active_lease(task):
            return None

        if not self.is_stale(task):
            return None

        self._record_event(
            task_id,
            "RECOVERY_STARTED",
            {
                "previous_status": "RUNNING",
                "reason": "Stale execution without active lease",
            },
        )

        self.lifecycle.mark_failed(
            task_id,
            details={
                "reason": "Interrupted execution",
                "recovery": True,
            },
        )

        result = self.retry_controller.handle_failure(
            task_id,
            error="Task interrupted by runner shutdown",
        )

        self._record_event(
            task_id,
            "RECOVERY_COMPLETED",
            {
                "new_status": result["status"],
                "retry_count": result.get(
                    "retry_count", 0
                ),
            },
        )

        return result

    def recover_stale_tasks(self, limit=100):
        stale_tasks = self.find_stale_tasks(
            limit=limit
        )

        results = []

        for task in stale_tasks:
            result = self.recover_task(
                task["task_id"]
            )

            if result is not None:
                results.append(result)

        return results

    def recovery_report(self):
        events = self.get_recovery_history()

        completed = [
            event for event in events
            if event["event_type"] == "RECOVERY_COMPLETED"
        ]

        retry_count = sum(
            1 for event in completed
            if event["details"].get("new_status") == "RETRY"
        )

        dead_letter_count = sum(
            1 for event in completed
            if event["details"].get("new_status")
            == "DEAD_LETTER"
        )

        return {
            "total_recoveries": len(completed),
            "retry_scheduled": retry_count,
            "dead_letter": dead_letter_count,
            "recovery_events": len(events),
        }
