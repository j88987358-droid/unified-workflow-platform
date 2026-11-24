from platform_core.plugin_system.worker_registry import WorkerRegistry
from platform_core.plugin_system.worker_manager import WorkerManager
from platform_core.task_queue.task_manager import TaskManager
from platform_core.task_queue.persistent_task_manager import PersistentTaskManager
from platform_core.event_system.event_bus import EventBus


class ArchitectureInitializer:

    def initialize(self, task_storage=None):
        registry = WorkerRegistry()
        manager = WorkerManager()

        if task_storage is not None:
            tasks = PersistentTaskManager(task_storage)
        else:
            tasks = TaskManager()

        events = EventBus()

        registry.discover()

        return {
            "worker_registry": registry,
            "worker_manager": manager,
            "task_manager": tasks,
            "event_bus": events
        }
