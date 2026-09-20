import subprocess

PROJECT_PATH = (
    "/Users/karmise/Documents/Codex/2026-07-29/restful-booker-platform"
)

result = subprocess.run(
    [
        f"{PROJECT_PATH}/.venv/bin/python",
        "-m",
        "pytest",
        "tests/unit",
        "-q",
    ],
    cwd=PROJECT_PATH,
    capture_output=True,
    text=True,
    timeout=60,
)

print("Exit code:", result.returncode)
print("Standard output:")
print(result.stdout)
print("Standard error:")
print(result.stderr)