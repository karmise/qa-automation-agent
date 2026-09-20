import json
from pathlib import Path

RESULTS_DIR = Path(
    "/Users/karmise/Documents/Codex/2026-07-29/"
    "restful-booker-platform/allure-results"
)

result_files = sorted(RESULTS_DIR.glob("*-result.json"))

if not result_files:
    print("No test result files found.")
else:
    failures = []

    for file in result_files:
        result = json.loads(file.read_text(encoding="utf-8"))

        if result.get("status") in {"failed", "broken"}:
            failures.append({
                "uuid": result.get("uuid"),
                "name": result.get("name"),
                "full_name": result.get("fullName"),
                "status": result.get("status"),
                "details": result.get("statusDetails", {}),
            })

    print(f"Result files read: {len(result_files)}")
    print(json.dumps(failures, indent=2, ensure_ascii=False))