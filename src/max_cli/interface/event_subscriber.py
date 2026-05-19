from typing import Optional

from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
)

from max_cli.common.events import (
    BatchProgressEvent,
    CompleteEvent,
    DownloadCompleteEvent,
    DownloadProgressEvent,
    EventEmitter,
    FileCompleteEvent,
    FileErrorEvent,
    FileStartEvent,
    MaxEvent,
    ProgressEvent,
    StatusEvent,
)
from max_cli.common.logger import console
from max_cli.common.utils import format_size


def _format_speed(bytes_per_sec: float) -> str:
    if bytes_per_sec <= 0:
        return ""
    base = format_size(bytes_per_sec)
    return base.rstrip()


def _format_eta(seconds: int) -> str:
    if seconds <= 0:
        return ""
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    remaining = seconds % 60
    return f"{minutes}m {remaining}s"


class EventSubscriber:
    def __init__(self, emitter: EventEmitter):
        self._emitter = emitter
        self._progress: Optional[Progress] = None
        self._batch_task: Optional[TaskID] = None
        self._file_tasks: dict[str, TaskID] = {}
        self._download_task: Optional[TaskID] = None
        self._stats: dict[str, int] = {"success": 0, "failed": 0, "total": 0}

    def _handle_event(self, event: MaxEvent) -> None:
        if event.type == "batch_progress":
            self._on_batch_progress(event)
        elif event.type == "file_start":
            self._on_file_start(event)
        elif event.type == "file_complete":
            self._on_file_complete(event)
        elif event.type == "file_error":
            self._on_file_error(event)
        elif event.type == "status":
            self._on_status(event)
        elif event.type == "progress":
            self._on_progress(event)
        elif event.type == "complete":
            self._on_complete(event)
        elif event.type == "download_progress":
            self._on_download_progress(event)
        elif event.type == "download_complete":
            self._on_download_complete(event)

    def _on_batch_progress(self, event: BatchProgressEvent) -> None:
        if self._progress and self._batch_task:
            self._progress.update(
                self._batch_task,
                completed=event.current,
                description=f"[green]{event.description}[/green] ({event.current}/{event.total})",
            )

    def _on_file_start(self, event: FileStartEvent) -> None:
        if self._progress:
            task_id = self._progress.add_task(
                f"[cyan]{event.action}[/cyan] {event.file}",
                total=1,
            )
            self._file_tasks[event.file] = task_id

    def _on_file_complete(self, event: FileCompleteEvent) -> None:
        self._stats["success"] += 1
        if event.file in self._file_tasks:
            task_id = self._file_tasks.pop(event.file)
            if self._progress:
                self._progress.update(task_id, completed=1)

    def _on_file_error(self, event: FileErrorEvent) -> None:
        self._stats["failed"] += 1
        if event.file in self._file_tasks:
            task_id = self._file_tasks.pop(event.file)
            if self._progress:
                self._progress.update(
                    task_id,
                    description=f"[red]{event.file}: {event.error}[/red]",
                )

    def _on_status(self, event: StatusEvent) -> None:
        console.print(f"[dim]{event.message}[/dim]")

    def _on_progress(self, event: ProgressEvent) -> None:
        if self._progress and event.file in self._file_tasks:
            task_id = self._file_tasks[event.file]
            self._progress.update(
                task_id,
                completed=event.percentage / 100,
                description=f"[cyan]{event.file}[/cyan] {event.percentage:.1f}%",
            )

    def _on_complete(self, event: CompleteEvent) -> None:
        summary = event.summary
        console.print(
            f"[green]Done:[/green] {summary.get('successful', 0)} succeeded, "
            f"[red]{summary.get('failed', 0)} failed[/red] "
            f"out of {summary.get('total', 0)} total"
        )

    def _on_download_progress(self, event: DownloadProgressEvent) -> None:
        if not self._progress:
            return
        if self._download_task is None:
            self._download_task = self._progress.add_task(
                "[cyan]Downloading[/cyan]",
                total=100,
            )
        pct = round(event.percentage)
        speed_str = _format_speed(event.speed)
        eta_str = _format_eta(event.eta)
        filename = (
            event.filename.split("/")[-1].split("\\")[-1] if event.filename else ""
        )
        detail_parts = []
        if speed_str:
            detail_parts.append(f"[dim]{speed_str}/s[/dim]")
        if eta_str:
            detail_parts.append(f"[dim]{eta_str}[/dim]")
        detail = "  ".join(detail_parts)
        description = f"[cyan]{filename}[/cyan]  [bold]{pct}%[/bold]  {detail}"
        self._progress.update(
            self._download_task,
            completed=pct,
            description=description,
        )

    def _on_download_complete(self, event: DownloadCompleteEvent) -> None:
        if self._progress and self._download_task is not None:
            filename = (
                event.filename.split("/")[-1].split("\\")[-1] if event.filename else ""
            )
            size_str = format_size(event.total_bytes) if event.total_bytes > 0 else ""
            description = f"[green]{filename}[/green]  [dim]{size_str}[/dim]"
            self._progress.update(
                self._download_task,
                completed=100,
                description=description,
            )
        self._download_task = None

    def subscribe(self) -> None:
        self._emitter.subscribe(self._handle_event)

    def unsubscribe(self) -> None:
        self._emitter.unsubscribe(self._handle_event)

    def create_progress_context(self, total: int, description: str = "Processing..."):
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None),
            TextColumn("{task.percentage:>3.0f}%"),
            transient=True,
        )
        self._batch_task = self._progress.add_task(description, total=total)
        return self._progress
