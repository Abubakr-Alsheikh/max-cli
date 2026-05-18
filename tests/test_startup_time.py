import subprocess
import sys
import time


def test_help_startup_time():
    """Ensure 'max --help' starts in under 200ms."""
    start = time.time()
    result = subprocess.run(
        [sys.executable, "-m", "max_cli.main", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    elapsed = time.time() - start

    assert result.returncode == 0, f"max --help failed: {result.stderr}"
    assert elapsed < 2.0, f"Startup took {elapsed:.3f}s (target: <2.0s)"


def test_no_heavy_imports_at_startup():
    """Verify heavy modules are not imported during CLI registration."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
sys.modules_before = set(sys.modules.keys())

from max_cli.core.cli.registry import register
import typer
app = typer.Typer()
register(app)

heavy = {'yt_dlp', 'openai', 'PIL', 'fitz', 'mutagen', 'torch', 'pandas'}
imported_heavy = heavy & set(sys.modules.keys())
if imported_heavy:
    print(f"HEAVY IMPORTS: {imported_heavy}")
    sys.exit(1)
""",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, (
        f"Heavy modules imported at startup:\n{result.stdout}\n{result.stderr}"
    )
