"""Stop hook: before Claude ends a turn that edited Python, run ruff + pytest.

Only runs when check_rules.py recorded a Python edit this session. On failure it
blocks the stop and hands the failure back to Claude. After one blocked retry
(stop_hook_active) it stops blocking and warns the user instead, matching the
AGENTS.md 2-strike rule.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PYTEST_TIMEOUT_SECONDS = 300
OUTPUT_TAIL_LINES = 40


def run(command: list[str], repo_root: Path) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PYTEST_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        return True, ""
    except subprocess.TimeoutExpired:
        return False, f"{' '.join(command)} timed out after {PYTEST_TIMEOUT_SECONDS}s"
    output = (result.stdout + result.stderr).strip().splitlines()
    return result.returncode == 0, "\n".join(output[-OUTPUT_TAIL_LINES:])


def main() -> int:
    payload = json.load(sys.stdin)
    repo_root = Path(payload.get("cwd") or ".").resolve()
    session_id = payload.get("session_id") or "default"
    marker = repo_root / ".claude" / ".state" / f"{session_id}.edited"
    if not marker.exists():
        return 0

    edited = sorted(set(marker.read_text(encoding="utf-8").split()))
    lint_ok, lint_out = run(["ruff", "check", "src", "tests"], repo_root)
    tests_ok, tests_out = run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-x",
            "--no-header",
            "-p",
            "no:cacheprovider",
        ],
        repo_root,
    )

    if lint_ok and tests_ok:
        marker.unlink()
        return 0

    failures = []
    if not lint_ok:
        failures.append("ruff check failed:\n" + lint_out)
    if not tests_ok:
        failures.append("pytest failed:\n" + tests_out)
    report = "\n\n".join(failures)

    if payload.get("stop_hook_active"):
        marker.unlink()
        print(
            json.dumps(
                {
                    "systemMessage": "Quality gate still failing after one retry. "
                    "Claude must report the failure instead of claiming success.\n"
                    + report
                }
            )
        )
        return 0

    print(
        json.dumps(
            {
                "decision": "block",
                "reason": "Quality gate failed after editing "
                + ", ".join(edited)
                + ". Fix the failures (or explain why they are pre-existing) "
                "before finishing.\n\n" + report,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
