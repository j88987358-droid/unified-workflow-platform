from datetime import datetime, timezone

class CheckpointManager:

    def __init__(self, storage, namespace="architecture"):
        self.storage = storage
        self.namespace = namespace

    def save(self, name, state):
        payload = {
            "state": state,
            "saved_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }
        return self.storage.set(
            f"{self.namespace}:checkpoint:{name}",
            payload,
        )

    def load(self, name):
        return self.storage.get(
            f"{self.namespace}:checkpoint:{name}"
        )

    def delete(self, name):
        return self.storage.delete(
            f"{self.namespace}:checkpoint:{name}"
        )
