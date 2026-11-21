import json
import re
from pathlib import Path

class PluginValidator:

    REQUIRED_FIELDS = {
        "id",
        "name",
        "version",
        "api_version",
        "enabled",
    }

    def validate_data(self, data):
        errors = []

        missing = self.REQUIRED_FIELDS - set(data)

        if missing:
            errors.append(
                f"Missing fields: {sorted(missing)}"
            )

        plugin_id = data.get("id")

        if plugin_id is not None:
            if not isinstance(plugin_id, str) or not re.fullmatch(
                r"[a-z0-9][a-z0-9_-]*",
                plugin_id
            ):
                errors.append("Invalid plugin id")

        if not isinstance(data.get("enabled"), bool):
            errors.append("enabled must be boolean")

        for field in (
            "name",
            "version",
            "api_version"
        ):
            if field in data and not isinstance(
                data[field], str
            ):
                errors.append(
                    f"{field} must be a string"
                )

        for field in ("dependencies", "permissions"):
            if field in data and not isinstance(
                data[field], list
            ):
                errors.append(
                    f"{field} must be a list"
                )

        return {
            "valid": not errors,
            "errors": errors,
        }

    def validate_file(self, filepath):
        path = Path(filepath)

        try:
            data = json.loads(
                path.read_text(encoding="utf-8")
            )

            return self.validate_data(data)

        except Exception as exc:
            return {
                "valid": False,
                "errors": [str(exc)],
            }
