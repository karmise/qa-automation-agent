"""Validated configuration with stable path resolution and environment overrides."""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    """Immutable configuration for one execution."""

    project: Path
    python: Path
    timeout: int = 60


def _path(value: object, name: str, base: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty path string")
    path = Path(value).expanduser()
    # Do not resolve interpreter symlinks: this would bypass virtual environments.
    return Path(os.path.abspath(path if path.is_absolute() else base / path))


def load_settings() -> Settings:
    """Resolve config paths relative to the TOML file, never to the client cwd."""
    explicit_config = os.environ.get("QA_AGENT_CONFIG")
    config_path = Path(explicit_config or ROOT / "agent.toml").expanduser().absolute()
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if explicit_config:
            raise ValueError(
                f"Configuration file not found: {config_path}; check QA_PROJECT_PATH and QA_AGENT_CONFIG"
            ) from None
        config = {}
    unknown = set(config) - {"project_path", "python_path", "timeout_seconds"}
    if unknown:
        raise ValueError(f"Unknown configuration keys: {', '.join(sorted(unknown))}")
    project_value = os.environ.get("QA_PROJECT_PATH", config.get("project_path"))
    if project_value is None:
        raise ValueError("Set project_path in agent.toml or set QA_PROJECT_PATH")
    project = _path(project_value, "project_path", config_path.parent)
    python_value = os.environ.get("QA_PYTHON_PATH", config.get("python_path"))
    python = (
        _path(python_value, "python_path", config_path.parent)
        if python_value is not None
        else project / ".venv/bin/python"
    )
    timeout = config.get("timeout_seconds", 60)
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise ValueError("timeout_seconds must be an integer between 1 and 3600")
    return Settings(project=project, python=python, timeout=timeout)
