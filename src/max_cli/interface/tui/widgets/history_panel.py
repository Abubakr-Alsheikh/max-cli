from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Label, Select, Static

from max_cli.interface.tui.activity_log import ActivityLog


class HistoryPanel(Vertical):
    """Task history panel with filtering."""

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold cyan]\U0001f4cb Task History[/bold cyan]", id="history-title"
        )
        with Horizontal(id="history-controls"):
            yield Select(
                [
                    ("All Activity", "all"),
                    ("Downloads", "download"),
                    ("Tasks", "task"),
                    ("File Ops", "file_op"),
                    ("Commands", "command"),
                    ("AI", "ai"),
                ],
                value="all",
                id="history-category-filter",
                allow_blank=False,
            )
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
        category_select = self.query_one("#history-category-filter", Select)
        category = category_select.value
        if category == Select.BLANK:
            category = "all"

        filter_input = self.query_one("#history-filter", Input)
        filter_text = filter_input.value.strip().lower()

        activity = ActivityLog()
        category_filter = None if category == "all" else category
        entries = activity.get_entries(category_filter=category_filter, limit=200)

        if filter_text:
            entries = [
                e
                for e in entries
                if filter_text in e.action.lower()
                or filter_text in str(e.details).lower()
                or filter_text in e.status.lower()
            ]

        table = self.query_one("#history-table", DataTable)
        table.clear()
        if not table.columns:
            table.add_column("Time", width=18)
            table.add_column("Category", width=10)
            table.add_column("Action", width=20)
            table.add_column("Status", width=10)
            table.add_column("Details", width=40)
            table.add_column("Duration", width=10)

        if not entries:
            table.add_row(
                "",
                "",
                "[dim]No history entries found[/dim]",
                "",
                "",
                "",
            )

        for entry in entries:
            time_str = entry.timestamp[:19] if entry.timestamp else "N/A"
            status_color = "green" if entry.status == "success" else "red"
            details = str(entry.details.get("url", entry.details.get("target", "")))[
                :38
            ]

            table.add_row(
                time_str,
                entry.category,
                entry.action.replace("_", " ").title(),
                f"[{status_color}]{entry.status}[/{status_color}]",
                details,
                f"{entry.duration_ms:.0f}ms" if entry.duration_ms > 0 else "-",
                key=entry.id,
            )

        count_label = self.query_one("#history-count", Label)
        count_label.update(f"{len(entries)} items")

    @on(Select.Changed, "#history-category-filter")
    def _on_category_changed(self) -> None:
        self.refresh_data()

    @on(Input.Changed, "#history-filter")
    def _on_filter_changed(self) -> None:
        self.refresh_data()

    @on(DataTable.RowSelected)
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        activity = ActivityLog()
        entry = activity.get_entry(event.row_key.value)
        if entry:
            detail = self.query_one("#history-detail", Static)
            lines = [
                f"[bold]ID:[/bold] {entry.id}",
                f"[bold]Category:[/bold] {entry.category}",
                f"[bold]Action:[/bold] {entry.action}",
                f"[bold]Status:[/bold] {entry.status}",
                f"[bold]Time:[/bold] {entry.timestamp[:19]}",
                f"[bold]Duration:[/bold] {entry.duration_ms}ms",
            ]
            if entry.details:
                lines.append("[bold]Details:[/bold]")
                for k, v in entry.details.items():
                    lines.append(f"  {k}: {v}")
            detail.update("\n".join(lines))

    @on(Button.Pressed, "#btn-clear-history")
    def _on_clear_history(self) -> None:
        btn = self.query_one("#btn-clear-history", Button)
        if btn.label == "Confirm?":
            from max_cli.interface.tui.activity_log import ActivityLog

            activity = ActivityLog()
            activity.clear()
            btn.label = "Clear History"
            self.refresh_data()
            detail = self.query_one("#history-detail", Static)
            detail.update("")
            self.notify("History cleared", severity="information")
        else:
            btn.label = "Confirm?"
            self.set_timer(5.0, lambda: self._reset_confirm())

    def _reset_confirm(self) -> None:
        try:
            btn = self.query_one("#btn-clear-history", Button)
            if btn.label == "Confirm?":
                btn.label = "Clear History"
        except Exception:
            pass
