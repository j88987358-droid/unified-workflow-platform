import json
from pathlib import Path

class WorkerRegistry:
    def __init__(self, worker_directory="plugins/workers"):
        self.worker_directory = Path(worker_directory)
        self.workers = {}

    def discover(self):
        discovered = []

        if not self.worker_directory.exists():
            return discovered

        for manifest in self.worker_directory.rglob("worker.json"):
            try:
                data = json.loads(
                    manifest.read_text(encoding="utf-8")
                )

                required = ("id", "name", "version", "entry_point")
                if not all(data.get(key) for key in required):
                    continue

                worker_id = data["id"]

                if worker_id in self.workers:
                    continue

                data["_manifest_path"] = str(manifest)
                self.workers[worker_id] = data
                discovered.append(data)

            except (OSError, json.JSONDecodeError):
                continue

        return discovered

    def register(self, worker_id, worker):
        if worker_id in self.workers:
            raise ValueError(f"Worker already registered: {worker_id}")

        self.workers[worker_id] = worker

    def get(self, worker_id):
        return self.workers.get(worker_id)

    def list_workers(self):
        return list(self.workers.keys())
