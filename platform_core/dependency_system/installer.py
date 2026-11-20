import re
import subprocess
import sys
from packaging.requirements import Requirement

class SecureDependencyInstaller:

    def __init__(self, approved_packages):
        self.approved_packages = set(approved_packages)

    def validate(self, dependencies):

        validated = []

        for item in dependencies:
            requirement = Requirement(item)

            if requirement.name.lower() not in self.approved_packages:
                raise ValueError(
                    f"Package not approved: {requirement.name}"
                )

            if requirement.url:
                raise ValueError("Direct URLs are not allowed")

            if requirement.extras:
                raise ValueError("Package extras are not allowed")

            specifiers = list(requirement.specifier)

            if len(specifiers) != 1:
                raise ValueError(
                    "Only exact pinned versions are allowed"
                )

            specifier = specifiers[0]

            if specifier.operator != "==" or "*" in specifier.version:
                raise ValueError(
                    "Dependency must use an exact version pin"
                )

            if not re.fullmatch(
                r"\d+(?:\.\d+){1,3}",
                specifier.version
            ):
                raise ValueError("Invalid pinned version")

            validated.append(str(requirement))

        return validated

    def install(self, dependencies, approved=False):

        packages = self.validate(dependencies)

        if not approved:
            return {
                "installed": False,
                "status": "APPROVAL_REQUIRED",
                "packages": packages
            }

        if packages:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--",
                    *packages
                ],
                check=True
            )

        return {
            "installed": True,
            "status": "SUCCESS",
            "packages": packages
        }
