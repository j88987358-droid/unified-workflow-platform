import json
import pytest

from platform_core.storage.apps_script_storage import (
    AppsScriptStorage
)


class FakeResponse:
    def __init__(self, data, status_code=200):
        self.data = data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception("HTTP error")

    def json(self):
        return self.data


class FakeSession:
    def __init__(self):
        self.data = {}
        self.calls = []

    def post(self, url, json, timeout, allow_redirects):
        self.calls.append(json)

        action = json["action"]
        key = json.get("key")

        if action == "ping":
            return FakeResponse({
                "success": True,
                "status": "CONNECTED"
            })

        if action == "set":
            self.data[key] = json.get("value")
            return FakeResponse({
                "success": True,
                "action": "SET",
                "key": key
            })

        if action == "get":
            if key not in self.data:
                return FakeResponse({
                    "success": True,
                    "found": False,
                    "value": None
                })

            return FakeResponse({
                "success": True,
                "found": True,
                "value": self.data[key]
            })

        if action == "delete":
            self.data.pop(key, None)
            return FakeResponse({
                "success": True,
                "action": "DELETE",
                "key": key
            })

        if action == "lease_inspect":
            return FakeResponse({
                "success": True,
                "active": False,
                "owner": None,
                "expires_at": None,
            })

        return FakeResponse({
            "success": False,
            "error": "UNKNOWN_ACTION"
        })


def make_storage(session=None):
    return AppsScriptStorage(
        url="https://script.google.com/macros/s/test/exec",
        token="test-token",
        session=session or FakeSession()
    )


def test_constructor_requires_credentials():
    with pytest.raises(ValueError):
        AppsScriptStorage("", "token")

    with pytest.raises(ValueError):
        AppsScriptStorage(
            "https://script.google.com/macros/s/test/exec",
            ""
        )


def test_constructor_rejects_invalid_url():
    with pytest.raises(ValueError):
        AppsScriptStorage(
            "https://example.com",
            "test-token"
        )


def test_health_check():
    storage = make_storage()
    assert storage.health_check() is True


def test_set_and_get():
    storage = make_storage()

    value = {
        "name": "AI Workflow",
        "status": "active",
        "count": 10
    }

    storage.set("test:key", value)

    assert storage.get("test:key") == value


def test_missing_key_returns_none():
    storage = make_storage()
    assert storage.get("missing:key") is None


def test_update_existing_value():
    storage = make_storage()

    storage.set("test:key", {"version": 1})
    storage.set("test:key", {"version": 2})

    assert storage.get("test:key") == {"version": 2}


def test_delete():
    storage = make_storage()

    storage.set("test:key", {"value": 100})
    storage.delete("test:key")

    assert storage.get("test:key") is None


def test_separate_instances_share_same_backend():
    session = FakeSession()

    storage_a = make_storage(session)
    storage_b = make_storage(session)

    storage_a.set("shared:key", {"status": "saved"})

    assert storage_b.get("shared:key") == {
        "status": "saved"
    }


def test_failed_api_response():
    class FailedSession:
        def post(self, *args, **kwargs):
            return FakeResponse({
                "success": False,
                "error": "UNAUTHORIZED"
            })

    storage = make_storage(FailedSession())

    with pytest.raises(RuntimeError, match="UNAUTHORIZED"):
        storage.get("test:key")


def test_adapter_sends_token():
    session = FakeSession()
    storage = make_storage(session)

    storage.health_check()

    assert session.calls[0]["token"] == "test-token"


def test_complex_json_values():
    storage = make_storage()

    value = {
        "tasks": [
            {"id": "task-1", "status": "PENDING"},
            {"id": "task-2", "status": "SUCCESS"}
        ],
        "metadata": {
            "retry_count": 3,
            "enabled": True
        }
    }

    storage.set("complex:key", value)

    assert storage.get("complex:key") == value


def test_lease_inspect_returns_authoritative_backend_state():
    storage = make_storage()
    result = storage.lease_inspect("task-123")
    assert result["success"] is True
    assert result["active"] is False
