"""A lock that holds across processes, not only threads.

The task queue is shared by the dashboard, CLI commands and the background
worker, each its own process. The lock is a byte lock on a small file
(`msvcrt` on Windows, `flock` elsewhere); the system drops it when the
process ends, so a crashed process never leaves a stale lock behind.
"""

import sys
import time
from pathlib import Path
from typing import IO, Any, Optional

LOCK_POLL_SECONDS = 0.05


class FileLock:
    """`with FileLock(path):` waits for the lock; `acquire(timeout=0)` tries
    once. A second FileLock on the same path conflicts even in this process."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: Optional[IO[bytes]] = None

    @property
    def held(self) -> bool:
        return self._handle is not None

    def acquire(self, timeout: Optional[float] = None) -> bool:
        """True once the lock is ours. None waits as long as it takes; with a
        timeout, False when it runs out (0 tries once)."""
        if self._handle is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        deadline = None if timeout is None else time.monotonic() + timeout
        while not _try_lock(handle):
            if deadline is not None and time.monotonic() >= deadline:
                handle.close()
                return False
            time.sleep(LOCK_POLL_SECONDS)
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            _unlock(self._handle)
        finally:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> "FileLock":
        self.acquire()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.release()


def is_locked(path: Path) -> bool:
    """True when some process (this one included) holds the lock on `path`."""
    probe = FileLock(path)
    if probe.acquire(timeout=0):
        probe.release()
        return False
    return True


if sys.platform == "win32":
    import msvcrt

    def _try_lock(handle: IO[bytes]) -> bool:
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    def _unlock(handle: IO[bytes]) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _try_lock(handle: IO[bytes]) -> bool:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True

    def _unlock(handle: IO[bytes]) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
