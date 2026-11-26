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
