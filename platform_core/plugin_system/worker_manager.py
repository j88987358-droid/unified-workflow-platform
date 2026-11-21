class WorkerManager:
    def __init__(self):
        self.workers = {}
        self.status = {}

    def register(self, worker_id, worker):
        if worker_id in self.workers:
            raise ValueError(f"Worker already exists: {worker_id}")

        self.workers[worker_id] = worker
        self.status[worker_id] = "REGISTERED"

    def start(self, worker_id, context=None):
        worker = self.workers[worker_id]

        worker.initialize(context or {})
        self.status[worker_id] = "READY"

        return self.status[worker_id]

    def execute(self, worker_id, task):
        worker = self.workers[worker_id]

        if self.status.get(worker_id) != "READY":
            raise RuntimeError("Worker is not ready")

        self.status[worker_id] = "RUNNING"

        try:
            result = worker.execute(task)
            self.status[worker_id] = "READY"
            return result

        except Exception:
            self.status[worker_id] = "ERROR"
            raise

    def health_check(self, worker_id):
        worker = self.workers[worker_id]
        return bool(worker.health_check())

    def stop(self, worker_id):
        worker = self.workers[worker_id]
        worker.shutdown()
        self.status[worker_id] = "STOPPED"
