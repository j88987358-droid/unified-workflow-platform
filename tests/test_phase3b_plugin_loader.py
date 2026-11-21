import json
from pathlib import Path

import pytest

from platform_core.plugin_system.dynamic_loader import (
    DynamicPluginLoader
)

def create_plugin(root, enabled=True):
    plugin_dir = root / "example_plugin"
    plugin_dir.mkdir(parents=True)

    manifest = {
        "id": "example.collector",
        "name": "Example Collector",
        "version": "1.0.0",
        "api_version": "1.0",
        "entry_point": "main:ExamplePlugin",
        "enabled": enabled,
        "dependencies": [],
        "permissions": ["logging"]
    }

    (plugin_dir / "plugin.json").write_text(
        json.dumps(manifest),
        encoding="utf-8"
    )

    (plugin_dir / "main.py").write_text(
        '''
from platform_core.contracts.base_plugin import BasePlugin

class ExamplePlugin(BasePlugin):
    name = "Example Collector"
    version = "1.0.0"

    def initialize(self, context):
        self.context = context

    def health_check(self):
        return True

    def execute(self, task):
        return {"status": "success"}

    def shutdown(self):
        pass
''',
        encoding="utf-8"
    )

def create_loader(root, approved=True):
    plugin_root = root / "plugins"
    plugin_root.mkdir()

    create_plugin(plugin_root)

    approved_ids = (
        ["example.collector"] if approved else []
    )

    loader = DynamicPluginLoader(
        plugin_directory=str(plugin_root),
        approved_ids=approved_ids
    )

    loader.discover()
    return loader

def test_plugin_discovery(tmp_path):
    loader = create_loader(tmp_path)

    assert loader.registry.get(
        "example.collector"
    ) is not None

def test_approved_plugin_loads(tmp_path):
    loader = create_loader(tmp_path)

    result = loader.load(
        "example.collector",
        {"environment": "test"}
    )

    assert result["status"] == "LOADED"

def test_plugin_health_check(tmp_path):
    loader = create_loader(tmp_path)

    loader.load("example.collector")

    assert loader.health_check("example.collector") is True

def test_unapproved_plugin_rejected(tmp_path):
    loader = create_loader(tmp_path, approved=False)

    with pytest.raises(PermissionError):
        loader.load("example.collector")

def test_disabled_plugin_rejected(tmp_path):
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir()

    create_plugin(plugin_root, enabled=False)

    loader = DynamicPluginLoader(
        str(plugin_root),
        approved_ids=["example.collector"]
    )

    loader.discover()

    with pytest.raises(PermissionError):
        loader.load("example.collector")

def test_duplicate_plugin_rejected(tmp_path):
    loader = create_loader(tmp_path)

    loader.load("example.collector")

    with pytest.raises(ValueError):
        loader.load("example.collector")

def test_plugin_unload(tmp_path):
    loader = create_loader(tmp_path)

    loader.load("example.collector")

    assert loader.unload("example.collector") is True
    assert loader.health_check("example.collector") is False
