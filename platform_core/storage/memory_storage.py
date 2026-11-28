from copy import deepcopy
import threading
import time

from .base_storage import BaseStorage


class InMemoryStorage(BaseStorage):
    """Thread-safe, process-local storage and lease adapter.

    This adapter is intended for local development and tests. Its leases are
    not shared across processes or machines.
    """

    def __init__(self):
        self.data = {}
        self._leases = {}
        self._lock = threading.RLock()

    def get(self, key):
        with self._lock:
            return deepcopy(self.data.get(key))

    def set(self, key, value):
        with self._lock:
            self.data[key] = deepcopy(value)
        return True

    def delete(self, key):
        with self._lock:
            self.data.pop(key, None)
        return True

    def atomic_update(self, key, updater):
        """Atomically replace one value using an updater under the storage lock."""
        if not callable(updater):
            raise TypeError("updater must be callable")
        with self._lock:
            current = deepcopy(self.data.get(key))
            updated = updater(current)
            self.data[key] = deepcopy(updated)
            return deepcopy(updated)

    def lease_start(self, task_id, owner, lease_seconds=180):
        if not task_id or not owner or lease_seconds <= 0:
            raise ValueError("task_id, owner and positive lease_seconds are required")

        now = time.time()
        with self._lock:
            current = self._leases.get(task_id)
            if current and current["expires_at"] > now and current["owner"] != owner:
                return {
                    "success": False,
                    "valid": False,
                    "error": "LEASE_ALREADY_HELD",
                    "owner": current["owner"],
                    "expires_at": current["expires_at"],
                }

            expiry = now + lease_seconds
            self._leases[task_id] = {
                "owner": owner,
                "expires_at": expiry,
            }
            return {
                "success": True,
                "valid": True,
                "task_id": task_id,
                "owner": owner,
                "expires_at": expiry,
            }

    def lease_heartbeat(self, task_id, owner, lease_seconds=180):
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")

        now = time.time()
        with self._lock:
            current = self._leases.get(task_id)
            if not current or current["owner"] != owner or current["expires_at"] <= now:
                return {"success": False, "valid": False, "error": "LEASE_NOT_HELD"}

            current["expires_at"] = now + lease_seconds
            return {
                "success": True,
                "valid": True,
                "task_id": task_id,
                "owner": owner,
                "expires_at": current["expires_at"],
            }

    def lease_check(self, task_id, owner, lease_seconds=180):
        del lease_seconds
        now = time.time()
        with self._lock:
            current = self._leases.get(task_id)
            valid = bool(
                current
                and current["owner"] == owner
                and current["expires_at"] > now
            )
            return {
                "success": True,
                "valid": valid,
                "expires_at": current["expires_at"] if current else None,
            }

    def lease_inspect(self, task_id):
        """Return authoritative lease state without requiring its owner."""
        now = time.time()
        with self._lock:
            current = self._leases.get(task_id)
            if not current:
                return {"success": True, "active": False, "owner": None, "expires_at": None}
            active = current["expires_at"] > now
            if not active:
                self._leases.pop(task_id, None)
            return {
                "success": True,
                "active": active,
                "owner": current["owner"] if active else None,
                "expires_at": current["expires_at"],
            }

    def lease_release(self, task_id, owner, lease_seconds=180):
        del lease_seconds
        with self._lock:
            current = self._leases.get(task_id)
            if current and current["owner"] == owner:
                self._leases.pop(task_id, None)
                return {"success": True, "released": True}
            return {"success": True, "released": False}
