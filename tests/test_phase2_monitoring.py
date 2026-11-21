import json

from platform_core.monitoring.health_monitor import HealthMonitor
from platform_core.monitoring.system_reporter import SystemReporter
from platform_core.validation.plugin_validator import PluginValidator
from platform_core.validation.dependency_validator import DependencyValidator

def test_health_monitor():
    monitor = HealthMonitor()
    monitor.register("database", lambda: True)

    class Healthy:
        def health_check(self):
            return True

    monitor.register("worker", Healthy())

    results = monitor.check_all()

    assert len(results) == 2
    assert results[1]["status"] == "HEALTHY"

def test_unknown_component():
    monitor = HealthMonitor()
    assert monitor.check("missing")["status"] == "UNKNOWN"

def test_system_reporter():
    reporter = SystemReporter()

    report = reporter.generate([
        {"name": "database", "status": "HEALTHY"},
        {"name": "worker", "status": "HEALTHY"},
    ])

    assert report["overall_status"] == "HEALTHY"
    assert report["healthy"] == 2

def test_degraded_report():
    report = SystemReporter().generate([
        {"name": "worker", "status": "ERROR"}
    ])

    assert report["overall_status"] == "DEGRADED"

def test_valid_plugin():
    validator = PluginValidator()

    data = {
        "id": "reddit_collector",
        "name": "Reddit Collector",
        "version": "1.0.0",
        "api_version": "1.0",
        "enabled": True,
        "dependencies": [],
        "permissions": ["network"],
    }

    assert validator.validate_data(data)["valid"]

def test_invalid_plugin():
    validator = PluginValidator()

    result = validator.validate_data({
        "id": "INVALID ID",
        "enabled": "yes",
    })

    assert not result["valid"]

def test_plugin_file(tmp_path):
    validator = PluginValidator()

    path = tmp_path / "plugin.json"
    path.write_text(json.dumps({
        "id": "test_plugin",
        "name": "Test",
        "version": "1.0.0",
        "api_version": "1.0",
        "enabled": True,
    }))

    assert validator.validate_file(path)["valid"]

def test_dependency_validator():
    result = DependencyValidator().validate({
        "packaging": ">=20"
    })

    assert result["valid"]
