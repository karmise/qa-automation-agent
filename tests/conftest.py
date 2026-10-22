from pathlib import Path

import pytest

from qa_agent import pipeline, runner, storage
from qa_agent.settings import Settings


@pytest.fixture(autouse=True)
def isolate_run_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate artifacts and target configuration from the developer's machine."""
    settings = Settings(
        project=tmp_path / "framework",
        python=tmp_path / "framework/.venv/bin/python",
        timeout=60,
    )
    monkeypatch.setattr(storage, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(runner, "load_settings", lambda: settings)
    monkeypatch.setattr(pipeline, "load_settings", lambda: settings)


@pytest.fixture
def results_dir(tmp_path: Path) -> Path:
    return tmp_path / "allure-results"
