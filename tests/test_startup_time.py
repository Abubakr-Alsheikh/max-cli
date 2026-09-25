"""Startup budget for `max`: import cost and heavy-import leaks.

Import cost = time to `import max_cli.main` minus bare interpreter startup,
best of several runs, so the number tracks our code rather than machine noise.
"""

import subprocess
import sys
import time

import pytest

IMPORT_COST_TARGET_SECONDS = 0.2  # AGENTS.md goal: `max --help` under 200ms
IMPORT_COST_CEILING_SECONDS = 1.0  # regression guard; ~0.09s on 2026-09-25 (D5)
TIMING_RUNS = 5
SUBPROCESS_TIMEOUT_SECONDS = 30

HEAVY_PACKAGES = [
    "yt_dlp",
    "openai",
    "PIL",
    "fitz",
    "mutagen",
    "requests",
    "textual",
    "psutil",
    "torch",
    "pandas",
    "segno",
    "pyperclip",
]


def _best_run_seconds(code: str) -> float:
    best = float("inf")
    for _ in range(TIMING_RUNS):
        start = time.perf_counter()
        subprocess.run(
            [sys.executable, "-c", code],
            check=True,
            capture_output=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
        best = min(best, time.perf_counter() - start)
    return best


@pytest.fixture(scope="module")
def import_cost_seconds() -> float:
    return _best_run_seconds("import max_cli.main") - _best_run_seconds("pass")


def test_help_runs():
    result = subprocess.run(
        [sys.executable, "-m", "max_cli.main", "--help"],
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
    )
    assert result.returncode == 0, f"max --help failed: {result.stderr}"


def test_import_cost_below_ceiling(import_cost_seconds: float):
    assert import_cost_seconds < IMPORT_COST_CEILING_SECONDS, (
        f"Import cost {import_cost_seconds:.3f}s exceeds regression ceiling "
        f"{IMPORT_COST_CEILING_SECONDS}s. Look for new module-level imports."
    )


def test_import_cost_meets_target(import_cost_seconds: float):
    assert import_cost_seconds < IMPORT_COST_TARGET_SECONDS, (
        f"Import cost {import_cost_seconds:.3f}s (target {IMPORT_COST_TARGET_SECONDS}s)"
    )


@pytest.fixture(scope="module")
def modules_after_registration() -> set:
    """Top-level package names loaded after registering every CLI command."""
    probe = (
        "import sys, typer\n"
        "from max_cli.core.cli.registry import register\n"
        "register(typer.Typer())\n"
        "print('\\n'.join(sorted({name.split('.')[0] for name in sys.modules})))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
    )
    assert result.returncode == 0, f"Registration probe crashed:\n{result.stderr}"
    return set(result.stdout.split())


@pytest.mark.parametrize("package", HEAVY_PACKAGES)
def test_heavy_package_not_imported_at_startup(
    package: str, modules_after_registration: set
):
    assert package not in modules_after_registration, (
        f"'{package}' is imported while registering commands. "
        "Move the import inside the method that uses it."
    )
