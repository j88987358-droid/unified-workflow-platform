from platform_core.runtime import ArchitectureRuntime
from platform_core.storage.memory_storage import InMemoryStorage

class ExampleWorker:

    def initialize(self, context):
        self.ready = True

    def execute(self, task):
        return {
            "message": "Task completed",
            "input": task,
        }

    def health_check(self):
        return getattr(self, "ready", False)

    def shutdown(self):
        self.ready = False

def test_runtime_initialization():
    runtime = ArchitectureRuntime()
    runtime.initialize()

    assert runtime.initialized is True

    runtime.shutdown()

def test_worker_registration_and_execution():
    runtime = ArchitectureRuntime()
    runtime.initialize()

    runtime.register_worker(
        "example",
        ExampleWorker(),
    )

    task = runtime.submit_task(
        "example",
        {"value": 123},
    )

    result = runtime.execute_task(
        task["task_id"]
    )

    assert result["status"] == "SUCCESS"
    assert result["result"]["input"]["value"] == 123
    assert runtime.metrics["tasks_completed"] == 1

    runtime.shutdown()

def test_checkpoint_save():
    storage = InMemoryStorage()
    runtime = ArchitectureRuntime(storage=storage)

    runtime.initialize()
    runtime.metrics["tasks_completed"] = 5
    runtime.save_state()

    saved = runtime.checkpoints.load("runtime")

    assert saved["state"]["metrics"]["tasks_completed"] == 5

    runtime.shutdown()

def test_health_report():
    runtime = ArchitectureRuntime()
    runtime.initialize()

    runtime.register_worker(
        "example",
        ExampleWorker(),
    )

    report = runtime.health_report()

    assert report["total_components"] == 1
    assert report["healthy"] == 1

    runtime.shutdown()

def test_runtime_requires_initialization():
    runtime = ArchitectureRuntime()

    try:
        runtime.submit_task("example")
        assert False
    except RuntimeError:
        assert True

def test_failed_task_is_scheduled_for_retry():
    class BrokenWorker(ExampleWorker):
        def execute(self, task):
            raise ValueError("Test failure")

    runtime = ArchitectureRuntime()
    runtime.initialize()
    runtime.register_worker("broken", BrokenWorker())

    task = runtime.submit_task("broken")
    result = runtime.execute_task(task["task_id"])

    # Phase 3C introduced automatic retry scheduling. A worker error is
    # first recorded as FAILED in history, then moved to RETRY by policy.
    assert result["status"] == "RETRY"
    assert result["retry_count"] == 1
    assert runtime.metrics["tasks_failed"] == 1

    runtime.shutdown()


def test_worker_input_cannot_override_task_metadata():
    from platform_core.execution.execution_engine import ExecutionEngine

    task = {
        "task_id": "real-task-id",
        "status": "RUNNING",
        "payload": {
            "data": {
                "task_id": "forged-task-id",
                "status": "SUCCESS",
                "value": 123,
            }
        },
    }

    engine = ExecutionEngine(
        task_manager=object(),
        lifecycle_manager=object(),
        retry_controller=object(),
        worker_manager=object(),
    )
    worker_input = engine._worker_input(task)

    assert worker_input["value"] == 123
    assert worker_input["task_id"] == "real-task-id"
    assert worker_input["status"] == "RUNNING"
