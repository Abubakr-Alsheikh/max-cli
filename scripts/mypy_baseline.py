"""Ratchet mypy errors: the count may only go down.

    python scripts/mypy_baseline.py           # check (CI)
    python scripts/mypy_baseline.py --update  # record a lower count after fixing errors

Fails when the error count is above the baseline (new errors) or below it
without an update (a fix that was not locked in). Configuration comes from
mypy.ini; the baseline lives in mypy-baseline.txt.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_FILE = REPO_ROOT / "mypy-baseline.txt"
MYPY_TARGET = "src"
SUMMARY_PATTERN = re.compile(r"Found (\d+) errors? in")
SUCCESS_MARKER = "Success: no issues found"
BLOCKING_MARKER = "errors prevented further checking"
MYPY_CRASH_EXIT_CODE = 2


def run_mypy() -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, "-m", "mypy", MYPY_TARGET, "--no-color-output"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = result.stdout + result.stderr
    # A blocking error stops mypy early with a tiny count; never read that as progress.
    if BLOCKING_MARKER in output or result.returncode == MYPY_CRASH_EXIT_CODE:
        print(output)
        raise SystemExit("mypy stopped early (blocking error above); count is invalid.")
    if SUCCESS_MARKER in output:
        return 0, output
    match = SUMMARY_PATTERN.search(output)
    if match is None:
        print(output)
        raise SystemExit("Could not parse mypy output (did mypy crash?).")
    return int(match.group(1)), output


def main() -> int:
    error_count, output = run_mypy()
    if "--update" in sys.argv:
        BASELINE_FILE.write_text(f"{error_count}\n", encoding="utf-8")
        print(f"Baseline set to {error_count}.")
        return 0

    baseline = int(BASELINE_FILE.read_text(encoding="utf-8").strip())
    if error_count > baseline:
        print(output)
        print(f"mypy: {error_count} errors, baseline {baseline}. Fix the new errors.")
        return 1
    if error_count < baseline:
        print(output)
        print(
            f"mypy: {error_count} errors, baseline {baseline}. Lock in the "
            "improvement: python scripts/mypy_baseline.py --update"
        )
        return 1
    print(f"mypy: {error_count} errors (matches baseline).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
