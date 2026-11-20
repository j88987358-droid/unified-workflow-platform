import re

class PluginManifestValidator:

    REQUIRED = [
        "id",
        "name",
        "version",
        "api_version",
        "entry_point",
        "enabled",
        "dependencies",
        "permissions"
    ]

    ALLOWED_PERMISSIONS = {
        "network",
        "storage",
        "logging"
    }

    def validate(self, manifest):

        errors = []

        for key in self.REQUIRED:
            if key not in manifest:
                errors.append(f"Missing field: {key}")

        if errors:
            return {"valid": False, "errors": errors}

        if not re.fullmatch(
            r"[a-zA-Z0-9_.-]+",
            str(manifest["id"])
        ):
            errors.append("Invalid plugin ID")

        if not re.fullmatch(
            r"\d+\.\d+\.\d+",
            str(manifest["version"])
        ):
            errors.append("Invalid plugin version")

        if manifest["api_version"] != "1.0":
            errors.append("Unsupported plugin API version")

        if not isinstance(manifest["enabled"], bool):
            errors.append("enabled must be boolean")

        if not isinstance(manifest["dependencies"], list):
            errors.append("dependencies must be a list")

        if not isinstance(manifest["permissions"], list):
            errors.append("permissions must be a list")

        if isinstance(manifest["permissions"], list):
            for permission in manifest["permissions"]:
                if permission not in self.ALLOWED_PERMISSIONS:
                    errors.append(
                        f"Permission not allowed: {permission}"
                    )

        if not isinstance(manifest["entry_point"], str):
            errors.append("Invalid entry point")

        return {
            "valid": len(errors) == 0,
            "errors": errors
        }
