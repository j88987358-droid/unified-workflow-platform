from importlib.metadata import (
    PackageNotFoundError,
    version,
)
from packaging.specifiers import SpecifierSet
from packaging.version import Version

class DependencyValidator:

    def validate(self, dependencies):
        results = []

        for name, required in dependencies.items():
            try:
                installed = version(name)

                compatible = (
                    not required
                    or Version(installed) in
                    SpecifierSet(required)
                )

                results.append({
                    "package": name,
                    "installed_version": installed,
                    "required_version": required,
                    "status": (
                        "COMPATIBLE"
                        if compatible
                        else "INCOMPATIBLE"
                    ),
                })

            except PackageNotFoundError:
                results.append({
                    "package": name,
                    "required_version": required,
                    "status": "MISSING",
                })

            except Exception as exc:
                results.append({
                    "package": name,
                    "status": "ERROR",
                    "error": str(exc),
                })

        return {
            "valid": all(
                item["status"] == "COMPATIBLE"
                for item in results
            ),
            "results": results,
        }
