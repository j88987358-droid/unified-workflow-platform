import os
import uuid

from platform_core.architecture_initializer import ArchitectureInitializer
from platform_core.storage.memory_storage import InMemoryStorage
from platform_core.persistence.checkpoint_manager import CheckpointManager
from platform_core.persistence.state_loader import StateLoader
from platform_core.monitoring.health_monitor import HealthMonitor
from platform_core.monitoring.system_reporter import SystemReporter
from platform_core.orchestrator import ExecutionOrchestrator

from platform_core.task_queue.task_lifecycle_manager import TaskLifecycleManager
from platform_core.task_queue.retry_controller import RetryController
from platform_core.task_queue.recovery_controller import RecoveryController

from platform_core.execution.execution_engine import ExecutionEngine
from platform_core.execution.lease_manager import ExecutionLeaseManager


class WorkerHealthProbe:

    def __init__(self, worker_manager, worker_id):
        self.worker_manager = worker_manager
        self.worker_id = worker_id

    def health_check(self):
        try:
            return self.worker_manager.health_check(
                self.worker_id
            )
        except Exception:
            return False


class ArchitectureRuntime:

    def __init__(self, storage=None):
        self.storage = storage or InMemoryStorage()
        self.initialized = False

    def _create_lease_manager(self):
        run_id = os.environ.get(
            "GITHUB_RUN_ID",
            "local",
        )

        run_attempt = os.environ.get(
            "GITHUB_RUN_ATTEMPT",
            "1",
        )

        owner = (
            f"runner-{run_id}-"
            f"attempt-{run_attempt}-"
            f"{uuid.uuid4().hex}"
        )

        return ExecutionLeaseManager(
            storage=self.storage,
            lease_seconds=180,
            heartbeat_interval=60,
            owner=owner,
        )

    def initialize(self):
        if self.initialized:
            return self.components

        self.components = ArchitectureInitializer().initialize(
            task_storage=self.storage
        )

        self.worker_registry = self.components[
            "worker_registry"
        ]

        self.worker_manager = self.components[
            "worker_manager"
        ]

        self.task_manager = self.components[
            "task_manager"
        ]

        self.event_bus = self.components[
            "event_bus"
        ]

        self.checkpoints = CheckpointManager(
            self.storage,
            namespace="architecture",
        )

        self.state_loader = StateLoader(
            self.checkpoints
        )

        self.health_monitor = HealthMonitor()
        self.reporter = SystemReporter()

        self.lifecycle_manager = TaskLifecycleManager(
            self.task_manager
        )

        self.retry_controller = RetryController(
            self.task_manager
        )

        self.recovery_controller = RecoveryController(
            task_manager=self.task_manager,
            lifecycle_manager=self.lifecycle_manager,
            retry_controller=self.retry_controller,
        )

        self.execution_engine = ExecutionEngine(
            task_manager=self.task_manager,
            lifecycle_manager=self.lifecycle_manager,
            retry_controller=self.retry_controller,
            worker_manager=self.worker_manager,
            lease_manager_factory=self._create_lease_manager,
        )

        self.orchestrator = ExecutionOrchestrator(
            self.worker_manager,
            self.task_manager,
            self.checkpoints,
        )

        self.previous_state = self.state_loader.restore(
            "runtime"
        )

        self.metrics = (
            self.previous_state.get("metrics", {})
            if self.previous_state
            else {
                "tasks_completed": 0,
                "tasks_failed": 0
            }
        )

        self.initialized = True

        return self.components

    def register_worker(self, worker_id, worker, context=None):
        self._require_initialized()

        result = self.orchestrator.register_worker(
            worker_id,
            worker,
            context
        )

        probe = WorkerHealthProbe(
            self.worker_manager,
            worker_id
        )

        self.health_monitor.register(
            f"worker:{worker_id}",
            probe
        )

        return result

    def submit_task(self, worker_id, payload=None, priority=5):
        self._require_initialized()

        return self.orchestrator.create_task(
            worker_id,
            payload,
            priority
        )

    def execute_task(self, task_id):
        self._require_initialized()

        result = self.execution_engine.execute_task(
            task_id
        )

        if result["status"] == "SUCCESS":
            self.metrics["tasks_completed"] += 1
        else:
            self.metrics["tasks_failed"] += 1

        self.save_state()

        return result

    def run_once(self, max_tasks=100):
        self._require_initialized()

        recovery_results = (
            self.recovery_controller.recover_stale_tasks()
        )

        execution_results = self.execution_engine.run_once(
            max_tasks=max_tasks
        )

        return {
            "recovery_results": recovery_results,
            "execution_results": execution_results,
        }

    def save_state(self):
        self._require_initialized()

        state = {
            "metrics": self.metrics,
            "worker_ids": list(
                self.worker_manager.workers.keys()
            ),
        }

        return self.checkpoints.save(
            "runtime",
            state
        )

    def health_report(self):
        self._require_initialized()

        results = self.health_monitor.check_all()

        return self.reporter.generate(results)

    def shutdown(self):
        if not self.initialized:
            return

        self.save_state()

        for worker_id in list(
            self.worker_manager.workers.keys()
        ):
            if self.worker_manager.status.get(
                worker_id
            ) == "READY":
                self.worker_manager.stop(worker_id)

        self.initialized = False

    def _require_initialized(self):
        if not self.initialized:
            raise RuntimeError(
                "Architecture Runtime is not initialized"
            )
