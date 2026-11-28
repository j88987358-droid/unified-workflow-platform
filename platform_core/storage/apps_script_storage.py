import requests


class AppsScriptStorage:

    def __init__(self, url, token, timeout=45, session=None):
        if not url or not token:
            raise ValueError("URL and token are required")

        if not url.startswith("https://script.google.com/"):
            raise ValueError("Invalid Google Apps Script URL")

        self.url = url
        self.token = token
        self.timeout = timeout
        self.session = session or requests.Session()

    def _request(self, action, key=None, value=None, **extra):
        payload = {
            "token": self.token,
            "action": action
        }

        if key is not None:
            payload["key"] = key

        if value is not None:
            payload["value"] = value

        payload.update(extra)

        try:
            response = self.session.post(
                self.url,
                json=payload,
                timeout=self.timeout,
                allow_redirects=True
            )

            response.raise_for_status()
            result = response.json()

        except requests.RequestException as exc:
            raise RuntimeError(
                f"Storage network error: {exc}"
            ) from exc

        except ValueError as exc:
            raise RuntimeError(
                "Storage API returned invalid JSON"
            ) from exc

        if not isinstance(result, dict):
            raise RuntimeError(
                "Storage API returned an invalid response"
            )

        if not result.get("success"):
            raise RuntimeError(
                result.get("error", "Storage API operation failed")
            )

        return result

    # Existing storage operations

    def get(self, key):
        result = self._request("get", key=key)

        if not result.get("found"):
            return None

        return result.get("value")

    def set(self, key, value):
        return self._request(
            "set",
            key=key,
            value=value
        )

    def atomic_update(self, key, updater, max_retries=10):
        """Update a key with server-side compare-and-set and bounded retries.

        The updater can run more than once after a conflict; avoid side effects.
        """
        if not callable(updater):
            raise TypeError("updater must be callable")
        if not isinstance(max_retries, int) or max_retries < 1:
            raise ValueError("max_retries must be a positive integer")

        for _ in range(max_retries):
            current = self._request("get_versioned", key=key)
            value = current.get("value") if current.get("found") else None
            revision = current.get("revision", 0)
            updated_value = updater(value)
            result = self._request(
                "compare_and_set", key=key,
                expected_revision=revision, new_value=updated_value,
            )
            if result.get("updated"):
                return updated_value
            if not result.get("conflict"):
                raise RuntimeError("Storage compare-and-set failed")
        raise RuntimeError(
            f"Storage update conflict: exceeded {max_retries} retries for {key!r}"
        )

    def delete(self, key):
        return self._request("delete", key=key)

    def health_check(self):
        result = self._request("ping")
        return result.get("status") == "CONNECTED"

    # Execution Lease operations

    def lease_start(self, task_id, owner, lease_seconds=180):
        return self._request(
            "lease_start",
            task_id=task_id,
            owner=owner,
            lease_seconds=lease_seconds
        )

    def lease_heartbeat(self, task_id, owner, lease_seconds=180):
        return self._request(
            "lease_heartbeat",
            task_id=task_id,
            owner=owner,
            lease_seconds=lease_seconds
        )

    def lease_check(self, task_id, owner, lease_seconds=180):
        return self._request(
            "lease_check",
            task_id=task_id,
            owner=owner,
            lease_seconds=lease_seconds
        )

    def lease_release(self, task_id, owner, lease_seconds=180):
        return self._request(
            "lease_release",
            task_id=task_id,
            owner=owner,
            lease_seconds=lease_seconds
            )

    def lease_inspect(self, task_id):
        return self._request(
            "lease_inspect",
            task_id=task_id,
        )
