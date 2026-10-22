import pytest

from qa_agent.settings import load_settings


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
    assert result.project == tmp_path
    assert result.python == tmp_path / ".venv/bin/python"
    assert result.timeout == 12


@pytest.mark.parametrize("timeout", ["0", "true", "3601", '"60"'])
def test_invalid_timeout_is_rejected(config, timeout):
    config.write_text(f'project_path = "/target"\ntimeout_seconds = {timeout}\n')
    with pytest.raises(ValueError, match="timeout_seconds"):
        load_settings()


def test_defaults_allow_api_and_ui_suites_and_disable_the_model(config):
    config.write_text('project_path = "/target"\n')
    result = load_settings()
    assert result.timeout == 900
    assert result.env == {}
    assert result.llm_command == ()


def test_environment_table_and_model_command(config):
    config.write_text(
        'project_path = "/target"\n'
        'llm_command = ["claude", "-p", "--tools", ""]\n'
        "llm_timeout_seconds = 30\n"
        '[env]\nRBP_BASE_URL = "http://127.0.0.1:8765"\n'
    )
    result = load_settings()
    assert result.env == {"RBP_BASE_URL": "http://127.0.0.1:8765"}
    assert result.llm_command == ("claude", "-p", "--tools", "")
    assert result.llm_timeout == 30


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ('llm_command = "claude -p"', "llm_command"),
        ('llm_command = ["", "-p"]', "llm_command"),
        ("llm_command = []", "llm_command"),
        ('env = { lower = "x" }', "env"),
        ("env = { RBP_BASE_URL = 1 }", "env"),
    ],
)
def test_invalid_environment_or_model_command_is_rejected(config, line, message):
    """A shell string is refused: the command must be an argument list."""
    config.write_text(f'project_path = "/target"\n{line}\n')
    with pytest.raises(ValueError, match=message):
        load_settings()
