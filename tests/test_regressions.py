"""Regression checks for boundaries exposed by the architecture review."""

import importlib
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from qa_agent import allure, runner, storage
from qa_agent.settings import load_settings


def test_timeout_preserves_partial_output():
    with patch(
        "qa_agent.runner.subprocess.run",
        side_effect=subprocess.TimeoutExpired(
            cmd=["pytest"], timeout=60, output=b"partial output\xff", stderr=b"diagnostic"
        ),
    ):
        result = runner.run_unit_tests()
    assert result["status"] == "timeout"
    assert result["stdout"] == "partial output\ufffd"
    assert result["stderr"] == "diagnostic"


@pytest.mark.parametrize("value", ["123", "true", '""', "[]"])
def test_malformed_project_setting_is_a_launch_error(value, tmp_path, monkeypatch):
    config = tmp_path / "agent.toml"
    config.write_text(f"project_path = {value}\n")
    monkeypatch.setenv("QA_AGENT_CONFIG", str(config))
    monkeypatch.delenv("QA_PROJECT_PATH", raising=False)
    monkeypatch.setattr(runner, "load_settings", load_settings)
    with patch("qa_agent.runner.subprocess.run") as execute:
        result = runner.run_unit_tests()
    assert result["status"] == "launch_error"
    assert "path string" in result["error"]
    execute.assert_not_called()


def test_relative_paths_are_based_on_config_and_keep_interpreter_symlinks(tmp_path, monkeypatch):
    config = tmp_path / "agent.toml"
    interpreter = tmp_path / "python-link"
    interpreter.symlink_to("/usr/bin/python3")
    config.write_text('project_path = "framework"\npython_path = "python-link"\n')
    monkeypatch.setenv("QA_AGENT_CONFIG", str(config))
    monkeypatch.delenv("QA_PROJECT_PATH", raising=False)
    monkeypatch.delenv("QA_PYTHON_PATH", raising=False)
    settings = load_settings()
    assert settings.project == tmp_path / "framework"
    assert settings.python == interpreter


def test_unreadable_allure_directory_is_not_reported_as_empty():
    with patch("pathlib.Path.iterdir", side_effect=PermissionError("Access denied")):
        result = allure.read_allure_failures("a" * 32)
    assert result["status"] == "read_error"
    assert "Access denied" in result["error"]


def test_summary_replacement_failure_keeps_previous_summary_and_cleans_temporary_file():
    summary = {"run_id": "b" * 32, "status": "passed", "report": "original"}
    storage.save_summary(summary)
    original_replace = Path.replace

    def fail_summary(source, destination):
        if Path(destination).name == "summary.json":
            raise OSError("Disk failure")
        return original_replace(source, destination)

    with patch("pathlib.Path.replace", autospec=True, side_effect=fail_summary):
        with pytest.raises(OSError, match="Disk failure"):
            storage.save_summary({**summary, "report": "changed"})
    assert storage.read_summary(summary["run_id"]) == summary
    assert not list(storage.run_directory(summary["run_id"]).glob(".*"))


@pytest.mark.parametrize(
    "data",
    [
        [],
        {"run_id": "d" * 32},
        {"run_id": "c" * 32, "report": 12},
        {"run_id": "c" * 32, "report": "bad", "status": []},
    ],
)
def test_invalid_summary_is_rejected(data):
    folder = storage.run_directory("c" * 32)
    folder.mkdir(parents=True)
    (folder / "summary.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Invalid saved summary"):
        storage.read_summary("c" * 32)


def test_learning_examples_are_safe_to_import():
    with patch("qa_agent.runner.subprocess.run") as execute:
        for module in ("try_runner", "try_allure", "try_graph", "qa", "server"):
            importlib.import_module(module)
    execute.assert_not_called()


def test_runner_uses_configured_interpreter_timeout_and_unique_directories(tmp_path, monkeypatch):
    from qa_agent.settings import Settings

    settings = Settings(
        project=tmp_path / "target project", python=tmp_path / "venv/bin/python", timeout=17
    )
    monkeypatch.setattr(runner, "load_settings", lambda: settings)
    with patch(
        "qa_agent.runner.subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, "1 passed", ""),
    ) as execute:
        first = runner.run_unit_tests()
        second = runner.run_unit_tests()
    assert first["run_id"] != second["run_id"]
    assert execute.call_count == 2
    for call, result in zip(execute.call_args_list, (first, second), strict=True):
        command = call.args[0]
        folder = storage.run_directory(result["run_id"]) / "allure-results"
        assert command == [
            str(settings.python),
            "-m",
            "pytest",
            "tests/unit",
            "-q",
            f"--alluredir={folder}",
        ]
        assert folder.is_dir()
        assert call.kwargs["cwd"] == settings.project
        assert call.kwargs["timeout"] == 17
        assert not call.kwargs.get("shell", False)


def test_summary_rejects_run_directory_pointing_outside_storage(tmp_path):
    storage.RUNS_DIR.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (storage.RUNS_DIR / ("f" * 32)).symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes"):
        storage.read_summary("f" * 32)
