class ExecutionOrchestrator:

    def __init__(
        self,
        worker_manager,
        task_manager,
        checkpoint_manager,
    ):
        self.worker_manager = worker_manager
        self.task_manager = task_manager
        self.checkpoints = checkpoint_manager

    def register_worker(self, worker_id, worker, context=None):
        self.worker_manager.register(worker_id, worker)
        return self.worker_manager.start(
            worker_id, context or {}
        )

    def create_task(self, worker_id, payload=None, priority=5):
        if worker_id not in self.worker_manager.workers:
            raise ValueError(
                f"Worker not registered: {worker_id}"
            )

        return self.task_manager.create_task(
            task_type=worker_id,
            payload={
                "worker_id": worker_id,
                "data": payload or {},
            },
            priority=priority,
        )

    def execute_task(self, task_id):
        task = self.task_manager.get_task(task_id)

        if task is None:
            raise KeyError(task_id)

        if task["status"] != "PENDING":
            raise ValueError(
                "Only PENDING tasks can be executed"
            )

        worker_id = task["payload"]["worker_id"]

        self.task_manager.update_status(
            task_id, "RUNNING"
        )

        try:
            result = self.worker_manager.execute(
                worker_id,
                task["payload"]["data"],
            )

            self.task_manager.update_status(
                task_id, "SUCCESS"
            )

            return {
                "task_id": task_id,
                "status": "SUCCESS",
                "result": result,
            }

        except Exception as exc:
            self.task_manager.update_status(
                task_id, "FAILED"
            )

            return {
                "task_id": task_id,
                "status": "FAILED",
                "error": str(exc),
            }
