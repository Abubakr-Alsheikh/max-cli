# Plan: Interactive Dashboard (TUI)

> Status: Completed
> Priority: P2
> Related: User Experience & Laziness (Feature 2C)

## Overview

Add an interactive Terminal User Interface (TUI) dashboard to Max CLI using the `textual` library. The dashboard provides a live, tabbed view of the task queue, history, configuration, and system metrics — replacing the need to run multiple static `max queue status`, `max queue history`, and `max config show` commands. The feature is delivered as an **optional dependency** (`max-cli[tui]`) so users who don't want the TUI overhead aren't forced to install it.

## Problem Analysis

Currently, monitoring background tasks and inspecting configuration requires running separate CLI commands that produce static output:

- `max queue status` — one-shot table snapshot
- `max queue history` — one-shot history table
- `max queue stats` — one-shot statistics panel
- `max config show` — one-shot settings table

There is **no live view** — users must re-run commands to see updated progress. There is **no interactive control** — canceling or retrying a task requires a separate command invocation. There is **no unified view** — queue, history, config, and system info are scattered across different subcommands.

## Goals

1. Provide a single `max dashboard` command that launches an interactive, auto-refreshing TUI.
2. Support tabbed navigation: Queue, History, Config, System.
3. Enable interactive actions: cancel tasks, retry tasks, edit config values, clear history.
4. Keep `textual` as an **optional** dependency — the core CLI must work without it.
5. Maintain strict Core/Interface separation — the TUI reads from `DaemonManager` and `Settings`, never from raw JSON files directly.
6. Achieve full test coverage using Textual's `Pilot` API for simulating user interactions.

## Implementation Details

### Phase 1: Optional Dependency in `pyproject.toml`

Add `textual` as an optional dependency group:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "ruff>=0.1.0",
    "mkdocs>=1.5.0",
    "mkdocs-material>=9.0.0",
]
ocr = [
    "pytesseract>=0.3.10",
]
tui = [
    "textual>=0.48.0",
]
```

No changes to the base `dependencies` list. Users install with:
```bash
pip install max-cli[tui]
```

### Phase 2: Directory Structure

Create the following structure under `src/max_cli/interface/tui/`:

```text
src/max_cli/interface/tui/
├── __init__.py
├── dashboard.py          # Typer command entry point (max dashboard)
├── app.py                # Main Textual App class
└── widgets/
    ├── __init__.py
    ├── queue_panel.py    # Live queue DataTable + action buttons
    ├── history_panel.py  # Scrollable history with filter Input
    ├── config_panel.py   # Editable Settings grid + Save button
    └── system_panel.py   # Disk usage, recent log lines
```

### Phase 3: Dashboard Entry Point (`dashboard.py`)

This file lives in `interface/tui/` and defines the `max dashboard` Typer command. It performs a lazy import check for `textual` and launches the app.

```python
"""src/max_cli/interface/tui/dashboard.py"""

import typer
from max_cli.common.logger import console

app = typer.Typer(help="Launch the interactive TUI dashboard")


@app.command()
def dashboard() -> None:
    """Launch the interactive Max CLI dashboard."""
    try:
        from max_cli.interface.tui.app import MaxDashboardApp
    except ImportError:
        console.print(
            "[yellow]The TUI dashboard requires the 'textual' library.[/yellow]\n"
            "Install it with: [bold]pip install max-cli[tui][/bold]"
        )
        raise typer.Exit(1)

    max_app = MaxDashboardApp()
    max_app.run()
```

**Registration**: Add to `src/max_cli/core/cli/commands/__init__.py` and `registry.py`:

```python
# In commands/__init__.py
from max_cli.core.cli.commands import tui
__all__ = [..., "tui"]

# In registry.py
commands.tui.register(app)
```

Create `src/max_cli/core/cli/commands/tui.py`:

```python
"""src/max_cli/core/cli/commands/tui.py"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typer import Typer


def register(app: "Typer") -> None:
    from max_cli.interface.tui.dashboard import app as dashboard_app
    app.add_typer(dashboard_app, name="dashboard")
```

### Phase 4: Main Textual App (`app.py`)

The main application class with `Tabs` for navigation. Each tab hosts a custom widget.

```python
"""src/max_cli/interface/tui/app.py"""

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, TabbedContent, TabPane

from max_cli.interface.tui.widgets.config_panel import ConfigPanel
from max_cli.interface.tui.widgets.history_panel import HistoryPanel
from max_cli.interface.tui.widgets.queue_panel import QueuePanel
from max_cli.interface.tui.widgets.system_panel import SystemPanel


class MaxDashboardApp(App):
    """Interactive dashboard for Max CLI."""

    CSS_PATH = None  # Inline CSS via DEFAULT_CSS

    DEFAULT_CSS = """
    MaxDashboardApp {
        layout: vertical;
    }
    TabbedContent {
        height: 1fr;
    }
    TabbedContent > TabPane {
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="queue"):
            with TabPane("Queue", id="queue"):
                yield QueuePanel(id="queue-panel")
            with TabPane("History", id="history"):
                yield HistoryPanel(id="history-panel")
            with TabPane("Config", id="config"):
                yield ConfigPanel(id="config-panel")
            with TabPane("System", id="system"):
                yield SystemPanel(id="system-panel")
        yield Footer()

    def on_mount(self) -> None:
        """Start auto-refresh timer for queue panel."""
        self.set_interval(2.0, self._refresh_active_panel)

    def _refresh_active_panel(self) -> None:
        """Refresh whichever tab is currently visible."""
        active = self.query_one(TabbedContent).active
        panel_map = {
            "queue": "#queue-panel",
            "history": "#history-panel",
            "system": "#system-panel",
        }
        if active in panel_map:
            panel = self.query_one(panel_map[active])
            if hasattr(panel, "refresh_data"):
                panel.refresh_data()

    def action_refresh(self) -> None:
        """Manual refresh of all panels."""
        for panel_id in ["#queue-panel", "#history-panel", "#system-panel"]:
            panel = self.query_one(panel_id)
            if hasattr(panel, "refresh_data"):
                panel.refresh_data()
```

### Phase 5: Queue Panel Widget (`widgets/queue_panel.py`)

Displays live task queue in a `DataTable` with status colors, progress bars, and action buttons (Cancel, Retry, Pause, Clear).

```python
"""src/max_cli/interface/tui/widgets/queue_panel.py"""

from textual import on
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Label, Static

from max_cli.core.engines.daemon_manager import DaemonManager
from max_cli.core.engines.task_queue import TaskStatus


class QueuePanel(Vertical):
    """Live queue status panel with auto-refresh."""

    def compose(self):
        yield Static("[bold]Task Queue[/bold]", id="queue-title")
        yield DataTable(id="queue-table")
        with Horizontal(id="queue-actions"):
            yield Button("Cancel Selected", id="btn-cancel", variant="error")
            yield Button("Retry Selected", id="btn-retry", variant="warning")
            yield Button("Pause Selected", id="btn-pause", variant="primary")
            yield Button("Clear Done", id="btn-clear", variant="default")
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
            table.add_column("Status", width=12)
            table.add_column("Progress", width=10)
            table.add_column("ETA", width=10)

        for task in tasks:
            status_style = self._status_style(task.status)
            progress_str = f"{task.progress:.0f}%" if task.progress > 0 else "—"
            eta_str = task.eta if task.eta else "—"

            table.add_row(
                task.id,
                task.type.value,
                task.title or task.description[:28],
                f"[{status_style}]{task.status.value}[/{status_style}]",
                progress_str,
                eta_str,
                key=task.id,
            )

        stats = daemon.get_stats()
        status_label = self.query_one("#queue-status", Label)
        status_label.update(
            f"  Pending: {stats['pending']}  |  "
            f"Running: {stats['running']}  |  "
            f"Failed: {stats['failed']}"
        )

    @staticmethod
    def _status_style(status: TaskStatus) -> str:
        return {
            TaskStatus.PENDING: "yellow",
            TaskStatus.RUNNING: "blue",
            TaskStatus.COMPLETED: "green",
            TaskStatus.FAILED: "red",
            TaskStatus.CANCELLED: "dim",
            TaskStatus.PAUSED: "cyan",
        }.get(status, "white")

    @on(Button.Pressed, "#btn-cancel")
    def _on_cancel(self) -> None:
        table = self.query_one("#queue-table", DataTable)
        if table.cursor_coordinate is not None:
            row_idx = table.cursor_coordinate.row
            row_key = table.get_row_at(row_idx)
            task_id = row_key[0] if row_key else None
            if task_id:
                daemon = DaemonManager()
                daemon.cancel(task_id)
                self.refresh_data()

    @on(Button.Pressed, "#btn-retry")
    def _on_retry(self) -> None:
        table = self.query_one("#queue-table", DataTable)
        if table.cursor_coordinate is not None:
            row_idx = table.cursor_coordinate.row
            row_key = table.get_row_at(row_idx)
            task_id = row_key[0] if row_key else None
            if task_id:
                daemon = DaemonManager()
                daemon.retry(task_id)
                self.refresh_data()

    @on(Button.Pressed, "#btn-pause")
    def _on_pause(self) -> None:
        table = self.query_one("#queue-table", DataTable)
        if table.cursor_coordinate is not None:
            row_idx = table.cursor_coordinate.row
            row_key = table.get_row_at(row_idx)
            task_id = row_key[0] if row_key else None
            if task_id:
                daemon = DaemonManager()
                daemon.pause(task_id)
                self.refresh_data()

    @on(Button.Pressed, "#btn-clear")
    def _on_clear(self) -> None:
        daemon = DaemonManager()
        daemon.clear(status=TaskStatus.COMPLETED)
        daemon.clear(status=TaskStatus.FAILED)
        daemon.clear(status=TaskStatus.CANCELLED)
        self.refresh_data()
```

### Phase 6: History Panel Widget (`widgets/history_panel.py`)

Scrollable history table with text filter input and detail view on row selection.

```python
"""src/max_cli/interface/tui/widgets/history_panel.py"""

from textual import on
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Input, Label, Static

from max_cli.core.engines.daemon_manager import DaemonManager
from max_cli.core.engines.task_queue import TaskType


class HistoryPanel(Vertical):
    """Task history panel with filtering."""

    def compose(self):
        yield Static("[bold]Task History[/bold]", id="history-title")
        with Horizontal(id="history-controls"):
            yield Input(placeholder="Filter by type (e.g. download)...", id="history-filter")
            yield Label("", id="history-count")
        yield DataTable(id="history-table")
        yield Static("", id="history-detail")

    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        filter_input = self.query_one("#history-filter", Input)
        filter_text = filter_input.value.strip().lower()

        daemon = DaemonManager()
        history = daemon.get_history(limit=200)

        if filter_text:
            history = [
                t for t in history
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

        for task in history:
            status_color = "green" if task.status == "completed" else "red"
            error_str = task.error[:28] if task.error else ""
            completed_str = task.completed_at[:19] if task.completed_at else "N/A"

            table.add_row(
                task.id,
                task.type.value,
                task.title or task.description[:28],
                f"[{status_color}]{task.status.value}[/{status_color}]",
                completed_str,
                f"[red]{error_str}[/red]" if error_str else "",
                key=task.id,
            )

        count_label = self.query_one("#history-count", Label)
        count_label.update(f"{len(history)} items")

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
                f"[bold]Created:[/bold] {task.created_at[:19]}",
                f"[bold]Completed:[/bold] {task.completed_at[:19] if task.completed_at else 'N/A'}",
                f"[bold]Retries:[/bold] {task.retry_count}/{task.max_retries}",
            ]
            if task.error:
                lines.append(f"[red][bold]Error:[/bold] {task.error}[/red]")
            if task.output_path:
                lines.append(f"[bold]Output:[/bold] {task.output_path}")
            detail.update("\n".join(lines))
```

### Phase 7: Config Panel Widget (`widgets/config_panel.py`)

Displays all `Settings` fields in an editable grid. Uses `Input` widgets for string/int/bool values with a Save button that writes back to the `.env` file.

```python
"""src/max_cli/interface/tui/widgets/config_panel.py"""

from pathlib import Path
from textual import on
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, Input, Label, Static

from max_cli.config import Settings


class ConfigPanel(Vertical):
    """Editable configuration panel."""

    def compose(self):
        yield Static("[bold]Configuration[/bold]", id="config-title")
        yield Label(
            "[dim]Settings from ~/.max_config.env[/dim]",
            id="config-source",
        )
        yield ScrollableContainer(Vertical(id="config-fields"))
        with Horizontal(id="config-actions"):
            yield Button("Save Changes", id="btn-save-config", variant="success")
            yield Button("Reset to Defaults", id="btn-reset-config", variant="error")
        yield Static("", id="config-status")

    def on_mount(self) -> None:
        self._build_fields()

    def _build_fields(self) -> None:
        container = self.query_one("#config-fields", Vertical)
        container.remove_children()

        settings = Settings()
        for field_name, field_info in Settings.model_fields.items():
            value = getattr(settings, field_name)
            label = Label(f"{field_name}:", classes="config-label")

            if isinstance(value, bool):
                input_widget = Input(value=str(value), id=f"cfg-{field_name}")
            elif isinstance(value, Path):
                input_widget = Input(value=str(value), id=f"cfg-{field_name}")
            elif isinstance(value, int):
                input_widget = Input(
                    value=str(value),
                    id=f"cfg-{field_name}",
                    type="integer",
                )
            else:
                # Mask API keys
                if "API_KEY" in field_name and value:
                    masked = str(value)[:8] + "..." if len(str(value)) > 8 else "***"
                    input_widget = Input(value=masked, id=f"cfg-{field_name}")
                else:
                    input_widget = Input(
                        value=str(value) if value is not None else "",
                        id=f"cfg-{field_name}",
                    )

            container.mount(Horizontal(label, input_widget, classes="config-row"))

    @on(Button.Pressed, "#btn-save-config")
    def _on_save(self) -> None:
        settings = Settings()
        env_path = Path.home() / ".max_config.env"

        lines = []
        for field_name in Settings.model_fields:
            input_widget = self.query_one(f"#cfg-{field_name}", Input)
            if input_widget:
                value = input_widget.value.strip()
                lines.append(f"{field_name}={value}")

        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        status = self.query_one("#config-status", Static)
        status.update("[green]Configuration saved to ~/.max_config.env[/green]")

    @on(Button.Pressed, "#btn-reset-config")
    def _on_reset(self) -> None:
        env_path = Path.home() / ".max_config.env"
        if env_path.exists():
            env_path.unlink()
        self._build_fields()
        status = self.query_one("#config-status", Static)
        status.update("[yellow]Reset to defaults. Restart CLI to apply.[/yellow]")
```

### Phase 8: System Panel Widget (`widgets/system_panel.py`)

Shows disk usage of `~/.max_cli/`, recent daemon log lines, and basic system info.

```python
"""src/max_cli/interface/tui/widgets/system_panel.py"""

import shutil
from pathlib import Path
from textual.containers import ScrollableContainer, Vertical
from textual.widgets import Label, Static

from max_cli.core.engines.daemon_manager import DaemonManager


class SystemPanel(Vertical):
    """System information and disk usage panel."""

    MAX_CLI_DIR = Path.home() / ".max_cli"

    def compose(self):
        yield Static("[bold]System Information[/bold]", id="system-title")
        yield Static("", id="system-disk")
        yield Static("[bold]Recent Activity[/bold]", id="system-log-title")
        yield ScrollableContainer(Static("", id="system-log"), id="log-scroll")

    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        self._update_disk_usage()
        self._update_recent_log()

    def _update_disk_usage(self) -> None:
        disk_widget = self.query_one("#system-disk", Static)

        if self.MAX_CLI_DIR.exists():
            total_size = self._get_dir_size(self.MAX_CLI_DIR)
            usage = shutil.disk_usage(self.MAX_CLI_DIR)
            pct = (usage.used / usage.total) * 100 if usage.total > 0 else 0

            disk_widget.update(
                f"  Max CLI Directory: {self.MAX_CLI_DIR}\n"
                f"  Data Size:         {self._format_bytes(total_size)}\n"
                f"  Disk Usage:        {usage.used / (1024**3):.1f} GB / "
                f"{usage.total / (1024**3):.1f} GB ({pct:.0f}%)\n"
                f"  Free Space:        {usage.free / (1024**3):.1f} GB"
            )
        else:
            disk_widget.update("  Max CLI directory not found.")

        # Queue summary
        daemon = DaemonManager()
        stats = daemon.get_stats()
        history = daemon.get_history(limit=1)
        last_task = history[0] if history else None

        summary_lines = [
            "",
            f"  Queue: {stats['total']} tasks "
            f"({stats['running']} running, {stats['pending']} pending)",
        ]
        if last_task:
            summary_lines.append(
                f"  Last task: {last_task.title or last_task.type.value} "
                f"[{'green' if last_task.status == 'completed' else 'red'}]"
                f"{last_task.status.value}[/]"
            )

        disk_widget.update(disk_widget.renderable + "\n".join(summary_lines))

    def _update_recent_log(self) -> None:
        log_widget = self.query_one("#system-log", Static)
        log_file = DaemonManager.DAEMON_LOG_FILE

        if log_file.exists():
            lines = log_file.read_text(encoding="utf-8").strip().split("\n")
            last_50 = lines[-50:]
            log_widget.update("\n".join(last_50))
        else:
            log_widget.update("  No daemon log found.")

    @staticmethod
    def _get_dir_size(path: Path) -> int:
        total = 0
        if path.is_dir():
            for p in path.rglob("*"):
                if p.is_file():
                    total += p.stat().st_size
        return total

    @staticmethod
    def _format_bytes(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
```

### Phase 9: Inline CSS Styling

Add shared CSS to `app.py` via `DEFAULT_CSS` for consistent panel styling:

```css
/* Embedded in app.py DEFAULT_CSS */

QueuePanel, HistoryPanel, ConfigPanel, SystemPanel {
    padding: 1 2;
}

DataTable {
    height: 1fr;
    border: solid $accent;
}

#queue-actions, #history-controls, #config-actions {
    dock: bottom;
    height: auto;
    margin-top: 1;
}

.config-row {
    margin: 0 1;
    height: auto;
}

.config-label {
    width: 30;
    text-style: bold;
}

#config-fields {
    height: 1fr;
}

#log-scroll {
    height: 12;
    border: solid $border;
}
```

### Phase 10: Command Registration

1. Create `src/max_cli/core/cli/commands/tui.py` (shown in Phase 3).
2. Update `src/max_cli/core/cli/commands/__init__.py`:

```python
from max_cli.core.cli.commands import (
    ai, audio, config, files, media, network,
    plugins as plugin_commands, queue, tools, tui,
)

__all__ = [
    "ai", "audio", "config", "files", "media", "network",
    "plugin_commands", "queue", "tools", "tui",
]
```

3. Update `src/max_cli/core/cli/registry.py`:

```python
def register(app: "Typer") -> None:
    # ...existing registrations...
    commands.tui.register(app)
```

## Testing Strategy

### Test File: `tests/interface/tui/test_dashboard.py`

```python
"""tests/interface/tui/test_dashboard.py"""

import pytest
from textual.testing import Pilot
from unittest.mock import patch, MagicMock

from max_cli.interface.tui.app import MaxDashboardApp


@pytest.fixture
def mock_daemon():
    """Mock DaemonManager to avoid file I/O."""
    with patch("max_cli.interface.tui.widgets.queue_panel.DaemonManager") as mock:
        daemon = MagicMock()
        daemon.get_all.return_value = []
        daemon.get_stats.return_value = {
            "total": 0, "pending": 0, "running": 0,
            "failed": 0, "paused": 0, "by_type": {},
        }
        mock.return_value = daemon
        yield daemon


class TestMaxDashboardApp:
    """Test the dashboard app launches and renders."""

    @pytest.mark.asyncio
    async def test_app_starts(self, mock_daemon):
        """App should mount without errors."""
        async with MaxDashboardApp().run_test() as pilot:
            assert pilot.app.query_one("TabbedContent") is not None

    @pytest.mark.asyncio
    async def test_queue_panel_renders_empty(self, mock_daemon):
        """Queue panel should show empty state."""
        async with MaxDashboardApp().run_test() as pilot:
            table = pilot.app.query_one("#queue-table")
            assert table.row_count == 0

    @pytest.mark.asyncio
    async def test_queue_panel_shows_tasks(self, mock_daemon):
        """Queue panel should display tasks from DaemonManager."""
        from max_cli.core.engines.task_queue import TaskItem, TaskType, TaskStatus

        mock_task = TaskItem(
            id="abc123",
            type=TaskType.DOWNLOAD,
            status=TaskStatus.RUNNING,
            title="Test Download",
            progress=45.0,
        )
        mock_daemon.get_all.return_value = [mock_task]

        async with MaxDashboardApp().run_test() as pilot:
            panel = pilot.app.query_one("#queue-panel")
            panel.refresh_data()
            await pilot.pause()

            table = pilot.app.query_one("#queue-table")
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_cancel_button_calls_daemon(self, mock_daemon):
        """Cancel button should call daemon.cancel with selected task ID."""
        from max_cli.core.engines.task_queue import TaskItem, TaskType, TaskStatus

        mock_task = TaskItem(
            id="abc123",
            type=TaskType.DOWNLOAD,
            status=TaskStatus.PENDING,
            title="Test",
        )
        mock_daemon.get_all.return_value = [mock_task]

        async with MaxDashboardApp().run_test() as pilot:
            panel = pilot.app.query_one("#queue-panel")
            panel.refresh_data()
            await pilot.pause()

            # Select first row
            table = pilot.app.query_one("#queue-table")
            table.cursor_coordinate = (0, 0)

            # Press cancel
            btn = pilot.app.query_one("#btn-cancel")
            await btn.press()
            await pilot.pause()

            mock_daemon.cancel.assert_called_once_with("abc123")

    @pytest.mark.asyncio
    async def test_history_filter(self, mock_daemon):
        """History panel should filter tasks by text input."""
        from max_cli.core.engines.task_queue import TaskItem, TaskType, TaskStatus

        tasks = [
            TaskItem(id="t1", type=TaskType.DOWNLOAD, status=TaskStatus.COMPLETED, title="Video 1"),
            TaskItem(id="t2", type=TaskType.VIDEO_COMPRESS, status=TaskStatus.COMPLETED, title="Compressed"),
        ]
        mock_daemon.get_history.return_value = tasks

        async with MaxDashboardApp().run_test() as pilot:
            # Switch to history tab
            tabs = pilot.app.query_one("TabbedContent")
            tabs.active = "history"
            await pilot.pause()

            panel = pilot.app.query_one("#history-panel")
            panel.refresh_data()
            await pilot.pause()

            table = pilot.app.query_one("#history-table")
            assert table.row_count == 2

            # Apply filter
            filter_input = pilot.app.query_one("#history-filter")
            filter_input.value = "download"
            await pilot.pause()

            panel.refresh_data()
            await pilot.pause()

            # Should only show download tasks
            table = pilot.app.query_one("#history-table")
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_auto_refresh_timer(self, mock_daemon):
        """Auto-refresh should call refresh_data periodically."""
        async with MaxDashboardApp().run_test() as pilot:
            # Advance time by 3 seconds (interval is 2s)
            await pilot.pause()
            await pilot.app._refresh_panel()

            # Should not raise
            assert True


class TestDashboardCommand:
    """Test the Typer entry point."""

    def test_dashboard_missing_textual(self):
        """Should show install message when textual is not available."""
        from typer.testing import CliRunner
        from max_cli.interface.tui.dashboard import app

        runner = CliRunner()

        with patch.dict("sys.modules", {"textual": None}):
            # Force reimport to trigger ImportError
            import importlib
            import max_cli.interface.tui.app
            if "max_cli.interface.tui.app" in sys.modules:
                del sys.modules["max_cli.interface.tui.app"]

            result = runner.invoke(app, ["dashboard"])
            assert result.exit_code == 1
            assert "pip install max-cli[tui]" in result.output
```

### Test File: `tests/interface/tui/test_widgets.py`

```python
"""tests/interface/tui/test_widgets.py"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from max_cli.interface.tui.widgets.system_panel import SystemPanel


class TestSystemPanel:
    """Test system panel rendering."""

    @pytest.mark.asyncio
    async def test_disk_usage_renders(self):
        """Panel should display disk usage info."""
        with patch("max_cli.interface.tui.widgets.system_panel.DaemonManager") as mock_dm:
            mock_daemon = MagicMock()
            mock_daemon.get_stats.return_value = {"total": 0, "running": 0, "pending": 0}
            mock_daemon.get_history.return_value = []
            mock_dm.return_value = mock_daemon

            async with SystemPanel().run_test() as pilot:
                disk_widget = pilot.app.query_one("#system-disk")
                assert disk_widget.renderable != ""

    @pytest.mark.asyncio
    async def test_format_bytes(self):
        """Helper should format bytes correctly."""
        assert SystemPanel._format_bytes(512) == "512.0 B"
        assert SystemPanel._format_bytes(1536) == "1.5 KB"
        assert SystemPanel._format_bytes(1048576) == "1.0 MB"
        assert SystemPanel._format_bytes(1073741824) == "1.0 GB"
```

### Running Tests

```bash
pytest tests/interface/tui/ -v
```

Note: Textual tests require `pytest-asyncio`. Add to `pyproject.toml` dev dependencies:

```toml
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "pytest-asyncio>=0.21.0",
    "ruff>=0.1.0",
    "mkdocs>=1.5.0",
    "mkdocs-material>=9.0.0",
]
```

And add to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

## Migration Path

### Backward Compatibility

- **No breaking changes**. All existing `max queue *` and `max config *` commands remain fully functional.
- The TUI is purely additive — it reads from the same `DaemonManager` and `Settings` sources as the existing CLI commands.
- Users without `textual` installed see a friendly install prompt, not a crash.

### Phased Rollout

1. **Phase 1 (This plan)**: Core dashboard with Queue, History, Config, System tabs.
2. **Phase 2 (Future)**: Add a `max dashboard --headless` mode that outputs JSON for scripting.
3. **Phase 3 (Future)**: Add a `NotificationPanel` widget that listens to the `EventEmitter` system for real-time task completion alerts.
4. **Phase 4 (Future)**: Add a `SearchPanel` with fuzzy file search across `~/.max_cli/`.

### Deprecation Consideration

Once the TUI is mature, the individual `max queue status` / `max queue history` commands could be marked as `[deprecated]` in their Typer help text, directing users to `max dashboard` instead. This is **not** part of this plan.

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| `textual` version incompatibility | Dashboard crashes on launch | Pin `textual>=0.48.0,<1.0.0` in optional deps. Test against latest minor. |
| `DaemonManager` file lock contention | TUI reads stale/corrupt queue data | `DaemonManager` uses `threading.Lock` — TUI creates a fresh instance per refresh, which is safe for reads. For writes (cancel/retry), the lock serializes access. |
| Large history (200+ items) slows DataTable | UI lag on History tab | Limit `get_history(limit=200)` and add pagination in Phase 2. |
| Config save overwrites user's manual `.env` edits | User loses custom settings | Save writes all fields — if a field wasn't displayed (e.g., new field added in a future version), it won't be preserved. Mitigation: read existing file, merge changes, write back. |
| Windows terminal rendering issues | Broken layout on cmd.exe | Textual supports Windows via `windows-curses`. Document that Windows users should use Windows Terminal or PowerShell 7 for best results. |
| Auto-refresh causes flicker | Poor UX | Use Textual's `set_interval` which only updates changed rows via DataTable's keyed rows, not full re-render. |

## Success Criteria

- [ ] `pip install max-cli[tui]` installs `textual` without conflicts.
- [ ] `max dashboard` launches the TUI with 4 tabs (Queue, History, Config, System).
- [ ] Queue tab auto-refreshes every 2 seconds and shows live task status/progress.
- [ ] Queue tab action buttons (Cancel, Retry, Pause, Clear) work correctly.
- [ ] History tab filters tasks by text input in real time.
- [ ] History tab row selection shows full task details.
- [ ] Config tab displays all `Settings` fields and saves changes to `~/.max_config.env`.
- [ ] System tab shows disk usage of `~/.max_cli/` and recent daemon log lines.
- [ ] Running `max dashboard` without `textual` installed shows a clear install prompt.
- [ ] All TUI tests pass with mocked `DaemonManager` (no real file I/O or network).
- [ ] `ruff check`, `mypy`, and `pytest` all pass on the new code.
- [ ] Documentation updated: `README.md` includes `max dashboard` usage examples.
