"""Convert the pre-Phase-3 download stores into TaskItems (decision D1).

Before the task store became the only queue and history, `max grab` kept
`grab_queue.json` / `grab_history.json` and the TUI kept
`download_history.json`. TaskManager reads each file once, converts its
entries with these functions, and renames the file to `<name>.migrated`.
"""

from typing import Any, Dict, List, Tuple

from max_cli.core.engines.task_queue import TaskItem, TaskStatus, TaskType

LEGACY_GRAB_QUEUE = "grab_queue.json"
LEGACY_GRAB_HISTORY = "grab_history.json"
LEGACY_DOWNLOAD_HISTORY = "download_history.json"
MIGRATED_SUFFIX = ".migrated"

# Options a download task keeps in its payload; NetworkEngine reads them back.
DOWNLOAD_OPTION_KEYS = (
    "quality",
    "audio_only",
    "output_path",
    "include_metadata",
    "playlist_items",
    "no_playlist",
    "subtitles",
    "custom_height",
    "player_client",
)

_GRAB_STATUS = {
    "pending": TaskStatus.PENDING,
    "downloading": TaskStatus.PENDING,  # interrupted mid-download: run it again
    "completed": TaskStatus.COMPLETED,
    "failed": TaskStatus.FAILED,
}


def grab_item_to_task(item: Dict[str, Any]) -> TaskItem:
    """Convert one `grab_queue.json` / `grab_history.json` entry."""
    status = _GRAB_STATUS.get(item.get("status", "pending"), TaskStatus.FAILED)
    payload = {"url": item["url"]}
    payload.update({key: item[key] for key in DOWNLOAD_OPTION_KEYS if key in item})
    file_path = item.get("file_path")
    task = TaskItem(
        type=TaskType.DOWNLOAD,
        status=status,
        title=item.get("title") or item["url"],
        payload=payload,
        error=item.get("error", ""),
        result={
            "file_size": item.get("file_size", 0),
            "duration": item.get("duration"),
        },
        output_path=item.get("output_path"),
        output_files=[file_path] if file_path else [],
    )
    task.id = item.get("id", task.id)
    task.created_at = item.get("added_at", task.created_at)
    if status == TaskStatus.PENDING:
        return task
    if status == TaskStatus.COMPLETED:
        task.progress = 100.0
    task.completed_at = item.get("completed_at") or task.created_at
    return task


def download_entry_to_task(entry: Dict[str, Any]) -> TaskItem:
    """Convert one `download_history.json` entry (TUI download panel)."""
    status = (
        TaskStatus.COMPLETED
        if entry.get("status") == "completed"
        else TaskStatus.FAILED
    )
    payload = dict(entry.get("settings") or {})
    payload["url"] = entry["url"]
    output_files = list(entry.get("output_files") or [])
    task = TaskItem(
        type=TaskType.DOWNLOAD,
        status=status,
        title=entry.get("title") or entry["url"],
        payload=payload,
        result={"file_size": entry.get("file_size", 0)},
        output_files=output_files,
        output_path=payload.get("output_path"),
        progress=100.0 if status == TaskStatus.COMPLETED else 0.0,
    )
    timestamp = entry.get("timestamp") or task.created_at
    task.created_at = timestamp
    task.completed_at = timestamp
    return task


def convert_grab_entries(
    entries: List[Dict[str, Any]],
) -> Tuple[List[TaskItem], List[TaskItem]]:
    """Split grab entries into (still queued, finished) tasks."""
    queued: List[TaskItem] = []
    finished: List[TaskItem] = []
    for task in (grab_item_to_task(entry) for entry in entries):
        (queued if task.status == TaskStatus.PENDING else finished).append(task)
    return queued, finished


def convert_download_history(data: Dict[str, Any]) -> List[TaskItem]:
    return [download_entry_to_task(entry) for entry in data.get("downloads", [])]
