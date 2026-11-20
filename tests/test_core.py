import json
from pathlib import Path

from platform_core.plugin_system.registry import PluginRegistry
from platform_core.environment.manager import EnvironmentManager
from platform_core.configuration.manager import ConfigurationManager

def test_environment_manager():
    result = EnvironmentManager().inspect()
    assert "python_version" in result

def test_configuration_manager():
    config = ConfigurationManager().load()
    assert config["plugin_api_version"] == "1.0"

def test_plugin_discovery(tmp_path):
    plugin_dir = tmp_path / "plugins" / "example"
    plugin_dir.mkdir(parents=True)

    manifest = {
        "id": "example.collector",
        "name": "Example Collector",
        "version": "1.0.0",
        "api_version": "1.0",
        "entry_point": "example:Plugin",
        "enabled": False,
        "dependencies": []
    }

    (plugin_dir / "plugin.json").write_text(json.dumps(manifest))

    registry = PluginRegistry(str(tmp_path / "plugins"))
    found = registry.discover()

    assert len(found) == 1
    assert registry.get("example.collector") is not None
