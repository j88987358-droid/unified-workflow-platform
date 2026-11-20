import json
from pathlib import Path

class PluginRegistry:
    def __init__(self, plugin_directory="plugins"):
        self.plugin_directory = Path(plugin_directory)
        self.plugins = {}

    def discover(self):
        if not self.plugin_directory.exists():
            return []

        discovered = []

        for manifest in self.plugin_directory.rglob("plugin.json"):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))

                required = ("id", "name", "version", "api_version")
                if not all(data.get(key) for key in required):
                    continue

                plugin_id = data["id"]
                if plugin_id in self.plugins:
                    continue

                data["_manifest_path"] = str(manifest)
                self.plugins[plugin_id] = data
                discovered.append(data)

            except (OSError, json.JSONDecodeError):
                continue

        return discovered

    def get(self, plugin_id):
        return self.plugins.get(plugin_id)

    def list_plugins(self):
        return list(self.plugins.values())
