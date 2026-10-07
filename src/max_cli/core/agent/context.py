"""What the agent sees about where you are, added to every request.

A few lines, so the model knows without a tool call what the folder holds,
which jobs are running and what Max did last: "shrink these" then needs no
list_folder first. Each part is cheap (one folder read, one queue read, one
log read) and a part that fails is left out.
"""

import os
from collections import Counter
from datetime import datetime
from pathlib import Path

from max_cli.common.exceptions import MaxError
from max_cli.common.file_kinds import kind_of

MAX_SCANNED_ENTRIES = 5_000  # a folder bigger than this is counted as "5,000+"
MAX_KINDS_NAMED = 5
CONTEXT_INTRO = "Context from Max (not from the user)"


def folder_line(folder: Path) -> str:
    """`D:\\Videos: 24 files (12 video, 8 image, 4 other), 3 folders.`"""
    kinds: Counter[str] = Counter()
    folders = 0
    more = False
    try:
        with os.scandir(folder) as entries:
            for count, entry in enumerate(entries):
                if count >= MAX_SCANNED_ENTRIES:
                    more = True
                    break
                if entry.name.startswith("."):
                    continue
                try:
                    if entry.is_dir():
                        folders += 1
                    elif entry.is_file():
                        kinds[kind_of(Path(entry.name)) or "other"] += 1
                except OSError:
                    continue
    except OSError:
        return ""
    files = sum(kinds.values())
    by_kind = ", ".join(
        f"{number} {kind}" for kind, number in kinds.most_common(MAX_KINDS_NAMED)
    )
    total = f"{files:,}{'+' if more else ''} files"
    return (
        f"{folder}: {total}{f' ({by_kind})' if by_kind else ''}, "
        f"{folders} folder{'s' if folders != 1 else ''}."
    )


def queue_line() -> str:
    """`Queue: 1 running (Compress a.mp4, 45%), 2 waiting.` or ""."""
    from max_cli.core.engines.task_manager import get_task_manager
    from max_cli.core.engines.task_queue import TaskStatus

    manager = get_task_manager()
    manager.try_refresh()
    running = manager.get_all(TaskStatus.RUNNING)
    waiting = manager.get_all(TaskStatus.PENDING)
    if not running and not waiting:
        return ""
    parts = []
    if running:
        names = ", ".join(f"{task.title}, {task.progress:.0f}%" for task in running[:2])
        parts.append(f"{len(running)} running ({names})")
    if waiting:
        parts.append(f"{len(waiting)} waiting")
    return f"Queue: {', '.join(parts)}."


def last_action_line() -> str:
    """`Last: video compress, success, 5 min ago.` or ""."""
    from max_cli.common.activity_log import ActivityLog

    entries = ActivityLog().get_entries(limit=1)
    if not entries:
        return ""
    entry = entries[0]
    try:
        minutes = int(
            (datetime.now() - datetime.fromisoformat(entry.timestamp)).total_seconds()
            // 60
        )
    except ValueError:
        return ""
    when = "just now" if minutes < 1 else _ago(minutes)
    return f"Last: {entry.category} {entry.action}, {entry.status}, {when}."


def _ago(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} h ago"
    return f"{hours // 24} days ago"


def request_context(folder: Path) -> str:
    """The context lines for one request, or "" when there is nothing to say."""
    lines = []
    for part in (lambda: folder_line(folder), queue_line, last_action_line):
        try:
            line = part()
        except (OSError, ValueError, KeyError, MaxError):
            continue
        if line:
            lines.append(line)
    if not lines:
        return ""
    return f"({CONTEXT_INTRO}: {' '.join(lines)})"
