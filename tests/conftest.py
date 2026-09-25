from pathlib import Path

import pytest

from qa_agent import runner, storage
from qa_agent.settings import Settings


@pytest.fixture(autouse=True)
def isolate_run_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate artifacts and target configuration from the developer's machine."""
    monkeypatch.setattr(storage, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(
        runner,
        "load_settings",
        lambda: Settings(
            project=tmp_path / "framework",
            python=tmp_path / "framework/.venv/bin/python",
        ),
    )
