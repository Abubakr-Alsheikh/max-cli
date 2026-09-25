"""Download history as a view over the task store (decision D1).

Downloads live in TaskManager history as DOWNLOAD tasks, next to every other
task. This class answers the questions the download UI asks: was this URL
downloaded before, where did the last download from this site go, and which
settings did the user pick last time.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from max_cli.core.engines.task_manager import TaskManager, get_task_manager
from max_cli.core.engines.task_queue import TaskItem, TaskStatus, TaskType

RECENT_DOWNLOADS_LIMIT = 20


class DownloadHistory:
    """Read and record downloads in the shared task store."""

    def __init__(self, manager: Optional[TaskManager] = None) -> None:
        self._manager = manager or get_task_manager()

    def record_download(
        self,
        url: str,
        title: str = "",
        output_files: Optional[list[str]] = None,
        settings_used: Optional[dict[str, Any]] = None,
        file_size: int = 0,
        status: str = "completed",
    ) -> TaskItem:
        """Record a download that ran outside the queue."""
        payload: dict[str, Any] = dict(settings_used or {})
        payload["url"] = url
        succeeded = status == TaskStatus.COMPLETED.value
        task = TaskItem(
            type=TaskType.DOWNLOAD,
            status=TaskStatus.COMPLETED if succeeded else TaskStatus.FAILED,
            title=title or url,
            description=url,
            payload=payload,
            progress=100.0 if succeeded else 0.0,
            result={"file_size": file_size},
            output_files=list(output_files or []),
            output_path=payload.get("output_path"),
            completed_at=datetime.now().isoformat(),
        )
        return self._manager.record(task)

    def is_already_downloaded(self, url: str) -> Optional[dict[str, Any]]:
        """Return the newest entry for `url`, or None if it was never downloaded."""
        for task in self._downloads():
            if task.payload.get("url") == url:
                return _to_entry(task)
        return None

    def get_last_output_path(self, url: str) -> Optional[str]:
        """Return the folder of the newest download from the same site as `url`."""
        domain = urlparse(url).netloc
        for task in self._downloads():
            if _domain(task) == domain and task.output_files:
                return str(Path(task.output_files[0]).parent)
        return None

    def get_last_settings(self) -> dict[str, Any]:
        """Return the options of the newest download, without its URL."""
        for task in self._downloads():
            settings = dict(task.payload)
            settings.pop("url", None)
            return settings
        return {}

    def get_recent(self, limit: int = RECENT_DOWNLOADS_LIMIT) -> list[dict[str, Any]]:
        """Return the newest entries, one per URL."""
        seen_urls = set()
        entries: list[dict[str, Any]] = []
        for task in self._downloads():
            url = task.payload.get("url")
            if url in seen_urls:
                continue
            seen_urls.add(url)
            entries.append(_to_entry(task))
            if len(entries) >= limit:
                break
        return entries

    def get_stats(self) -> dict[str, int]:
        downloads = self._downloads()
        return {
            "total": len(downloads),
            "completed": sum(1 for t in downloads if t.status == TaskStatus.COMPLETED),
            "failed": sum(1 for t in downloads if t.status == TaskStatus.FAILED),
            "total_size": sum(_file_size(t) for t in downloads),
            "unique_domains": len({_domain(t) for t in downloads if _domain(t)}),
        }

    def clear_history(self) -> int:
        """Remove every finished download from history. Returns the count."""
        return self._manager.clear_history(task_type=TaskType.DOWNLOAD)

    def _downloads(self) -> list[TaskItem]:
        """Finished downloads, newest first."""
        return self._manager.get_history(limit=0, task_type=TaskType.DOWNLOAD)


def _domain(task: TaskItem) -> str:
    return urlparse(task.payload.get("url", "")).netloc


def _file_size(task: TaskItem) -> int:
    return int(task.result.get("file_size") or 0)


def _to_entry(task: TaskItem) -> dict[str, Any]:
    settings = dict(task.payload)
    url = settings.pop("url", "")
    return {
        "url": url,
        "title": task.title,
        "domain": _domain(task),
        "timestamp": task.completed_at or task.created_at,
        "output_files": list(task.output_files),
        "settings": settings,
        "file_size": _file_size(task),
        "status": task.status.value,
    }
