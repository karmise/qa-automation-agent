from pathlib import Path

import pytest

import server


@pytest.fixture(autouse=True)
def isolate_run_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep all agent test artifacts outside the real run history."""
    monkeypatch.setattr(server, "RUNS_DIR", tmp_path / "runs")

    monkeypatch.setattr(server, "load_settings", lambda: {
        "project": tmp_path / "framework",
        "python": tmp_path / "framework/.venv/bin/python",
        "timeout": 60,
    })
