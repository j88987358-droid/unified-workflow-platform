class ExecutionEngine:

    def __init__(
        self,
        task_manager,
        lifecycle_manager,
        retry_controller,
        worker_manager,
        lease_manager_factory=None,
    ):
        if task_manager is None:
            raise ValueError("TaskManager required")

        if lifecycle_manager is None:
            raise ValueError("LifecycleManager required")

        if retry_controller is None:
            raise ValueError("RetryController required")

        if worker_manager is None:
            raise ValueError("WorkerManager required")

        self.task_manager = task_manager
        self.lifecycle = lifecycle_manager
        self.retry_controller = retry_controller
        self.worker_manager = worker_manager
        self.lease_manager_factory = lease_manager_factory

    def _get_worker_id(self, task):
        payload = task.get("payload") or {}

        worker_id = payload.get("worker_id")

        if not worker_id:
            worker_id = task.get("task_type")

        if not worker_id:
            raise ValueError("Task has no worker_id")

        return worker_id

    def _worker_input(self, task):
        """Expose task metadata plus the submitted business payload.

        Runtime submissions wrap user data under payload['data']; lower-level
        task-queue callers may provide a flat payload. Preserve task_id and
        other task metadata for workers that rely on the execution envelope.
        """
        payload = task.get("payload") or {}
        data = payload.get("data")

        if isinstance(data, dict):
            # Submitted data is untrusted input. Task metadata must win so a
            # caller cannot replace task_id, status, payload, or timestamps.
            return {**data, **task}

        return task

    def _ensure_worker_ready(self, worker_id):
        if worker_id not in self.worker_manager.workers:
            raise KeyError(f"Worker not registered: {worker_id}")

        status = self.worker_manager.status.get(worker_id)

        if status != "READY":
            self.worker_manager.start(worker_id)

        if not self.worker_manager.health_check(worker_id):
            raise RuntimeError(f"Worker unhealthy: {worker_id}")

    def _cleanup_lease(
        self,
        lease_manager,
        lease_started,
        lease_lost,
    ):
        if lease_manager is None or not lease_started:
            return

        try:
            lease_manager.stop()
        except Exception:
            return

        if lease_lost:
            return

        try:
            lease_manager.release()
        except Exception:
            pass

    def _execute_running_task(self, task):
        """Acquire the execution lease before changing task state or running work."""
        task_id = task["task_id"]
        lease_manager = None
        lease_started = False
        lease_lost = False

        if self.lease_manager_factory is not None:
            try:
                lease_manager = self.lease_manager_factory()
                lease_manager.start(task_id)
                lease_started = True
            except Exception as exc:
                # A competing runner may own the lease, or the lease backend
                # may be unavailable. Do not mutate the task: another runner
                # may be executing it, and a later pass can safely retry.
                return {
                    "task_id": task_id,
                    "status": "LEASE_UNAVAILABLE",
                    "task_status": task.get("status"),
                    "error": str(exc),
                }

        try:
            current = self.task_manager.get_task(task_id)
            if current is None:
                raise KeyError(task_id)

            if current["status"] in {"PENDING", "RETRY"}:
                task = self.lifecycle.mark_running(task_id)
            elif current["status"] == "RUNNING":
                task = current
            else:
                return current

            try:
                worker_id = self._get_worker_id(task)
                self._ensure_worker_ready(worker_id)
                result = self.worker_manager.execute(
                    worker_id,
                    self._worker_input(task),
                )

                if lease_manager is not None:
                    lease_manager.check()

                return self.lifecycle.mark_success(
                    task_id,
                    details={"result": result},
                )

            except Exception as exc:
                if lease_manager is not None:
                    try:
                        lease_manager.check()
                    except Exception:
                        lease_lost = True
                        raise

                current = self.task_manager.get_task(task_id)
                if current is None:
                    raise KeyError(task_id)
                if current["status"] != "RUNNING":
                    raise

                self.lifecycle.mark_failed(
                    task_id,
                    details={"error": str(exc)},
                )
                return self.retry_controller.handle_failure(
                    task_id,
                    error=str(exc),
                )
        finally:
            self._cleanup_lease(
                lease_manager,
                lease_started,
                lease_lost,
            )

    def execute_task(self, task_id):
        task = self.task_manager.get_task(task_id)
        if task is None:
            raise KeyError(task_id)

        if task["status"] not in {"PENDING", "RETRY", "RUNNING"}:
            raise ValueError(
                f"Task cannot execute from status {task['status']}"
            )

        return self._execute_running_task(task)

    def process_pending_tasks(self, max_tasks=100):
        if max_tasks < 1:
            raise ValueError("max_tasks must be positive")

        results = []
        for _ in range(max_tasks):
            task = self.task_manager.get_next_pending_task()
            if task is None:
                break
            result = self.execute_task(task["task_id"])
            results.append(result)
            if result.get("status") == "LEASE_UNAVAILABLE":
                # The same highest-priority task may remain pending. Avoid
                # repeatedly selecting it in this run.
                break
        return results

    def process_due_retries(self):
        # Do not pre-mark retry tasks RUNNING. The lease must be acquired
        # first, then ExecutionEngine performs the RETRY -> RUNNING transition.
        due_tasks = self.retry_controller.get_due_retries()
        results = []
        for task in due_tasks:
            result = self.execute_task(task["task_id"])
            results.append(result)
        return results

    def run_once(self, max_tasks=100):
        return {
            "pending_results": self.process_pending_tasks(max_tasks=max_tasks),
            "retry_results": self.process_due_retries(),
        }
