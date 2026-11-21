import importlib.util
import json
import re
import sys
import uuid

from pathlib import Path

from platform_core.contracts.base_worker import BaseWorker
from platform_core.plugin_system.worker_registry import WorkerRegistry
from platform_core.plugin_system.worker_manager import WorkerManager


class DynamicWorkerLoader:

    API_VERSION = "1.0"

    def __init__(
        self,
        worker_directory="plugins/workers",
        approved_worker_ids=None
    ):
        self.worker_directory = Path(worker_directory).resolve()

        self.registry = WorkerRegistry(
            str(self.worker_directory)
        )

        self.manager = WorkerManager()

        self.approved_worker_ids = set(
            approved_worker_ids or []
        )

        self.loaded_modules = {}
        self.errors = {}

    def discover(self):
        return self.registry.discover()

    def validate_manifest(self, manifest):

        required = [
            "id",
            "name",
            "version",
            "api_version",
            "entry_point",
            "enabled",
            "dependencies"
        ]

        errors = []

        for key in required:
            if key not in manifest:
                errors.append(f"Missing field: {key}")

        if errors:
            return {
                "valid": False,
                "errors": errors
            }

        if not re.fullmatch(
            r"[a-zA-Z0-9_.-]+",
            str(manifest["id"])
        ):
            errors.append("Invalid worker ID")

        if not re.fullmatch(
            r"\d+\.\d+\.\d+",
            str(manifest["version"])
        ):
            errors.append("Invalid worker version")

        if manifest["api_version"] != self.API_VERSION:
            errors.append("Unsupported worker API version")

        if not isinstance(manifest["enabled"], bool):
            errors.append("enabled must be boolean")

        if not isinstance(manifest["dependencies"], list):
            errors.append("dependencies must be a list")

        if not isinstance(manifest["entry_point"], str):
            errors.append("Invalid entry point")

        return {
            "valid": len(errors) == 0,
            "errors": errors
        }

    def _check_dependencies(self, dependencies):

        from importlib import metadata

        for dependency in dependencies:

            if not isinstance(dependency, str):
                raise ValueError(
                    "Invalid dependency declaration"
                )

            name = re.split(
                r"[<>=!~;\[]",
                dependency,
                1
            )[0].strip()

            if not name:
                raise ValueError("Invalid dependency name")

            try:
                metadata.version(name)
            except metadata.PackageNotFoundError:
                raise ValueError(
                    f"Dependency not installed: {name}"
                )

    def load(self, worker_id, context=None):

        if worker_id in self.manager.workers:
            raise ValueError("Worker already loaded")

        manifest = self.registry.get(worker_id)

        if not isinstance(manifest, dict):
            raise ValueError("Worker manifest not found")

        validation = self.validate_manifest(manifest)

        if not validation["valid"]:
            raise ValueError(
                f"Invalid manifest: {validation['errors']}"
            )

        if not manifest["enabled"]:
            raise PermissionError("Worker is disabled")

        if worker_id not in self.approved_worker_ids:
            raise PermissionError(
                "Worker approval required"
            )

        self._check_dependencies(
            manifest["dependencies"]
        )

        manifest_path = Path(
            manifest["_manifest_path"]
        ).resolve()

        worker_directory = manifest_path.parent

        module_name, class_name = (
            manifest["entry_point"].split(":", 1)
        )

        if not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_.]*",
            module_name
        ):
            raise ValueError("Invalid module path")

        if not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*",
            class_name
        ):
            raise ValueError("Invalid class name")

        module_path = (
            worker_directory /
            (module_name.replace(".", "/") + ".py")
        ).resolve()

        if not module_path.is_relative_to(
            worker_directory
        ):
            raise ValueError(
                "Module path escapes worker directory"
            )

        if not module_path.is_file():
            raise FileNotFoundError(
                f"Worker module not found: {module_path}"
            )

        unique_name = (
            f"dynamic_worker_{uuid.uuid4().hex}"
        )

        spec = importlib.util.spec_from_file_location(
            unique_name,
            module_path
        )

        if spec is None or spec.loader is None:
            raise ImportError(
                "Unable to load worker module"
            )

        module = importlib.util.module_from_spec(spec)

        sys.modules[unique_name] = module

        try:
            spec.loader.exec_module(module)

            worker_class = getattr(
                module,
                class_name,
                None
            )

            if not isinstance(worker_class, type):
                raise TypeError(
                    "Worker entry point must be a class"
                )

            if not issubclass(worker_class, BaseWorker):
                raise TypeError(
                    "Worker must inherit from BaseWorker"
                )

            worker = worker_class()

            if not isinstance(worker, BaseWorker):
                raise TypeError("Invalid worker instance")

            self.manager.register(worker_id, worker)

            try:
                self.manager.start(
                    worker_id,
                    context or {}
                )
            except Exception:
                self.manager.workers.pop(worker_id, None)
                self.manager.status.pop(worker_id, None)
                raise

            self.loaded_modules[worker_id] = unique_name

            return {
                "worker_id": worker_id,
                "status": "READY",
                "class": class_name
            }

        except Exception:
            sys.modules.pop(unique_name, None)
            raise

    def execute(self, worker_id, task):

        if worker_id not in self.manager.workers:
            raise ValueError("Worker is not loaded")

        return self.manager.execute(worker_id, task)

    def health_check(self, worker_id):

        if worker_id not in self.manager.workers:
            return False

        return self.manager.health_check(worker_id)

    def unload(self, worker_id):

        if worker_id not in self.manager.workers:
            return False

        try:
            self.manager.stop(worker_id)
        finally:
            self.manager.workers.pop(worker_id, None)
            self.manager.status.pop(worker_id, None)

            module_name = self.loaded_modules.pop(
                worker_id,
                None
            )

            if module_name:
                sys.modules.pop(module_name, None)

        return True

    def shutdown_all(self):

        results = {}

        for worker_id in list(self.manager.workers):

            try:
                results[worker_id] = self.unload(worker_id)

            except Exception as error:
                results[worker_id] = str(error)

        return results
