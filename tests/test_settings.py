from pathlib import Path

import pytest

from settings import load_settings


@pytest.fixture
def config(tmp_path, monkeypatch):
    path = tmp_path / "agent.toml"
    monkeypatch.setenv("QA_AGENT_CONFIG", str(path))
    monkeypatch.delenv("QA_PROJECT_PATH", raising=False)
    monkeypatch.delenv("QA_PYTHON_PATH", raising=False)
    return path


def test_missing_config_is_actionable(config):
    with pytest.raises(ValueError, match="QA_PROJECT_PATH"):
        load_settings()


def test_environment_overrides_config(config, monkeypatch, tmp_path):
    config.write_text('project_path = "/ignored"\ntimeout_seconds = 12\n')
    monkeypatch.setenv("QA_PROJECT_PATH", str(tmp_path))
    result = load_settings()
    assert result["project"] == tmp_path
    assert result["python"] == tmp_path / ".venv/bin/python"
    assert result["timeout"] == 12


@pytest.mark.parametrize("timeout", ["0", "true", "3601", '"60"'])
def test_invalid_timeout_is_rejected(config, timeout):
    config.write_text(f'project_path = "/target"\ntimeout_seconds = {timeout}\n')
    with pytest.raises(ValueError, match="timeout_seconds"):
        load_settings()
