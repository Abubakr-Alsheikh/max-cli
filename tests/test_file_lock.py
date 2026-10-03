"""common/file_lock.py: a lock that holds across processes."""

import subprocess
import sys

from max_cli.common.file_lock import FileLock, is_locked

# A second Python process tries the lock once and prints what happened.
TRY_FROM_ANOTHER_PROCESS = (
    "import sys; from pathlib import Path; "
    "from max_cli.common.file_lock import FileLock; "
    "lock = FileLock(Path(sys.argv[1])); "
    "print('got' if lock.acquire(timeout=0) else 'busy')"
)


def _try_elsewhere(path) -> str:
    done = subprocess.run(
        [sys.executable, "-c", TRY_FROM_ANOTHER_PROCESS, str(path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return done.stdout.strip()


def test_a_held_lock_refuses_a_second_holder_until_released(tmp_path):
    path = tmp_path / "queue.lock"
    first, second = FileLock(path), FileLock(path)

    assert first.acquire(timeout=0)
    assert not second.acquire(timeout=0)
    assert is_locked(path)

    first.release()

    assert second.acquire(timeout=0)
    second.release()
    assert not is_locked(path)


def test_another_process_sees_the_lock(tmp_path):
    path = tmp_path / "worker.lock"

    with FileLock(path):
        assert _try_elsewhere(path) == "busy"

    assert _try_elsewhere(path) == "got"


def test_a_lock_dies_with_its_process(tmp_path):
    path = tmp_path / "worker.lock"
    # The child takes the lock and exits without releasing it.
    assert _try_elsewhere(path) == "got"

    assert FileLock(path).acquire(timeout=0)
