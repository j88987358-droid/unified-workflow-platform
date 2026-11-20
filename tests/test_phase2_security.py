import json

from pathlib import Path

from platform_core.plugin_system.validator import (
    PluginManifestValidator
)

from platform_core.plugin_system.compatibility import (
    PluginCompatibilityChecker
)

from platform_core.dependency_system.installer import (
    SecureDependencyInstaller
)

def valid_manifest():
    return {
        "id": "example.collector",
        "name": "Example Collector",
        "version": "1.0.0",
        "api_version": "1.0",
        "entry_point": "example:Plugin",
        "enabled": False,
        "dependencies": [],
        "permissions": ["network"]
    }

def test_valid_manifest():
    result = PluginManifestValidator().validate(valid_manifest())
    assert result["valid"] is True

def test_invalid_permission():
    manifest = valid_manifest()
    manifest["permissions"] = ["system_access"]

    result = PluginManifestValidator().validate(manifest)
    assert result["valid"] is False

def test_api_compatibility():
    result = PluginCompatibilityChecker().check(valid_manifest())
    assert result["compatible"] is True

def test_incompatible_api():
    manifest = valid_manifest()
    manifest["api_version"] = "9.0"

    result = PluginCompatibilityChecker().check(manifest)
    assert result["compatible"] is False

def test_dependency_requires_approval():
    installer = SecureDependencyInstaller(["packaging"])

    result = installer.install(
        ["packaging==25.0"],
        approved=False
    )

    assert result["status"] == "APPROVAL_REQUIRED"
    assert result["installed"] is False

def test_unapproved_dependency():
    installer = SecureDependencyInstaller(["packaging"])

    try:
        installer.validate(["unknown-package==1.0"])
    except ValueError:
        return

    assert False, "Unapproved package was accepted"

def test_approved_package_config():
    config = json.loads(
        Path("config/approved-dependencies.json").read_text()
    )

    assert "packaging" in config["approved_packages"]
