import pytest

from platform_core.storage.apps_script_storage import AppsScriptStorage


class MockResponse:

    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class MockSession:

    def __init__(self, response=None):
        self.response = response or {
            "success": True
        }
        self.calls = []

    def post(self, url, json, **kwargs):
        self.calls.append({
            "url": url,
            "payload": json,
            "kwargs": kwargs
        })

        return MockResponse(self.response)


@pytest.fixture
def storage():
    session = MockSession()

    instance = AppsScriptStorage(
        url="https://script.google.com/macros/s/test/exec",
        token="test-token",
        session=session
    )

    return instance, session


def test_lease_start(storage):
    instance, session = storage

    result = instance.lease_start(
        "task-123",
        "runner-1",
        180
    )

    assert result["success"] is True

    payload = session.calls[0]["payload"]

    assert payload["action"] == "lease_start"
    assert payload["task_id"] == "task-123"
    assert payload["owner"] == "runner-1"
    assert payload["lease_seconds"] == 180
    assert payload["token"] == "test-token"


def test_lease_heartbeat(storage):
    instance, session = storage

    instance.lease_heartbeat(
        "task-123",
        "runner-1"
    )

    payload = session.calls[0]["payload"]

    assert payload["action"] == "lease_heartbeat"
    assert payload["task_id"] == "task-123"
    assert payload["owner"] == "runner-1"


def test_lease_check(storage):
    instance, session = storage

    session.response = {
        "success": True,
        "valid": True
    }

    result = instance.lease_check(
        "task-123",
        "runner-1"
    )

    assert result["valid"] is True


def test_lease_release(storage):
    instance, session = storage

    instance.lease_release(
        "task-123",
        "runner-1"
    )

    payload = session.calls[0]["payload"]

    assert payload["action"] == "lease_release"
    assert payload["task_id"] == "task-123"
    assert payload["owner"] == "runner-1"


def test_lease_failure_rejected(storage):
    instance, session = storage

    session.response = {
        "success": False,
        "error": "LEASE_ALREADY_HELD"
    }

    with pytest.raises(RuntimeError):
        instance.lease_start(
            "task-123",
            "runner-2"
        )


def test_existing_storage_methods_preserved(storage):
    instance, session = storage

    instance.set("test-key", {"value": 123})

    payload = session.calls[0]["payload"]

    assert payload["action"] == "set"
    assert payload["key"] == "test-key"
    assert payload["value"] == {"value": 123}
