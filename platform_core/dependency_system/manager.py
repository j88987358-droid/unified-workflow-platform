from importlib.metadata import version, PackageNotFoundError
from packaging.requirements import Requirement

class DependencyManager:
    def inspect(self, dependencies):
        results = []

        for item in dependencies:
            requirement = Requirement(item)
            try:
                installed = version(requirement.name)
                satisfied = requirement.specifier.contains(
                    installed, prereleases=True
                )
                status = "OK" if satisfied else "VERSION_MISMATCH"
            except PackageNotFoundError:
                installed = None
                status = "NOT_INSTALLED"

            results.append({
                "package": requirement.name,
                "required": str(requirement.specifier),
                "installed": installed,
                "status": status
            })

        return results

    def validate_manifest(self, manifest):
        dependencies = manifest.get("dependencies", [])
        if not isinstance(dependencies, list):
            raise ValueError("Plugin dependencies must be a list")

        return self.inspect(dependencies)
