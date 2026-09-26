"""Run the GitHub CI checks on this machine before you push.

    python scripts/ci_local.py                 # quick: ruff, mypy ratchet, tests with coverage
    python scripts/ci_local.py --full          # also tests on every CI Python, and the build
    python scripts/ci_local.py --install-hook  # make `git push` run the quick check first

The quick check uses the Python you run it with. --full installs the package
into a fresh uv virtualenv per Python version in .ci-venvs/ (uv downloads any
missing Python), so it also catches a dependency missing from pyproject.toml
and syntax that Python 3.9 rejects.

A pass on a clean tree records HEAD in the git directory (ci-local.json). The
pre-push hook skips commits that already passed, and the Claude guard hook
refuses `gh pr create` until HEAD has passed with --full.

CI itself lives in .github/workflows/ci.yml; tests/test_ci_local.py fails when
the Python versions or the coverage floor here drift from it. CI's macOS and
Linux runners have no local copy, so CI still has the last word on those.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON_VERSIONS = ("3.9", "3.10", "3.11", "3.12")
TYPECHECK_PYTHON = "3.11"
COVERAGE_MIN = 70
PACKAGE_EXTRAS = ".[dev,tui]"
WORK_DIR = REPO_ROOT / ".ci-venvs"
LOG_DIR = WORK_DIR / "logs"
STAMP_NAME = "ci-local.json"
ZERO_SHA = "0" * 40
FAILURE_TAIL_LINES = 40
HOOK_MARKER = "Installed by scripts/ci_local.py"
HOOK_SCRIPT = f"""#!/bin/sh
# {HOOK_MARKER} --install-hook.
exec python scripts/ci_local.py --pre-push
"""
PYTEST_ARGS = (
    "-q",
    "-p",
    "no:cacheprovider",
    "--cov=max_cli",
    "--cov-report=",
    f"--cov-fail-under={COVERAGE_MIN}",
)


@dataclass
class StepResult:
    name: str
    ok: bool
    seconds: float
    output: str


def run_step(
    name: str, command: list[str], env: dict[str, str] | None = None
) -> StepResult:
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, **(env or {})},
    )
    return StepResult(
        name=name,
        ok=completed.returncode == 0,
        seconds=time.monotonic() - started,
        output=completed.stdout + completed.stderr,
    )


def git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return completed.stdout.strip()


def stamp_path() -> Path:
    return REPO_ROOT / git("rev-parse", "--git-path", STAMP_NAME)


def read_stamp() -> dict[str, str]:
    try:
        return json.loads(stamp_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def tree_is_clean() -> bool:
    return git("status", "--porcelain", "--untracked-files=no") == ""


def record_pass(mode: str) -> None:
    """Remember that HEAD passed, but only when the checked files are HEAD's."""
    if not tree_is_clean():
        print("Uncommitted changes: this pass is not recorded for HEAD.")
        return
    head = git("rev-parse", "HEAD")
    if read_stamp() == {"head": head, "mode": "full"}:
        return  # a quick pass doesn't downgrade a full pass of the same commit
    stamp = {"head": head, "mode": mode}
    stamp_path().write_text(json.dumps(stamp), encoding="utf-8")


def quick_steps() -> list[StepResult]:
    python = sys.executable
    steps = [
        ("ruff check", [python, "-m", "ruff", "check", "."]),
        ("mypy baseline", [python, "scripts/mypy_baseline.py"]),
        (
            f"pytest (Python {current_version()})",
            [python, "-m", "pytest", *PYTEST_ARGS],
        ),
    ]
    results = []
    for name, command in steps:
        print(f"... {name}", flush=True)
        results.append(run_step(name, command))
    return results


def current_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def venv_python(venv: Path) -> Path:
    if sys.platform == "win32":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def test_step_name(version: str) -> str:
    return f"pytest (Python {version}, fresh venv)"


def create_venv(version: str) -> StepResult | None:
    """Make the venv once; later runs reuse it. None when it already exists.

    Call this for one version at a time: parallel uv processes queue on one
    lock while uv downloads a Python, and time out.
    """
    venv = WORK_DIR / f"py{version}"
    if venv_python(venv).exists():
        return None
    return run_step(
        test_step_name(version),
        ["uv", "venv", str(venv), "--python", version, "--managed-python", "-q"],
    )


def run_tests_on(version: str) -> StepResult:
    """Install as CI does, then run the tests in their own temp folders."""
    name = test_step_name(version)
    python = venv_python(WORK_DIR / f"py{version}")
    installed = run_step(
        name,
        ["uv", "pip", "install", "-q", "--python", str(python), "-e", PACKAGE_EXTRAS],
    )
    if not installed.ok:
        return installed
    tested = run_step(
        name,
        [
            str(python),
            "-m",
            "pytest",
            *PYTEST_ARGS,
            f"--basetemp={WORK_DIR / f'tmp-{version}'}",
        ],
        env={"COVERAGE_FILE": str(WORK_DIR / f".coverage-{version}")},
    )
    tested.seconds += installed.seconds
    return tested


def build_package() -> StepResult:
    return run_step("build", ["uv", "build", "-q", "--out-dir", str(WORK_DIR / "dist")])


def full_steps() -> list[StepResult]:
    if shutil.which("uv") is None:
        return [
            StepResult("uv", False, 0.0, "--full needs uv: https://docs.astral.sh/uv/")
        ]
    WORK_DIR.mkdir(exist_ok=True)
    python = sys.executable
    lint = [
        ("ruff check", [python, "-m", "ruff", "check", "."]),
        ("mypy baseline", [python, "scripts/mypy_baseline.py"]),
    ]
    results = []
    for name, command in lint:
        print(f"... {name}", flush=True)
        results.append(run_step(name, command))
    ready = []
    for version in PYTHON_VERSIONS:
        created = create_venv(version)
        if created is None or created.ok:
            ready.append(version)
        else:
            results.append(created)
    print(f"... pytest on Python {', '.join(ready)} in parallel, and build", flush=True)
    with ThreadPoolExecutor(max_workers=len(ready) + 1) as pool:
        jobs = [pool.submit(run_tests_on, version) for version in ready]
        jobs.append(pool.submit(build_package))
        results.extend(job.result() for job in jobs)
    return results


def log_path(step_name: str) -> Path:
    words = "".join(
        char if char.isalnum() or char == "." else " " for char in step_name
    )
    return LOG_DIR / f"{'-'.join(words.lower().split())}.log"


def report(results: list[StepResult]) -> bool:
    """Save each step's full output, show the end of each failure, then a summary."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    print()
    for result in results:
        log_path(result.name).write_text(result.output, encoding="utf-8")
        if not result.ok:
            tail = result.output.strip().splitlines()[-FAILURE_TAIL_LINES:]
            print(f"--- {result.name} failed; full log: {log_path(result.name)} ---")
            print("\n".join(tail))
            print()
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        print(f"{status}  {result.name}  ({result.seconds:.0f}s)")
    return all(result.ok for result in results)


def check(full: bool) -> int:
    if current_version() != TYPECHECK_PYTHON:
        print(
            f"Note: CI type-checks on Python {TYPECHECK_PYTHON}; you run {current_version()}."
        )
    started = time.monotonic()
    results = full_steps() if full else quick_steps()
    ok = report(results)
    print(
        f"\n{'All checks passed' if ok else 'Checks failed'} in {time.monotonic() - started:.0f}s."
    )
    if ok:
        record_pass("full" if full else "quick")
    return 0 if ok else 1


def pre_push(ref_lines: list[str]) -> int:
    """Git passes one line per pushed ref: local_ref local_sha remote_ref remote_sha."""
    pushed = {line.split()[1] for line in ref_lines if len(line.split()) == 4}
    pushed.discard(ZERO_SHA)  # deleting a remote branch pushes no code
    if not pushed or pushed == {read_stamp().get("head")}:
        return 0
    if pushed != {git("rev-parse", "HEAD")}:
        print("ci_local: you are pushing a commit that is not checked out.")
        print("Check it out and run `python scripts/ci_local.py`, then push again.")
        return 1
    if not tree_is_clean():
        print(
            "ci_local: commit or stash your changes, so the check tests what you push."
        )
        return 1
    print("ci_local: running the quick CI check before the push.")
    return check(full=False)


def install_hook() -> int:
    hook = REPO_ROOT / git("rev-parse", "--git-path", "hooks/pre-push")
    if hook.exists() and HOOK_MARKER not in hook.read_text(encoding="utf-8"):
        print(f"{hook} already exists and is not ours; merge it by hand.")
        return 1
    hook.parent.mkdir(parents=True, exist_ok=True)
    with hook.open("w", encoding="utf-8", newline="\n") as hook_file:
        hook_file.write(HOOK_SCRIPT)
    hook.chmod(0o755)
    print(
        f"Installed {hook}: `git push` now runs the quick check for unchecked commits."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--full", action="store_true", help="every CI Python, plus the build"
    )
    mode.add_argument(
        "--install-hook", action="store_true", help="add the git pre-push hook"
    )
    mode.add_argument("--pre-push", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.install_hook:
        return install_hook()
    if args.pre_push:
        return pre_push(sys.stdin.read().splitlines())
    return check(full=args.full)


if __name__ == "__main__":
    sys.exit(main())
