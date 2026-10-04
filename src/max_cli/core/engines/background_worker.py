"""Run the task queue in a process of its own, after the command returns.

A CLI command that queues work calls `start_background_worker()`: it starts
`max queue worker` detached from the terminal unless some process already
runs the queue (the dashboard, or a worker started earlier). The worker
runs every queued task, waits WORKER_IDLE_EXIT_SECONDS for more, then
exits. Closing the terminal doesn't stop it.
"""

import subprocess
import sys
from pathlib import Path

from max_cli.core.engines.task_manager import get_task_manager

WORKER_LOG_NAME = "worker.log"
WORKER_COMMAND = ("-m", "max_cli.main", "queue", "worker")


def worker_log_path() -> Path:
    """Where the background worker writes what it did and what failed."""
    return get_task_manager().QUEUE_DIR / WORKER_LOG_NAME


def start_background_worker() -> bool:
    """Start the worker unless one runs already. True when one was started."""
    if get_task_manager().worker_alive():
        return False
    _spawn(worker_log_path())
    return True


def _spawn(log_path: Path) -> "subprocess.Popen[bytes]":
    """Start `max queue worker` detached, its output going to `log_path`."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        return subprocess.Popen(  # noqa: S603 - our own interpreter and module, no shell
            [sys.executable, *WORKER_COMMAND],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            close_fds=True,
            **_detached(),
        )


def _detached() -> dict:
    """Popen options that keep the worker alive after the terminal closes.

    On Windows the worker gets a console of its own, hidden: the ffmpeg,
    ffprobe and yt-dlp processes it starts share it. DETACHED_PROCESS left
    it with none, so each of them opened a visible window, and closing one
    killed the job.
    """
    if sys.platform == "win32":
        return {
            "creationflags": subprocess.CREATE_NO_WINDOW
            | subprocess.CREATE_NEW_PROCESS_GROUP
        }
    return {"start_new_session": True}
