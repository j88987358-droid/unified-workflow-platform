import threading
import uuid


class ExecutionLeaseManager:

    def __init__(
        self,
        storage,
        lease_seconds=180,
        heartbeat_interval=60,
        owner=None,
    ):
        if storage is None:
            raise ValueError("Storage is required")

        if lease_seconds < 30:
            raise ValueError("Lease duration must be at least 30 seconds")

        if heartbeat_interval <= 0:
            raise ValueError("Heartbeat interval must be positive")

        if heartbeat_interval >= lease_seconds:
            raise ValueError(
                "Heartbeat interval must be shorter than lease duration"
            )

        self.storage = storage
        self.lease_seconds = lease_seconds
        self.heartbeat_interval = heartbeat_interval

        self.owner = owner or str(uuid.uuid4())

        self._stop_event = threading.Event()
        self._thread = None
        self._error = None
        self._started = False

    def start(self, task_id):
        if self._started:
            raise RuntimeError("Lease manager is already running")

        result = self.storage.lease_start(
            task_id=task_id,
            owner=self.owner,
            lease_seconds=self.lease_seconds,
        )

        self._task_id = task_id
        self._error = None
        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"lease-heartbeat-{task_id}",
            daemon=True,
        )

        self._started = True
        self._thread.start()

        return result

    def _heartbeat_loop(self):
        while not self._stop_event.wait(
            self.heartbeat_interval
        ):
            try:
                self.storage.lease_heartbeat(
                    task_id=self._task_id,
                    owner=self.owner,
                    lease_seconds=self.lease_seconds,
                )

            except Exception as exc:
                self._error = exc
                self._stop_event.set()
                return

    def stop(self):
        if not self._started:
            return

        self._stop_event.set()

        timeout = (
            self.heartbeat_interval
            + getattr(self.storage, "timeout", 45)
            + 5
        )

        self._thread.join(timeout=timeout)

        if self._thread.is_alive():
            raise RuntimeError(
                "Heartbeat thread did not stop safely"
            )

        self._started = False

        if self._error is not None:
            raise RuntimeError(
                f"Execution lease heartbeat failed: {self._error}"
            ) from self._error

    def check(self):
        if not self._started:
            raise RuntimeError("Lease manager is not running")

        if self._error is not None:
            raise RuntimeError(
                f"Execution lease heartbeat failed: {self._error}"
            ) from self._error

        result = self.storage.lease_check(
            task_id=self._task_id,
            owner=self.owner,
            lease_seconds=self.lease_seconds,
        )

        if not result.get("valid"):
            raise RuntimeError("Execution lease is no longer valid")

        return True

    def release(self):
        if self._started:
            self.stop()

        return self.storage.lease_release(
            task_id=self._task_id,
            owner=self.owner,
            lease_seconds=self.lease_seconds,
        )
