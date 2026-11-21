from platform_core.contracts.base_worker import BaseWorker
from platform_core.plugin_system.worker_registry import WorkerRegistry
from platform_core.plugin_system.worker_manager import WorkerManager
from platform_core.task_queue.task_manager import TaskManager
from platform_core.event_system.event_bus import EventBus
from platform_core.architecture_initializer import ArchitectureInitializer

class ExampleWorker(BaseWorker):
    def initialize(self, context):
        self.ready = True

    def execute(self, task):
        return {"result": task["value"] * 2}

    def health_check(self):
        return getattr(self, "ready", False)

def test_worker_lifecycle():
    manager = WorkerManager()
    worker = ExampleWorker()

    manager.register("example", worker)
    assert manager.start("example") == "READY"
    assert manager.health_check("example") is True

    result = manager.execute("example", {"value": 5})
    assert result["result"] == 10

    manager.stop("example")
    assert manager.status["example"] == "STOPPED"

def test_task_creation():
    manager = TaskManager()
    task = manager.create_task("example", {"value": 5})

    assert task["status"] == "PENDING"
    assert manager.get_task(task["task_id"]) is not None

def test_task_status():
    manager = TaskManager()
    task = manager.create_task("example")

    manager.update_status(task["task_id"], "SUCCESS")

    assert manager.get_task(task["task_id"])["status"] == "SUCCESS"

def test_event_bus():
    bus = EventBus()
    received = []

    bus.subscribe("task.completed", received.append)
    bus.publish("task.completed", {"task_id": "123"})

    assert received == [{"task_id": "123"}]

def test_worker_registry(tmp_path):
    registry = WorkerRegistry(str(tmp_path))
    assert registry.discover() == []

def test_architecture_initializer():
    result = ArchitectureInitializer().initialize()

    assert "worker_registry" in result
    assert "worker_manager" in result
    assert "task_manager" in result
    assert "event_bus" in result
