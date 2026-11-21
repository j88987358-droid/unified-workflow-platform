import json
from pathlib import Path

from platform_core.plugin_system.dynamic_loader import DynamicPluginLoader
from platform_core.plugin_system.dynamic_worker_loader import DynamicWorkerLoader
from platform_core.plugin_system.manager import PluginManager
from platform_core.plugin_system.registry import PluginRegistry


class WorkerHealthProbe:
    def __init__(self, manager, worker_id):
        self.manager = manager
        self.worker_id = worker_id

    def health_check(self):
        try:
            return self.manager.health_check(self.worker_id)
        except Exception:
            return False


class AutomaticRegistrar:

    def __init__(
        self,
        runtime,
        plugin_directory="plugins",
        worker_directory="plugins/workers",
        approval_file="config/registration-approvals.json"
    ):
        self.runtime = runtime
        self.plugin_directory = plugin_directory
        self.worker_directory = worker_directory
        self.approval_file = Path(approval_file)

        self.results = {
            "plugins": {},
            "workers": {},
            "errors": []
        }

        self._load_approvals()

    def _load_approvals(self):
        if not self.approval_file.exists():
            self.approvals = {
                "approved_plugin_ids": [],
                "approved_worker_ids": []
            }
            return

        data = json.loads(
            self.approval_file.read_text(encoding="utf-8")
        )

        if not isinstance(data, dict):
            raise ValueError("Invalid approval configuration")

        plugins = data.get("approved_plugin_ids", [])
        workers = data.get("approved_worker_ids", [])

        if not isinstance(plugins, list):
            raise ValueError("Plugin approvals must be a list")

        if not isinstance(workers, list):
            raise ValueError("Worker approvals must be a list")

        self.approvals = {
            "approved_plugin_ids": plugins,
            "approved_worker_ids": workers
        }

    def register_plugins(self, context=None):

        registry = PluginRegistry(self.plugin_directory)

        loader = DynamicPluginLoader(
            plugin_directory=self.plugin_directory,
            approved_ids=self.approvals["approved_plugin_ids"]
        )

        loader.discover()

        manager = PluginManager(registry)
        manager.registry = loader.registry

        for plugin_id in self.approvals["approved_plugin_ids"]:
            try:
                result = loader.load(plugin_id, context or {})

                instance = loader.instances[plugin_id]

                manager.register_instance(
                    plugin_id,
                    instance
                )

                self.results["plugins"][plugin_id] = result

            except Exception as error:
                self.results["errors"].append({
                    "component": "plugin",
                    "id": plugin_id,
                    "error": str(error)
                })

        self.plugin_loader = loader
        self.plugin_manager = manager

        return self.results["plugins"]

    def register_workers(self, context=None):

        loader = DynamicWorkerLoader(
            worker_directory=self.worker_directory,
            approved_worker_ids=self.approvals["approved_worker_ids"]
        )

        loader.discover()

        # Use the main ArchitectureRuntime WorkerManager.
        loader.manager = self.runtime.worker_manager

        for worker_id in self.approvals["approved_worker_ids"]:
            try:
                result = loader.load(
                    worker_id,
                    context or {}
                )

                probe = WorkerHealthProbe(
                    self.runtime.worker_manager,
                    worker_id
                )

                self.runtime.health_monitor.register(
                    f"worker:{worker_id}",
                    probe
                )

                self.results["workers"][worker_id] = result

            except Exception as error:
                self.results["errors"].append({
                    "component": "worker",
                    "id": worker_id,
                    "error": str(error)
                })

        self.worker_loader = loader

        return self.results["workers"]

    def register_all(self, context=None):

        if not self.runtime.initialized:
            raise RuntimeError(
                "ArchitectureRuntime must be initialized first"
            )

        self.register_plugins(context)
        self.register_workers(context)

        return self.report()

    def report(self):

        return {
            "plugin_count": len(self.results["plugins"]),
            "worker_count": len(self.results["workers"]),
            "error_count": len(self.results["errors"]),
            "plugins": self.results["plugins"],
            "workers": self.results["workers"],
            "errors": self.results["errors"]
        }

    def shutdown(self):

        results = {
            "plugins": {},
            "workers": {}
        }

        if hasattr(self, "plugin_loader"):
            results["plugins"] = (
                self.plugin_loader.shutdown_all()
            )

        if hasattr(self, "worker_loader"):
            results["workers"] = (
                self.worker_loader.shutdown_all()
            )

        return results
