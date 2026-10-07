"""Run the GitHub CI checks on this machine before you push.

    python scripts/ci_local.py                 # changed: about 1-3 minutes
    python scripts/ci_local.py --quick         # the whole suite on this Python, with coverage
    python scripts/ci_local.py --full          # the whole suite on every CI Python, and the build
    python scripts/ci_local.py --install-hook  # make `git push` run the changed check first

The default (changed) check runs ruff, the mypy ratchet, an import of every
module on Python 3.9 (when .ci-venvs/py3.9 exists), and only the tests that
cover the files changed since main (`related_tests`). A change to
pyproject.toml or a conftest.py runs the whole suite instead. GitHub CI runs
everything on every PR, so the slow runs need not happen here; --quick and
--full stay for when you want them.

--full installs the package into a fresh uv virtualenv per Python version in
.ci-venvs/ (uv downloads any missing Python), so it also catches a dependency
missing from pyproject.toml.

A pass on a clean tree records HEAD and its mode in the git directory
(ci-local.json). The pre-push hook skips commits that already passed, and the
Claude guard hook refuses `gh pr create` for a package change until HEAD has
passed any check.

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
import sysconfig
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
# A push that changes none of these skips the check: GitHub CI tests it.
PACKAGE_PATHS = ("src/", "pyproject.toml")
BASE_BRANCH = "origin/main"
FAILURE_TAIL_LINES = 40
CHANGED, QUICK, FULL = "changed", "quick", "full"
MODE_STRENGTH = {CHANGED: 0, QUICK: 1, FULL: 2}
SOURCE_ROOT = "src/"
TESTS_DIR = "tests"
# A change to one of these can break any test: run the whole suite.
WHOLE_SUITE_TRIGGERS = ("pyproject.toml", "conftest.py")
# Imports every max_cli module, so Python 3.9 meets every annotation and
# syntax at import time. Heavy libraries load lazily, so this takes seconds.
IMPORT_EVERY_MODULE = (
    "import importlib, pkgutil, max_cli\n"
    "for found in pkgutil.walk_packages(max_cli.__path__, 'max_cli.'):\n"
    "    if not found.name.endswith('__main__'):\n"
    "        importlib.import_module(found.name)\n"
)
OLDEST_PYTHON = "3.9"
HOOK_MARKER = "Installed by scripts/ci_local.py"
HOOK_SCRIPT = f"""#!/bin/sh
# {HOOK_MARKER} --install-hook.
exec python scripts/ci_local.py --pre-push
"""
# A test stuck this long prints every thread's stack, so a hang names itself.
HANG_REPORT_SECONDS = 120
PYTEST_ARGS = (
    "-q",
    "-p",
    "no:cacheprovider",
    "-o",
    f"faulthandler_timeout={HANG_REPORT_SECONDS}",
)
COVERAGE_ARGS = ("--cov=max_cli", "--cov-report=", f"--cov-fail-under={COVERAGE_MIN}")
# With four Pythons side by side, one suite takes 5 to 8 minutes and the
# coverage run (TYPECHECK_PYTHON) about 10 (2026-10-02, 1,450 tests): 600
# stopped it at 99%. Past this, it hangs; faulthandler_timeout reports where.
STEP_TIMEOUT_SECONDS = 1200
# Tests that measure time. --full runs them alone after the parallel suites,
# where two suites at once made the startup budget fail on a busy machine.
TIMING_MARKER = "timing"
# Test suites at once in --full. Four at once starved each other and made a
# timing-sensitive test hang; two keeps the run short and the machine usable.
# CI_LOCAL_PARALLEL=1 runs one at a time, for a machine short of memory.
PARALLEL_SUITES = max(1, int(os.environ.get("CI_LOCAL_PARALLEL", "2") or "2"))


@dataclass
class StepResult:
    name: str
    ok: bool
    seconds: float
    output: str


def run_step(
    name: str, command: list[str], env: dict[str, str] | None = None
) -> StepResult:
    """Run a step with its output going straight to a file.

    Captured output is lost on Windows when a step is killed for hanging,
    and with it pytest's stack dump of the stuck test. A file keeps it.
    """
    started = time.monotonic()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    live_log = LOG_DIR / f"{log_path(name).stem}.live"
    with live_log.open("w", encoding="utf-8", errors="replace") as sink:
        process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            stdout=sink,
            stderr=subprocess.STDOUT,
            env={**os.environ, **(env or {})},
        )
        try:
            returncode = process.wait(timeout=STEP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            returncode = None
    output = live_log.read_text(encoding="utf-8", errors="replace")
    live_log.unlink(missing_ok=True)
    if returncode is None:
        output += f"\nStopped after {STEP_TIMEOUT_SECONDS}s: something hangs."
    return StepResult(
        name=name,
        ok=returncode == 0,
        seconds=time.monotonic() - started,
        output=output,
    )


def announce(result: StepResult) -> StepResult:
    """Print each step as it finishes, so a long run shows progress."""
    status = "PASS" if result.ok else "FAIL"
    print(f"    {status}  {result.name}  ({result.seconds:.0f}s)", flush=True)
    return result


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
    earlier = read_stamp()
    if earlier.get("head") == head and MODE_STRENGTH.get(
        earlier.get("mode", ""), -1
    ) >= MODE_STRENGTH.get(mode, 0):
        return  # a lighter pass doesn't downgrade a stronger one of the commit
    stamp = {"head": head, "mode": mode}
    stamp_path().write_text(json.dumps(stamp), encoding="utf-8")


def _module_names(source: str) -> tuple[str, str]:
    """`src/max_cli/core/agent/context.py` -> ("max_cli.core.agent.context",
    "from max_cli.core.agent import context")."""
    dotted = source.removeprefix(SOURCE_ROOT).removesuffix(".py").replace("/", ".")
    package, _, name = dotted.rpartition(".")
    return dotted, f"from {package} import {name}"


def related_tests(changed: list[str], repo_root: Path = REPO_ROOT) -> list[str]:
    """The test files that cover `changed` (repo-relative paths), sorted: the
    changed test files, test files named after a changed module, and test
    files that import one. The Claude stop hook uses it too."""
    found: set[str] = set()
    sources = []
    for name in changed:
        name = name.replace("\\", "/")
        if name.startswith(f"{TESTS_DIR}/") and Path(name).name.startswith("test_"):
            if (repo_root / name).is_file():
                found.add(name)
        elif name.startswith(SOURCE_ROOT) and name.endswith(".py"):
            sources.append(name)
    if not sources:
        return sorted(found)
    for test_file in sorted((repo_root / TESTS_DIR).rglob("test_*.py")):
        relative = test_file.relative_to(repo_root).as_posix()
        if relative in found:
            continue
        try:
            text = test_file.read_text(encoding="utf-8")
        except OSError:
            continue
        for source in sources:
            stem = Path(source).stem
            dotted, from_import = _module_names(source)
            named = stem != "__init__" and stem in test_file.stem
            if named or dotted in text or from_import in text:
                found.add(relative)
                break
    return sorted(found)


def changed_files() -> list[str]:
    """Files changed on this branch since it left main. Empty when git can't
    say (no origin/main): the caller then runs the whole suite."""
    try:
        base = git("merge-base", BASE_BRANCH, "HEAD")
        return git("diff", "--name-only", f"{base}..HEAD").splitlines()
    except subprocess.CalledProcessError:
        return []


def changed_steps() -> list[StepResult]:
    python = sys.executable
    results = []
    for name, command in (
        ("ruff check", [python, "-m", "ruff", "check", "."]),
        ("mypy baseline", [python, "scripts/mypy_baseline.py"]),
    ):
        print(f"... {name}", flush=True)
        results.append(announce(run_step(name, command)))
    oldest = venv_python(WORK_DIR / f"py{OLDEST_PYTHON}")
    if oldest.exists():
        name = f"import every module (Python {OLDEST_PYTHON})"
        print(f"... {name}", flush=True)
        results.append(
            announce(run_step(name, [str(oldest), "-c", IMPORT_EVERY_MODULE]))
        )
    else:
        print(
            f"... skipped the Python {OLDEST_PYTHON} import: no .ci-venvs/py"
            f"{OLDEST_PYTHON} (one --full run makes it)",
            flush=True,
        )
    changed = changed_files()
    pytest = pytest_program(Path(sysconfig.get_path("scripts")))
    if not changed or any(Path(name).name in WHOLE_SUITE_TRIGGERS for name in changed):
        tests: list[str] = []  # every test
        name = f"pytest, whole suite (Python {current_version()})"
    else:
        tests = related_tests(changed)
        if not tests:
            print("... no tests cover the changed files", flush=True)
            return results
        name = f"pytest, {len(tests)} related files (Python {current_version()})"
    print(f"... {name}", flush=True)
    results.append(announce(run_step(name, [pytest, *PYTEST_ARGS, *tests])))
    return results


def quick_steps() -> list[StepResult]:
    python = sys.executable
    steps = [
        ("ruff check", [python, "-m", "ruff", "check", "."]),
        ("mypy baseline", [python, "scripts/mypy_baseline.py"]),
        (
            f"pytest (Python {current_version()})",
            [
                pytest_program(Path(sysconfig.get_path("scripts"))),
                *PYTEST_ARGS,
                *COVERAGE_ARGS,
            ],
        ),
    ]
    results = []
    for name, command in steps:
        print(f"... {name}", flush=True)
        results.append(announce(run_step(name, command)))
    return results


def current_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def venv_python(venv: Path) -> Path:
    if sys.platform == "win32":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def pytest_program(scripts_dir: Path) -> str:
    """The `pytest` script in `scripts_dir`, run the way GitHub CI runs it.

    `python -m pytest` also puts the working folder on sys.path, so a test
    importing `tests.interface...` passed here and failed on every GitHub job.
    """
    return str(scripts_dir / ("pytest.exe" if sys.platform == "win32" else "pytest"))


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
    """Install as CI does, then run the tests in their own temp folders.

    Only the type-check Python measures coverage: coverage doubles the run
    time and barely changes between versions.
    """
    name = test_step_name(version)
    python = venv_python(WORK_DIR / f"py{version}")
    installed = run_step(
        name,
        ["uv", "pip", "install", "-q", "--python", str(python), "-e", PACKAGE_EXTRAS],
    )
    if not installed.ok:
        return announce(installed)
    coverage = COVERAGE_ARGS if version == TYPECHECK_PYTHON else ()
    tested = run_step(
        name,
        [
            pytest_program(python.parent),
            *PYTEST_ARGS,
            *coverage,
            "-m",
            f"not {TIMING_MARKER}",
            f"--basetemp={WORK_DIR / f'tmp-{version}'}",
        ],
        env={"COVERAGE_FILE": str(WORK_DIR / f".coverage-{version}")},
    )
    tested.seconds += installed.seconds
    return announce(tested)


def run_timing_tests(version: str) -> StepResult:
    """The timing-marked tests alone, so no other suite competes for the CPU."""
    python = venv_python(WORK_DIR / f"py{version}")
    return announce(
        run_step(
            f"timing tests (Python {version})",
            [pytest_program(python.parent), *PYTEST_ARGS, "-m", TIMING_MARKER],
        )
    )


def build_package() -> StepResult:
    return announce(
        run_step("build", ["uv", "build", "-q", "--out-dir", str(WORK_DIR / "dist")])
    )


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
        results.append(announce(run_step(name, command)))
    ready = []
    for version in PYTHON_VERSIONS:
        created = create_venv(version)
        if created is None or created.ok:
            ready.append(version)
        else:
            results.append(created)
    print(
        f"... pytest on Python {', '.join(ready)}, {PARALLEL_SUITES} at a time",
        flush=True,
    )
    with ThreadPoolExecutor(max_workers=PARALLEL_SUITES) as pool:
        jobs = [pool.submit(run_tests_on, version) for version in ready]
        results.extend(job.result() for job in jobs)
    print("... timing tests, one Python at a time", flush=True)
    results.extend(run_timing_tests(version) for version in ready)
    print("... build", flush=True)
    results.append(build_package())
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


def check(mode: str = CHANGED) -> int:
    if current_version() != TYPECHECK_PYTHON:
        print(
            f"Note: CI type-checks on Python {TYPECHECK_PYTHON}; you run {current_version()}."
        )
    started = time.monotonic()
    steps = {CHANGED: changed_steps, QUICK: quick_steps, FULL: full_steps}[mode]
    results = steps()
    ok = report(results)
    print(
        f"\n{'All checks passed' if ok else 'Checks failed'} in {time.monotonic() - started:.0f}s."
    )
    if ok:
        record_pass(mode)
    return 0 if ok else 1


def _pushed_commit(local_ref: str, sha: str) -> str:
    """The commit a pushed ref points at. An annotated tag is its own object,
    so a release tag on HEAD looked like some other commit."""
    if local_ref.startswith("refs/tags/") and sha != ZERO_SHA:
        return git("rev-parse", f"{sha}^{{commit}}") or sha
    return sha


def pushes_package_changes(ref_lines: list[str]) -> bool:
    """True when a pushed commit changes src/ or pyproject.toml.

    A new branch or tag counts from where it left main. When git can't say,
    it counts as a change.
    """
    for line in ref_lines:
        fields = line.split()
        if len(fields) != 4 or fields[1] == ZERO_SHA:
            continue
        local_sha, remote_sha = fields[1], fields[3]
        try:
            base = (
                remote_sha
                if remote_sha != ZERO_SHA
                else git("merge-base", BASE_BRANCH, local_sha)
            )
            changed = git("diff", "--name-only", f"{base}..{local_sha}").splitlines()
        except subprocess.CalledProcessError:
            return True
        if any(name.startswith(PACKAGE_PATHS) for name in changed):
            return True
    return False


def pre_push(ref_lines: list[str]) -> int:
    """Git passes one line per pushed ref: local_ref local_sha remote_ref remote_sha."""
    pushed = {
        _pushed_commit(line.split()[0], line.split()[1])
        for line in ref_lines
        if len(line.split()) == 4
    }
    pushed.discard(ZERO_SHA)  # deleting a remote branch pushes no code
    if not pushed or pushed == {read_stamp().get("head")}:
        return 0
    if not pushes_package_changes(ref_lines):
        print("ci_local: no changes to src/ or pyproject.toml; GitHub CI checks them.")
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
    print("ci_local: checking what changed before the push.")
    return check(CHANGED)


def install_hook() -> int:
    hook = REPO_ROOT / git("rev-parse", "--git-path", "hooks/pre-push")
    if hook.exists() and HOOK_MARKER not in hook.read_text(encoding="utf-8"):
        print(f"{hook} already exists and is not ours; merge it by hand.")
        return 1
    hook.parent.mkdir(parents=True, exist_ok=True)
    with hook.open("w", encoding="utf-8", newline="\n") as hook_file:
        hook_file.write(HOOK_SCRIPT)
    hook.chmod(0o755)
    print(f"Installed {hook}: `git push` now checks what changed in unchecked commits.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--quick",
        action="store_true",
        help="the whole suite on this Python, with coverage",
    )
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
    return check(FULL if args.full else QUICK if args.quick else CHANGED)


if __name__ == "__main__":
    sys.exit(main())
