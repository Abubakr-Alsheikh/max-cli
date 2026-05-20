from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Label, Static

from max_cli.core.engines.daemon_manager import DaemonManager


class HistoryPanel(Vertical):
    """Task history panel with filtering."""

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold cyan]\U0001f4cb Task History[/bold cyan]", id="history-title"
        )
        with Horizontal(id="history-controls"):
            yield Input(
                placeholder="\U0001f50d Filter by type, title, or ID...",
                id="history-filter",
            )
            yield Label("", id="history-count")
        yield DataTable(id="history-table")
        yield Static("", id="history-detail")
        with Horizontal(id="history-actions"):
            yield Button(
                "\U0001f9f9 Clear History", id="btn-clear-history", variant="error"
            )

    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        filter_input = self.query_one("#history-filter", Input)
        filter_text = filter_input.value.strip().lower()

        daemon = DaemonManager()
        history = daemon.get_history(limit=200)

        if filter_text:
            history = [
                t
                for t in history
                if filter_text in t.type.value
                or filter_text in (t.title or "").lower()
                or filter_text in t.id.lower()
            ]

        table = self.query_one("#history-table", DataTable)
        table.clear()
        if not table.columns:
            table.add_column("ID", width=10)
            table.add_column("Type", width=16)
            table.add_column("Title", width=30)
            table.add_column("Status", width=12)
            table.add_column("Completed", width=20)
            table.add_column("Error", width=30)

        if not history:
            table.add_row(
                "",
                "",
                "[dim]No history entries found[/dim]",
                "",
                "",
                "",
            )

        for task in history:
            status_color = "green" if task.status.value == "completed" else "red"
            error_str = (task.error or "")[:28]
            completed_str = (task.completed_at or "N/A")[:19]
            title = task.title or ""
            if task.description and not title:
                title = task.description[:28]

            table.add_row(
                task.id,
                task.type.value,
                title,
                f"[{status_color}]{task.status.value}[/{status_color}]",
                completed_str,
                f"[red]{error_str}[/red]" if error_str else "",
                key=task.id,
            )

        count_label = self.query_one("#history-count", Label)
        count_label.update(f"[dim]{len(history)} items[/dim]")

    @on(Input.Changed, "#history-filter")
    def _on_filter_changed(self) -> None:
        self.refresh_data()

    @on(DataTable.RowSelected)
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        daemon = DaemonManager()
        task = daemon.get(event.row_key.value)
        if task:
            detail = self.query_one("#history-detail", Static)
            lines = [
                f"[bold]ID:[/bold] {task.id}",
                f"[bold]Type:[/bold] {task.type.value}",
                f"[bold]Title:[/bold] {task.title or 'N/A'}",
                f"[bold]Status:[/bold] {task.status.value}",
                f"[bold]Progress:[/bold] {task.progress:.0f}%",
                f"[bold]Created:[/bold] {(task.created_at or '')[:19]}",
                f"[bold]Completed:[/bold] {(task.completed_at or 'N/A')[:19]}",
                f"[bold]Retries:[/bold] {task.retry_count}/{task.max_retries}",
            ]
            if task.error:
                lines.append(f"[red][bold]Error:[/bold] {task.error}[/red]")
            if task.output_path:
                lines.append(f"[bold]Output:[/bold] {task.output_path}")
            detail.update("\n".join(lines))

    @on(Button.Pressed, "#btn-clear-history")
    def _on_clear_history(self) -> None:
        daemon = DaemonManager()
        daemon.clear_history()
        self.refresh_data()
        detail = self.query_one("#history-detail", Static)
        detail.update("")
