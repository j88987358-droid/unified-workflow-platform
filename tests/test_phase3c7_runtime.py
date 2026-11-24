from platform_core.runtime import ArchitectureRuntime
from platform_core.storage.memory_storage import InMemoryStorage
from platform_core.task_queue.persistent_task_manager import PersistentTaskManager
from platform_core.contracts.base_worker import BaseWorker


class DemoWorker(BaseWorker):

    name = "demo-worker"

    def initialize(self, context):
        self.initialized = True

    def execute(self, task):
        return {
            "received_task_id": task["task_id"],
            "received_payload": task["payload"],
            "success": True
        }

    def health_check(self):
        return True


def test_runtime_uses_persistent_task_manager():
    runtime = ArchitectureRuntime(
        storage=InMemoryStorage()
    )

    runtime.initialize()

    assert isinstance(
        runtime.task_manager,
        PersistentTaskManager
    )

    runtime.shutdown()


def test_runtime_register_submit_execute():
    runtime = ArchitectureRuntime(
        storage=InMemoryStorage()
    )

    runtime.initialize()

    try:
        runtime.register_worker(
            "demo_worker",
            DemoWorker()
        )

        task = runtime.submit_task(
            "demo_worker",
            payload={"message": "hello"},
            priority=1
        )

        assert task["status"] == "PENDING"

        result = runtime.execute_task(
            task["task_id"]
        )

        assert result["status"] == "SUCCESS"

        saved = runtime.task_manager.get_task(
            task["task_id"]
        )

        assert saved["status"] == "SUCCESS"
        assert saved["completed_at"]

        assert runtime.metrics["tasks_completed"] == 1

    finally:
        runtime.shutdown()


def test_runtime_preserves_legacy_initializer_mode():
    from platform_core.architecture_initializer import ArchitectureInitializer
    from platform_core.task_queue.task_manager import TaskManager

    components = ArchitectureInitializer().initialize()

    assert isinstance(
        components["task_manager"],
        TaskManager
    )


def test_runtime_requires_initialization():
    runtime = ArchitectureRuntime()

    try:
        runtime.submit_task("demo_worker")
        assert False
    except RuntimeError:
        pass
