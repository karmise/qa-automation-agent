"""Load local target settings without credentials or machine-specific code."""

import os
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parent


def load_settings() -> dict:
    """Read an optional TOML configuration and explicit environment overrides."""
    config_path = Path(os.environ.get("QA_AGENT_CONFIG", ROOT / "agent.toml"))
    config = tomllib.loads(config_path.read_text()) if config_path.exists() else {}
    project_value = os.environ.get("QA_PROJECT_PATH") or config.get("project_path")
    if not project_value:
        raise ValueError("Set project_path in agent.toml or set QA_PROJECT_PATH")
    project = Path(project_value).expanduser().resolve()
    python_value = os.environ.get("QA_PYTHON_PATH") or config.get("python_path")
    python = Path(python_value).expanduser().resolve() if python_value else project / ".venv/bin/python"
    timeout = config.get("timeout_seconds", 60)
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise ValueError("timeout_seconds must be an integer between 1 and 3600")
    return {"project": project, "python": python, "timeout": timeout}
