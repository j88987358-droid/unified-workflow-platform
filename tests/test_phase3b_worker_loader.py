import json

import pytest

from platform_core.plugin_system.dynamic_worker_loader import (
    DynamicWorkerLoader
)


WORKER_CODE = (
    "from platform_core.contracts.base_worker import BaseWorker\n"
    "\n"
    "class ExampleWorker(BaseWorker):\n"
    "    name = 'Example Worker'\n"
    "    version = '1.0.0'\n"
    "\n"
    "    def initialize(self, context):\n"
    "        self.context = context\n"
    "\n"
    "    def execute(self, task):\n"
    "        return {'status': 'success', 'task': task}\n"
    "\n"
    "    def health_check(self):\n"
    "        return True\n"
    "\n"
    "    def shutdown(self):\n"
    "        pass\n"
)


def create_loader(tmp_path, approved=True):

    worker_dir = tmp_path / "plugins" / "workers"
    example_dir = worker_dir / "example_worker"

    example_dir.mkdir(parents=True)

    manifest = {
        "id": "example.worker",
        "name": "Example Worker",
        "version": "1.0.0",
        "api_version": "1.0",
        "entry_point": "main:ExampleWorker",
        "enabled": True,
        "dependencies": []
    }

    (example_dir / "worker.json").write_text(
        json.dumps(manifest),
        encoding="utf-8"
    )

    (example_dir / "main.py").write_text(
        WORKER_CODE,
        encoding="utf-8"
    )

    approved_ids = (
        ["example.worker"] if approved else []
    )

    loader = DynamicWorkerLoader(
        str(worker_dir),
        approved_worker_ids=approved_ids
    )

    loader.discover()

    return loader


def test_worker_discovery(tmp_path):

    loader = create_loader(tmp_path)

    assert loader.registry.get(
        "example.worker"
    ) is not None


def test_worker_load(tmp_path):

    loader = create_loader(tmp_path)

    result = loader.load("example.worker")

    assert result["status"] == "READY"


def test_worker_execution(tmp_path):

    loader = create_loader(tmp_path)

    loader.load("example.worker")

    result = loader.execute(
        "example.worker",
        {"action": "test"}
    )

    assert result["status"] == "success"


def test_worker_health_check(tmp_path):

    loader = create_loader(tmp_path)

    loader.load("example.worker")

    assert loader.health_check(
        "example.worker"
    ) is True


def test_unapproved_worker_rejected(tmp_path):

    loader = create_loader(tmp_path, approved=False)

    with pytest.raises(PermissionError):
        loader.load("example.worker")


def test_duplicate_worker_rejected(tmp_path):

    loader = create_loader(tmp_path)

    loader.load("example.worker")

    with pytest.raises(ValueError):
        loader.load("example.worker")


def test_worker_unload(tmp_path):

    loader = create_loader(tmp_path)

    loader.load("example.worker")

    assert loader.unload("example.worker") is True

    assert loader.health_check(
        "example.worker"
    ) is False


def test_disabled_worker_rejected(tmp_path):

    loader = create_loader(tmp_path)

    manifest = loader.registry.get("example.worker")
    manifest["enabled"] = False

    with pytest.raises(PermissionError):
        loader.load("example.worker")
