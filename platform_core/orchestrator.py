class ExecutionOrchestrator:

    def __init__(
        self,
        worker_manager,
        task_manager,
        checkpoint_manager,
        execution_engine=None,
    ):
        self.worker_manager = worker_manager
        self.task_manager = task_manager
        self.checkpoints = checkpoint_manager
        self.execution_engine = execution_engine

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
        """Delegate execution to the single authoritative execution engine."""
        if self.execution_engine is None:
            raise RuntimeError(
                "ExecutionEngine must be injected; direct worker execution is disabled"
            )
        return self.execution_engine.execute_task(task_id)
