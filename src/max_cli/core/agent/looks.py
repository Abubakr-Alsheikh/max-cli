"""Read-only tools that let the agent look before it acts.

- `list_folder`: what a folder holds.
- `inspect`: the facts about one file or folder: a song's tags, a video's
  length and codecs, an image's size and camera, a PDF's pages (the
  `describe` functions the dashboard pages show).
- `find_files`: search a folder and its subfolders by kind, name, size and
  age.
- `probe_link`: what a link holds before downloading it (`grab.probe`).
- `recent_activity`: what Max did lately and what undo can reverse.
- `job_status`: the queued jobs, running, waiting and finished.

They change nothing and never ask. Paths go through the same folder limits
as actions.
"""

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from max_cli.common.exceptions import ResourceNotFoundError
from max_cli.common.file_kinds import AUDIO, IMAGE, PDF, VIDEO, kind_of
from max_cli.common.utils import format_size

MAX_LISTED = 60  # entries list_folder names; the counts cover every file
# A folder is "mostly" one kind at this share, so inspect adds that kind's
# facts (an audio folder's tag summary, an image folder's formats).
MOSTLY = 0.5
MAX_LOOK_CHARS = 6_000


def _plain(value: Any) -> Any:
    """Facts as JSON-safe values: paths and dates become text."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {key: _plain(item) for key, item in dataclasses.asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _to_json(data: dict[str, Any]) -> str:
    return json.dumps(_plain(data), ensure_ascii=False)[:MAX_LOOK_CHARS]


def list_folder(path: Path) -> str:
    """A folder's subfolders and files (name, kind, size), the files counted
    by kind, as JSON for the model."""
    if not path.is_dir():
        raise ResourceNotFoundError(f"Not a folder: {path}")
    folders: list[str] = []
    files: list[tuple[str, str, int]] = []
    for entry in sorted(path.iterdir(), key=lambda item: item.name.casefold()):
        if entry.name.startswith("."):
            continue
        try:
            if entry.is_dir():
                folders.append(entry.name)
            elif entry.is_file():
                files.append((entry.name, kind_of(entry), entry.stat().st_size))
        except OSError:
            continue  # vanished, or a broken link
    kinds: dict[str, int] = {}
    for _name, kind, _size in files:
        kinds[kind] = kinds.get(kind, 0) + 1
    listed = files[:MAX_LISTED]
    return _to_json(
        {
            "folder": str(path),
            "subfolders": folders[:MAX_LISTED],
            "file_count": len(files),
            "total_size": format_size(sum(size for _n, _k, size in files)),
            "kinds": kinds,
            "files": [
                {"name": name, "kind": kind, "size": format_size(size)}
                for name, kind, size in listed
            ],
            "more_files": max(0, len(files) - len(listed)),
        }
    )


def _describers() -> dict[str, Callable[[Path], Any]]:
    from max_cli.core.operations import audio, images, pdf, video

    return {
        AUDIO: audio.describe,
        IMAGE: images.describe,
        PDF: pdf.describe,
        VIDEO: video.describe,
    }


def inspect(path: Path) -> str:
    """The facts about a file, or a folder and its main kind of file."""
    from max_cli.core.operations import files

    facts = files.describe(path)  # raises for a missing path
    result: dict[str, Any] = {"basics": facts}
    describers = _describers()
    if facts.is_folder:
        main = max(facts.kinds, key=lambda kind: facts.kinds[kind], default="")
        mostly = facts.file_count and facts.kinds.get(main, 0) / facts.file_count
        # Video and PDF facts are per file; audio and images sum up a folder.
        if main in (AUDIO, IMAGE) and mostly >= MOSTLY:
            result[main] = describers[main](path)
    elif kind_of(path) in describers:
        result[kind_of(path)] = describers[kind_of(path)](path)
    return _to_json(result)


# --- find_files --------------------------------------------------------------

MAX_FOUND = 40  # matches find_files names; the totals cover every match
MAX_SCANNED = 20_000  # files a search looks at before it stops and says so
BYTES_PER_MB = 1024 * 1024
SECONDS_PER_DAY = 86_400
FIND_SORTS = ("size", "newest", "oldest", "name")


@dataclass(frozen=True)
class FileFilter:
    """Name, size and age limits; 0 or "" leaves a limit out. find_files and
    the agent's batches (`run_action` with `select`) use the same rules."""

    name: str = ""
    min_size_mb: float = 0
    max_size_mb: float = 0
    newer_than_days: float = 0
    older_than_days: float = 0

    @property
    def pattern(self) -> str:
        """`name` as a case-free pattern: a plain word matches anywhere."""
        pattern = self.name.strip().casefold()
        if pattern and not any(mark in pattern for mark in "*?["):
            pattern = f"*{pattern}*"
        return pattern

    def keeps(self, entry: Path, size: int, modified: float, now: float) -> bool:
        import fnmatch

        pattern = self.pattern
        age_days = (now - modified) / SECONDS_PER_DAY
        size_mb = size / BYTES_PER_MB
        return not (
            (pattern and not fnmatch.fnmatch(entry.name.casefold(), pattern))
            or (self.min_size_mb and size_mb < self.min_size_mb)
            or (self.max_size_mb and size_mb > self.max_size_mb)
            or (self.newer_than_days and age_days > self.newer_than_days)
            or (self.older_than_days and age_days < self.older_than_days)
        )

    def select(self, files: list[Path]) -> list[Path]:
        """The files that pass; a file that can't be read is left out."""
        import time

        now = time.time()
        kept = []
        for entry in files:
            try:
                info = entry.stat()
            except OSError:
                continue
            if self.keeps(entry, info.st_size, info.st_mtime, now):
                kept.append(entry)
        return kept


def find_files(
    path: Path,
    kind: str = "",
    name: str = "",
    min_size_mb: float = 0,
    max_size_mb: float = 0,
    newer_than_days: float = 0,
    older_than_days: float = 0,
    sort: str = "size",
    missing: str = "",
) -> str:
    """Files under `path` and its subfolders that match every filter given,
    as JSON: the count and total size of all matches, then the top ones.

    `kind` is a file_kinds kind (video, audio, image ...), `name` a pattern
    such as *.mp4 or *invoice*. `missing` (an extension such as mp3) keeps
    only files with no same-name file of that type beside them: the work
    still to do, for a conversion. Hidden files and folders are skipped.
    """
    import time
    from datetime import datetime

    if not path.is_dir():
        raise ResourceNotFoundError(f"Not a folder: {path}")
    if sort not in FIND_SORTS:
        sort = "size"
    now = time.time()
    limits = FileFilter(
        name, min_size_mb, max_size_mb, newer_than_days, older_than_days
    )
    done_suffix = (
        f".{missing.strip().lstrip('.').casefold()}" if missing.strip() else ""
    )
    already_done: list[str] = []
    matches: list[tuple[Path, int, float]] = []
    scanned = 0
    stopped = False
    for entry in path.rglob("*"):
        if any(part.startswith(".") for part in entry.relative_to(path).parts):
            continue
        try:
            if not entry.is_file():
                continue
            info = entry.stat()
        except OSError:
            continue  # vanished, locked, or a broken link
        scanned += 1
        if scanned > MAX_SCANNED:
            stopped = True
            break
        if kind and kind_of(entry) != kind:
            continue
        if not limits.keeps(entry, info.st_size, info.st_mtime, now):
            continue
        if done_suffix and (
            entry.suffix.casefold() == done_suffix
            or entry.with_suffix(done_suffix).exists()
        ):
            if entry.suffix.casefold() != done_suffix:
                already_done.append(str(entry.relative_to(path)))
            continue
        matches.append((entry, info.st_size, info.st_mtime))
    order = {
        "size": (lambda item: -item[1]),
        "newest": (lambda item: -item[2]),
        "oldest": (lambda item: item[2]),
        "name": (lambda item: str(item[0]).casefold()),
    }[sort]
    matches.sort(key=order)
    shown = matches[:MAX_FOUND]
    return _to_json(
        {
            "folder": str(path),
            "matches": len(matches),
            "total_size": format_size(sum(size for _p, size, _m in matches)),
            "files": [
                {
                    "path": str(found.relative_to(path)),
                    "kind": kind_of(found),
                    "size": format_size(size),
                    "modified": datetime.fromtimestamp(modified).strftime("%Y-%m-%d"),
                }
                for found, size, modified in shown
            ],
            "more": max(0, len(matches) - len(shown)),
            **(
                {
                    "already_done": {
                        "count": len(already_done),
                        "files": already_done[:MAX_FOUND],
                        "note": f"These have a {done_suffix} already: leave them "
                        "out and tell the user you skipped them.",
                    }
                }
                if already_done
                else {}
            ),
            "note": (
                f"Stopped after {MAX_SCANNED:,} files; narrow the folder."
                if stopped
                else ""
            ),
        }
    )


# --- probe_link --------------------------------------------------------------

MAX_PLAYLIST_ITEMS = 15


def probe_link(url: str) -> str:
    """What a link holds, before downloading it: title, length, site, the
    qualities with their sizes, or a playlist's items."""
    from max_cli.core.operations import grab

    info = grab.probe(url)
    return _to_json(
        {
            "url": info.url,
            "title": info.title,
            "uploader": info.uploader,
            "site": info.site,
            "duration_seconds": info.total_duration,
            "is_playlist": info.is_playlist,
            "is_live": info.is_live,
            "upload_date": info.upload_date,
            "qualities": [
                {
                    "quality": quality.label,
                    "size": format_size(quality.size_bytes)
                    if quality.size_bytes
                    else "unknown",
                }
                for quality in info.qualities
            ],
            "audio_size": format_size(info.audio_size_bytes)
            if info.audio_size_bytes
            else "unknown",
            "subtitles": info.subtitle_languages,
            "playlist_items": len(info.entries),
            "first_items": [
                {"index": entry.index, "title": entry.title, "seconds": entry.duration}
                for entry in info.entries[:MAX_PLAYLIST_ITEMS]
            ],
        }
    )


# --- recent_activity -----------------------------------------------------------

MAX_RECENT = 15


def recent_activity(limit: int = 10) -> str:
    """What Max did lately (from the CLI, the dashboard or the agent) and the
    file changes it can still undo, newest first."""
    from max_cli.common.activity_log import ActivityLog
    from max_cli.common.transaction_log import TransactionLog

    limit = max(1, min(int(limit or 10), MAX_RECENT))
    actions = []
    for entry in ActivityLog().get_entries(limit=limit):
        details = entry.details or {}
        args = details.get("args") or {}
        actions.append(
            {
                "when": entry.timestamp[:16].replace("T", " "),
                "what": f"{entry.category} {entry.action}",
                "status": entry.status,
                "message": str(details.get("message") or details.get("error") or ""),
                "prompt": str(details.get("prompt") or ""),
                "target": str(
                    args.get("target") or args.get("folder") or args.get("path") or ""
                ),
                "output_files": details.get("output_files") or [],
            }
        )
    changes = [
        {
            "when": str(group["timestamp"])[:16].replace("T", " "),
            "command": group["command"],
            "folder": group.get("folder") or "",
            "changes": group["operation_count"],
            "undone": group["undo_status"] == "undone",
        }
        for group in TransactionLog.list_groups()[:limit]
    ]
    return _to_json({"actions": actions, "file_changes_undo_can_reverse": changes})


# --- job_status ------------------------------------------------------------------

MAX_JOBS = 15
MAX_JOB_OUTPUTS = 5


def _job(task: Any) -> dict[str, Any]:
    status = getattr(task.status, "value", task.status)
    job: dict[str, Any] = {
        "id": task.id,
        "title": task.title,
        "status": status,
        "added": task.created_at[:16].replace("T", " "),
    }
    if status == "running":
        job["progress"] = f"{task.progress:.0f}%"
        if task.eta:
            job["eta"] = task.eta
    if task.error:
        job["error"] = task.error
    if task.output_files:
        job["outputs"] = task.output_files[:MAX_JOB_OUTPUTS]
    return job


def job_status(limit: int = 10) -> str:
    """The background queue: jobs running or waiting, then the latest
    finished ones (done, failed or cancelled), newest first."""
    from max_cli.core.engines.task_manager import get_task_manager

    limit = max(1, min(int(limit or 10), MAX_JOBS))
    manager = get_task_manager()
    manager.try_refresh()
    active = [task for task in manager.get_all() if task.is_active]
    return _to_json(
        {
            "worker_running": manager.worker_alive(),
            "running_or_waiting": [_job(task) for task in active[:limit]],
            "more_waiting": max(0, len(active) - limit),
            "finished": [_job(task) for task in manager.get_history(limit=limit)],
        }
    )
