import json

import pytest

from platform_core.runtime import ArchitectureRuntime
from platform_core.plugin_system.auto_registrar import AutomaticRegistrar


def test_empty_approval_registration(tmp_path):

    approval_file = tmp_path / "approvals.json"

    approval_file.write_text(
        json.dumps({
            "approved_plugin_ids": [],
            "approved_worker_ids": []
        }),
        encoding="utf-8"
    )

    runtime = ArchitectureRuntime()
    runtime.initialize()

    registrar = AutomaticRegistrar(
        runtime=runtime,
        plugin_directory=str(tmp_path / "plugins"),
        worker_directory=str(tmp_path / "workers"),
        approval_file=str(approval_file)
    )

    report = registrar.register_all()

    assert report["plugin_count"] == 0
    assert report["worker_count"] == 0
    assert report["error_count"] == 0

    runtime.shutdown()


def test_registration_requires_initialized_runtime(tmp_path):

    approval_file = tmp_path / "approvals.json"

    approval_file.write_text(
        json.dumps({
            "approved_plugin_ids": [],
            "approved_worker_ids": []
        }),
        encoding="utf-8"
    )

    runtime = ArchitectureRuntime()

    registrar = AutomaticRegistrar(
        runtime=runtime,
        approval_file=str(approval_file)
    )

    with pytest.raises(RuntimeError):
        registrar.register_all()


def test_invalid_approval_configuration(tmp_path):

    approval_file = tmp_path / "approvals.json"

    approval_file.write_text(
        json.dumps({
            "approved_plugin_ids": "invalid",
            "approved_worker_ids": []
        }),
        encoding="utf-8"
    )

    runtime = ArchitectureRuntime()
    runtime.initialize()

    with pytest.raises(ValueError):
        AutomaticRegistrar(
            runtime=runtime,
            approval_file=str(approval_file)
        )

    runtime.shutdown()


def test_registration_report_structure(tmp_path):

    approval_file = tmp_path / "approvals.json"

    approval_file.write_text(
        json.dumps({
            "approved_plugin_ids": [],
            "approved_worker_ids": []
        }),
        encoding="utf-8"
    )

    runtime = ArchitectureRuntime()
    runtime.initialize()

    registrar = AutomaticRegistrar(
        runtime=runtime,
        approval_file=str(approval_file)
    )

    report = registrar.register_all()

    assert "plugins" in report
    assert "workers" in report
    assert "errors" in report

    runtime.shutdown()
