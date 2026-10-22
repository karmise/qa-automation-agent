"""Validated configuration with stable path resolution and environment overrides."""

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

KNOWN_KEYS = {
    "project_path",
    "python_path",
    "timeout_seconds",
    "env",
    "llm_command",
    "llm_timeout_seconds",
}
ENV_NAME = re.compile(r"[A-Z_][A-Z0-9_]*")


@dataclass(frozen=True)
class Settings:
    """Immutable configuration for one execution."""

    project: Path
    python: Path
    timeout: int = 900
    env: dict[str, str] = field(default_factory=dict)
    llm_command: tuple[str, ...] = ()
    llm_timeout: int = 180


def _path(value: object, name: str, base: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty path string")
    path = Path(value).expanduser()
    # Do not resolve interpreter symlinks: this would bypass virtual environments.
    return Path(os.path.abspath(path if path.is_absolute() else base / path))


def _seconds(value: object, name: str) -> int:
    if type(value) is not int or not 1 <= value <= 3600:
        raise ValueError(f"{name} must be an integer between 1 and 3600")
    return value


def _env(value: object) -> dict[str, str]:
    """Extra variables for the target process, such as RBP_BASE_URL."""
    if not isinstance(value, dict):
        raise ValueError("env must be a table of string values")
    for key, item in value.items():
        if not ENV_NAME.fullmatch(key) or not isinstance(item, str):
            raise ValueError("env must map uppercase variable names to string values")
    return dict(value)


def _command(value: object) -> tuple[str, ...]:
    """An argument list, never a shell string: the prompt is sent on stdin.

    Later arguments may be empty, as in Claude Code's `--tools ""` (no tools).
    """
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(part, str) for part in value)
        or not value[0]
    ):
        raise ValueError("llm_command must be a list of strings starting with an executable")
    return tuple(value)


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
    unknown = set(config) - KNOWN_KEYS
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
    return Settings(
        project=project,
        python=python,
        timeout=_seconds(config.get("timeout_seconds", 900), "timeout_seconds"),
        env=_env(config.get("env", {})),
        llm_command=_command(config["llm_command"]) if "llm_command" in config else (),
        llm_timeout=_seconds(config.get("llm_timeout_seconds", 180), "llm_timeout_seconds"),
    )
