"""Read-only Git facts about the target project; every failure degrades to 'unknown'."""

import re
import subprocess
from pathlib import Path

SHA = re.compile(r"[0-9a-f]{40}")


def _git(project: Path, *arguments: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(project), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def snapshot(project: Path) -> dict:
    """Record the tested commit and uncommitted files."""
    head = (_git(project, "rev-parse", "HEAD") or "").strip()
    if not SHA.fullmatch(head):
        return {"head": None}
    branch = (_git(project, "rev-parse", "--abbrev-ref", "HEAD") or "").strip() or None
    status = _git(project, "status", "--porcelain", "--untracked-files=no") or ""
    dirty = sorted(line[3:].strip() for line in status.splitlines() if len(line) > 3)
    return {"head": head, "branch": branch, "dirty_files": dirty}


def changes_since(project: Path, previous: dict | None, current: dict) -> dict:
    """List files changed between the previous run's commit and this run's tree."""
    files = set(current.get("dirty_files", []))
    base = (previous or {}).get("head")
    if base and current.get("head") and SHA.fullmatch(base) and base != current["head"]:
        diff = _git(project, "diff", "--name-only", f"{base}..{current['head']}")
        if diff is None:
            return {"base": base, "files": sorted(files), "error": "Cannot diff commits"}
        files |= {line.strip() for line in diff.splitlines() if line.strip()}
    return {"base": base, "files": sorted(files)}
