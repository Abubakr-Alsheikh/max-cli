from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Label, Static

from max_cli.core.engines.daemon_manager import DaemonManager
from max_cli.core.engines.task_queue import TaskStatus


STATUS_ICONS = {
    TaskStatus.PENDING: "\u23f3",
    TaskStatus.RUNNING: "\u25b6",
    TaskStatus.COMPLETED: "\u2705",
    TaskStatus.FAILED: "\u274c",
    TaskStatus.CANCELLED: "\u23f9",
    TaskStatus.PAUSED: "\u23f8",
}


class QueuePanel(Vertical):
    """Live queue status panel with auto-refresh."""

    def compose(self) -> ComposeResult:
        yield Static("[bold cyan]\u26a1 Task Queue[/bold cyan]", id="queue-title")
        yield DataTable(id="queue-table")
        yield Static(
            "[dim]Press [bold]Enter[/bold] to select a task[/dim]",
            id="queue-hint",
        )
        with Horizontal(id="queue-actions"):
            yield Button("\u274c Cancel", id="btn-cancel", variant="error")
            yield Button("\u267b Retry", id="btn-retry", variant="warning")
            yield Button("\u23f8 Pause", id="btn-pause", variant="primary")
            yield Button("\U0001f9f9 Clear Done", id="btn-clear", variant="default")
        yield Label("", id="queue-status")

    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        daemon = DaemonManager()
        tasks = daemon.get_all()
        table = self.query_one("#queue-table", DataTable)

        table.clear()
        if not table.columns:
            table.add_column("ID", width=10)
            table.add_column("Type", width=16)
            table.add_column("Title", width=30)
            table.add_column("Status", width=14)
            table.add_column("Progress", width=14)
            table.add_column("ETA", width=10)

        if not tasks:
            table.add_row(
                "",
                "",
                "[dim]No tasks in queue[/dim]",
                "",
                "",
                "",
            )

        for task in tasks:
            status_style = self._status_style(task.status)
            icon = STATUS_ICONS.get(task.status, "")
            progress_str = self._format_progress(task.progress)
            eta_str = str(task.eta) if task.eta else "\u2014"

            title = task.title or ""
            if task.description and not title:
                title = task.description[:28]

            table.add_row(
                task.id,
                task.type.value,
                title,
                f"{icon} [{status_style}]{task.status.value}[/{status_style}]",
                progress_str,
                eta_str,
                key=task.id,
            )

        stats = daemon.get_stats()
        status_label = self.query_one("#queue-status", Label)
        status_label.update(
            f"  Pending: {stats.get('pending', 0)}  |  "
            f"Running: {stats.get('running', 0)}  |  "
            f"Failed: {stats.get('failed', 0)}"
        )

    @staticmethod
    def _format_progress(progress: float) -> str:
        if progress <= 0:
            return "[dim]\u2014[/dim]"
        filled = int(progress / 10)
        bar = "\u2588" * filled + "\u2591" * (10 - filled)
        color = "green" if progress >= 100 else "yellow" if progress >= 50 else "blue"
        return f"[{color}][{bar}] {progress:.0f}%[/{color}]"

    @staticmethod
    def _status_style(status: TaskStatus) -> str:
        status_map = {
            TaskStatus.PENDING: "yellow",
            TaskStatus.RUNNING: "blue",
            TaskStatus.COMPLETED: "green",
            TaskStatus.FAILED: "red",
            TaskStatus.CANCELLED: "dim",
            TaskStatus.PAUSED: "cyan",
        }
        return status_map.get(status, "white")

    @on(Button.Pressed, "#btn-cancel")
    def _on_cancel(self) -> None:
        table = self.query_one("#queue-table", DataTable)
        if table.cursor_coordinate is not None:
            row_idx = table.cursor_coordinate.row
            row_data = table.get_row_at(row_idx)
            task_id = row_data[0] if row_data else None
            if task_id:
                daemon = DaemonManager()
                daemon.cancel(str(task_id))
                self.refresh_data()

    @on(Button.Pressed, "#btn-retry")
    def _on_retry(self) -> None:
        table = self.query_one("#queue-table", DataTable)
        if table.cursor_coordinate is not None:
            row_idx = table.cursor_coordinate.row
            row_data = table.get_row_at(row_idx)
            task_id = row_data[0] if row_data else None
            if task_id:
                daemon = DaemonManager()
                daemon.retry(str(task_id))
                self.refresh_data()

    @on(Button.Pressed, "#btn-pause")
    def _on_pause(self) -> None:
        table = self.query_one("#queue-table", DataTable)
        if table.cursor_coordinate is not None:
            row_idx = table.cursor_coordinate.row
            row_data = table.get_row_at(row_idx)
            task_id = row_data[0] if row_data else None
            if task_id:
                daemon = DaemonManager()
                daemon.pause(str(task_id))
                self.refresh_data()

    @on(Button.Pressed, "#btn-clear")
    def _on_clear(self) -> None:
        daemon = DaemonManager()
        for status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            daemon.clear(status=status)
        self.refresh_data()
