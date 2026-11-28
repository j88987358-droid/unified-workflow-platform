from datetime import datetime, timezone, timedelta
import time

import pytest

from platform_core.execution.execution_engine import ExecutionEngine
from platform_core.execution.lease_manager import ExecutionLeaseManager
from platform_core.orchestrator import ExecutionOrchestrator
from platform_core.runtime import ArchitectureRuntime
from platform_core.storage.memory_storage import InMemoryStorage
from platform_core.task_queue.persistent_task_manager import PersistentTaskManager
from platform_core.task_queue.task_lifecycle_manager import TaskLifecycleManager
from platform_core.task_queue.retry_controller import RetryController
from platform_core.task_queue.recovery_controller import RecoveryController


class LeaseUnavailable:
    def start(self, task_id):
        raise RuntimeError("LEASE_ALREADY_HELD")


class FakeLeaseStorage:
    def __init__(self, result=None, error=None):
        self.result = result or {"success": True, "active": False}
        self.error = error
        self.calls = []

    def lease_inspect(self, task_id):
        self.calls.append(task_id)
        if self.error:
            raise self.error
        return self.result


def make_engine(storage=None, lease_factory=None):
    storage = storage or InMemoryStorage()
    manager = PersistentTaskManager(storage)
    lifecycle = TaskLifecycleManager(manager)
    retry = RetryController(manager, base_delay_seconds=1)

    class WorkerManager:
        workers = {"demo": object()}
        status = {"demo": "READY"}

        def start(self, worker_id):
            self.status[worker_id] = "READY"

        def health_check(self, worker_id):
            return True

        def execute(self, worker_id, task):
            return {"echo": task.get("value")}

    engine = ExecutionEngine(
        task_manager=manager,
        lifecycle_manager=lifecycle,
        retry_controller=retry,
        worker_manager=WorkerManager(),
        lease_manager_factory=lease_factory,
    )
    return storage, manager, lifecycle, retry, engine


def test_local_storage_lease_rejects_other_owner_and_inspects_state():
    storage = InMemoryStorage()
    first = storage.lease_start("task-1", "runner-a", 30)
    assert first["success"] is True
    assert storage.lease_start("task-1", "runner-b", 30)["error"] == "LEASE_ALREADY_HELD"
    inspected = storage.lease_inspect("task-1")
    assert inspected["active"] is True
    assert inspected["owner"] == "runner-a"
    assert storage.lease_release("task-1", "runner-a")["released"] is True
    assert storage.lease_inspect("task-1")["active"] is False


def test_local_storage_atomic_update_does_not_lose_threaded_increments():
    import threading

    storage = InMemoryStorage()
    storage.set("counter", {"value": 0})

    def increment():
        for _ in range(100):
            storage.atomic_update(
                "counter",
                lambda current: {"value": current["value"] + 1},
            )

    threads = [threading.Thread(target=increment) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert storage.get("counter")["value"] == 800


def test_runtime_defaults_to_separate_storage_interfaces_in_local_mode():
    runtime = ArchitectureRuntime()
    assert runtime.task_storage is runtime.lease_storage
    assert runtime.storage is runtime.task_storage


def test_runtime_accepts_separate_task_and_lease_storage():
    task_storage = InMemoryStorage()
    lease_storage = InMemoryStorage()
    runtime = ArchitectureRuntime(task_storage=task_storage, lease_storage=lease_storage)
    assert runtime.task_storage is task_storage
    assert runtime.lease_storage is lease_storage


def test_runtime_rejects_ambiguous_legacy_and_task_storage_arguments():
    with pytest.raises(ValueError, match="either storage or task_storage"):
        ArchitectureRuntime(storage=InMemoryStorage(), task_storage=InMemoryStorage())


def test_execution_lease_failure_does_not_mark_pending_task_running():
    storage, manager, lifecycle, retry, engine = make_engine(
        lease_factory=lambda: LeaseUnavailable()
    )
    task = manager.create_task("demo", payload={"worker_id": "demo", "value": 5})

    result = engine.execute_task(task["task_id"])

    assert result["status"] == "LEASE_UNAVAILABLE"
    assert manager.get_task(task["task_id"])["status"] == "PENDING"


def test_execution_engine_acquires_lease_before_running_transition():
    storage, manager, lifecycle, retry, engine = make_engine()
    task = manager.create_task("demo", payload={"worker_id": "demo", "value": 5})
    seen = {}

    class InspectingLease:
        def start(self, task_id):
            seen["status_at_acquire"] = manager.get_task(task_id)["status"]

        def check(self):
            return True

        def stop(self):
            return None

        def release(self):
            return {"released": True}

    engine.lease_manager_factory = InspectingLease
    result = engine.execute_task(task["task_id"])

    assert seen["status_at_acquire"] == "PENDING"
    assert result["status"] == "SUCCESS"


def test_execution_engine_processes_due_retries_through_lease_path():
    storage, manager, lifecycle, retry, engine = make_engine(
        lease_factory=lambda: LeaseUnavailable()
    )
    task = manager.create_task("demo", payload={"worker_id": "demo"})
    lifecycle.mark_running(task["task_id"])
    lifecycle.mark_failed(task["task_id"], {"error": "temporary"})
    retry.handle_failure(task["task_id"])
    retry.clock = lambda: datetime.now(timezone.utc) + timedelta(seconds=10)

    results = engine.process_due_retries()

    assert len(results) == 1
    assert results[0]["status"] == "LEASE_UNAVAILABLE"
    assert manager.get_task(task["task_id"])["status"] == "RETRY"


def test_recovery_uses_authoritative_active_lease_even_without_task_metadata():
    storage, manager, lifecycle, retry, engine = make_engine()
    task = manager.create_task("demo")
    lifecycle.mark_running(task["task_id"])
    lease_storage = FakeLeaseStorage({"success": True, "active": True, "owner": "runner-x"})
    recovery = RecoveryController(manager, lifecycle, retry, stale_after_seconds=1, lease_storage=lease_storage)

    assert recovery.has_active_lease(manager.get_task(task["task_id"])) is True
    assert lease_storage.calls == [task["task_id"]]


def test_recovery_fails_safe_when_authoritative_lease_check_errors():
    storage, manager, lifecycle, retry, engine = make_engine()
    task = manager.create_task("demo")
    lifecycle.mark_running(task["task_id"])
    lease_storage = FakeLeaseStorage(error=RuntimeError("backend unavailable"))
    recovery = RecoveryController(manager, lifecycle, retry, stale_after_seconds=1, lease_storage=lease_storage)

    assert recovery.has_active_lease(manager.get_task(task["task_id"])) is True


def test_recovery_uses_backend_absence_over_stale_task_lease_metadata():
    storage, manager, lifecycle, retry, engine = make_engine()
    task = manager.create_task("demo")
    lifecycle.mark_running(task["task_id"])
    current = manager.get_task(task["task_id"])
    current["lease_status"] = "ACTIVE"
    current["lease_expires_at"] = "2099-01-01T00:00:00+00:00"
    lease_storage = FakeLeaseStorage({"success": True, "active": False})
    recovery = RecoveryController(manager, lifecycle, retry, stale_after_seconds=1, lease_storage=lease_storage)

    assert recovery.has_active_lease(current) is False


def test_orchestrator_delegates_to_execution_engine_only():
    class Engine:
        def execute_task(self, task_id):
            return {"task_id": task_id, "status": "SUCCESS"}

    orchestrator = ExecutionOrchestrator(object(), object(), object(), execution_engine=Engine())
    assert orchestrator.execute_task("task-9")["status"] == "SUCCESS"


def test_orchestrator_without_engine_cannot_execute_worker_directly():
    orchestrator = ExecutionOrchestrator(object(), object(), object())
    with pytest.raises(RuntimeError, match="direct worker execution is disabled"):
        orchestrator.execute_task("task-9")


def test_lease_manager_rejects_storage_without_lease_contract():
    with pytest.raises(TypeError, match="missing required methods"):
        ExecutionLeaseManager(object())


def test_local_lease_expires_and_can_be_acquired_by_another_owner():
    storage = InMemoryStorage()
    assert storage.lease_start("task-exp", "runner-old", 0.01)["success"] is True
    time.sleep(0.03)
    result = storage.lease_start("task-exp", "runner-new", 30)
    assert result["success"] is True
    assert storage.lease_inspect("task-exp")["owner"] == "runner-new"


def test_runtime_requires_lease_storage_for_task_storage_without_lease_api():
    class TaskOnlyStorage:
        def get(self, key):
            return None
        def set(self, key, value):
            return True
        def delete(self, key):
            return True

    runtime = ArchitectureRuntime(task_storage=TaskOnlyStorage())
    with pytest.raises(RuntimeError, match="Lease storage is missing required methods"):
        runtime.initialize()


def test_two_local_runners_cannot_execute_the_same_task_twice():
    import threading
    from concurrent.futures import ThreadPoolExecutor

    storage = InMemoryStorage()
    manager_a = PersistentTaskManager(storage)
    manager_b = PersistentTaskManager(storage)
    lifecycle_a = TaskLifecycleManager(manager_a)
    lifecycle_b = TaskLifecycleManager(manager_b)
    retry_a = RetryController(manager_a, base_delay_seconds=1)
    retry_b = RetryController(manager_b, base_delay_seconds=1)
    counter = {"executions": 0}
    counter_lock = threading.Lock()

    class WorkerManager:
        workers = {"demo": object()}
        status = {"demo": "READY"}

        def start(self, worker_id):
            self.status[worker_id] = "READY"

        def health_check(self, worker_id):
            return True

        def execute(self, worker_id, task):
            with counter_lock:
                counter["executions"] += 1
            time.sleep(0.05)
            return {"ok": True}

    workers = WorkerManager()
    def make_runner(manager, lifecycle, retry):
        return ExecutionEngine(
            manager, lifecycle, retry, workers,
            lease_manager_factory=lambda: ExecutionLeaseManager(
                storage, lease_seconds=30, heartbeat_interval=10
            ),
        )

    engine_a = make_runner(manager_a, lifecycle_a, retry_a)
    engine_b = make_runner(manager_b, lifecycle_b, retry_b)
    task = manager_a.create_task("demo", payload={"worker_id": "demo"})
    barrier = threading.Barrier(2)

    def run(engine):
        barrier.wait()
        return engine.execute_task(task["task_id"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, (engine_a, engine_b)))

    assert counter["executions"] == 1
    assert sorted(result["status"] for result in results) == ["LEASE_UNAVAILABLE", "SUCCESS"]


def test_separate_runtime_storages_are_wired_to_the_correct_components():
    task_storage = InMemoryStorage()
    lease_storage = InMemoryStorage()
    runtime = ArchitectureRuntime(task_storage=task_storage, lease_storage=lease_storage)
    runtime.initialize()
    try:
        assert runtime.task_manager.storage is task_storage
        assert runtime.checkpoints.storage is task_storage
        assert runtime.recovery_controller.lease_storage is lease_storage
        assert runtime._create_lease_manager().storage is lease_storage
    finally:
        runtime.shutdown()


def test_persistent_task_manager_mutations_are_atomic_across_instances():
    from concurrent.futures import ThreadPoolExecutor

    storage = InMemoryStorage()
    managers = [PersistentTaskManager(storage) for _ in range(4)]

    def create_batch(index):
        manager = managers[index]
        return [manager.create_task(f"worker-{index}") for _ in range(25)]

    with ThreadPoolExecutor(max_workers=4) as pool:
        batches = list(pool.map(create_batch, range(4)))

    created_ids = {task["task_id"] for batch in batches for task in batch}
    persisted_ids = {task["task_id"] for task in managers[0].list_tasks()}
    assert len(created_ids) == 100
    assert persisted_ids == created_ids


def test_concurrent_lifecycle_transition_allows_only_one_running_claim():
    from concurrent.futures import ThreadPoolExecutor

    storage = InMemoryStorage()
    manager_a = PersistentTaskManager(storage)
    manager_b = PersistentTaskManager(storage)
    lifecycle_a = TaskLifecycleManager(manager_a)
    lifecycle_b = TaskLifecycleManager(manager_b)
    task = manager_a.create_task("demo")

    def mark_running(lifecycle):
        try:
            return lifecycle.mark_running(task["task_id"])["status"]
        except ValueError:
            return "REJECTED"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(mark_running, (lifecycle_a, lifecycle_b)))

    assert sorted(results) == ["REJECTED", "RUNNING"]
    assert manager_a.get_task(task["task_id"])["status"] == "RUNNING"


def test_runtime_rejects_lease_adapter_without_authoritative_inspection():
    class LeaseAdapterWithoutInspect:
        def lease_start(self, *args, **kwargs): return {"success": True, "valid": True}
        def lease_heartbeat(self, *args, **kwargs): return {"success": True, "valid": True}
        def lease_check(self, *args, **kwargs): return {"success": True, "valid": True}
        def lease_release(self, *args, **kwargs): return {"success": True, "released": True}

    runtime = ArchitectureRuntime(
        task_storage=InMemoryStorage(),
        lease_storage=LeaseAdapterWithoutInspect(),
    )
    with pytest.raises(RuntimeError, match="lease_inspect"):
        runtime.initialize()
