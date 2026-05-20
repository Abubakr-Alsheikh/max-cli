from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, TabbedContent, TabPane

from max_cli.interface.tui.widgets.config_panel import ConfigPanel
from max_cli.interface.tui.widgets.history_panel import HistoryPanel
from max_cli.interface.tui.widgets.queue_panel import QueuePanel
from max_cli.interface.tui.widgets.system_panel import SystemPanel


class MaxDashboardApp(App):
    """Interactive dashboard for Max CLI."""

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
    ]

    CSS = """
    * {
        scrollbar-background: $surface;
        scrollbar-background-hover: $surface-darken-1;
        scrollbar-color: $primary-lighten-2;
        scrollbar-color-active: $primary;
        scrollbar-corner-color: $surface;
    }

    MaxDashboardApp {
        background: $surface;
    }

    Header {
        background: $boost;
        color: $text;
        text-style: bold;
        border-bottom: solid $accent;
    }

    Header > HeaderTitle {
        dock: left;
        content-align: left middle;
        width: 1fr;
        padding: 0 2;
    }

    Footer {
        background: $boost;
        border-top: solid $accent;
    }

    TabbedContent {
        height: 1fr;
        padding: 0 1 1 1;
    }

    TabbedContent > ContentTab {
        padding: 0 2;
    }

    TabbedContent > ContentTab.-active {
        text-style: bold;
    }

    TabbedContent > TabPane {
        padding: 0 1;
    }

    QueuePanel, HistoryPanel, ConfigPanel, SystemPanel {
        padding: 1 2;
    }

    DataTable {
        height: 1fr;
        border: solid $accent;
        background: $surface;
    }

    DataTable > .datatable--header {
        background: $primary-background;
        text-style: bold;
    }

    DataTable > .datatable--row-cursor {
        background: $primary-lighten-3;
    }

    DataTable > .datatable--row-hover {
        background: $primary-darken-2;
    }

    DataTable > .datatable--row-selected {
        background: $primary;
    }

    #queue-actions, #history-controls, #config-actions, #system-actions {
        dock: bottom;
        height: auto;
        margin-top: 1;
    }

    Button {
        margin: 0 1;
    }

    Button:focus {
        text-style: bold;
    }

    .config-row {
        margin: 0 1;
        height: auto;
    }

    .config-label {
        width: 30;
        text-style: bold;
    }

    .config-section {
        margin: 1 0;
        padding: 1 2;
        border: tall $primary-background;
    }

    .config-section-title {
        text-style: bold;
        color: $accent;
        padding: 0 1;
        margin-bottom: 1;
    }

    #config-fields {
        height: 1fr;
    }

    #log-scroll {
        height: 12;
        border: solid $border;
        background: $surface-darken-1;
    }

    #system-info {
        padding: 1 2;
        border: tall $primary-background;
        margin: 1 0;
    }

    #disk-progress {
        margin: 1 0;
        height: auto;
    }

    .status-success {
        color: $success;
    }

    .status-warning {
        color: $warning;
    }

    .status-error {
        color: $error;
    }

    #history-detail {
        padding: 1 2;
        border: tall $accent;
        margin-top: 1;
        background: $surface-darken-1;
    }

    #history-filter {
        width: 40;
    }

    #config-search {
        width: 40;
        margin-bottom: 1;
    }

    #queue-title, #history-title, #config-title, #system-title {
        padding: 0 0 1 0;
    }

    #queue-status, #config-status, #config-source {
        padding: 1 0 0 0;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
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
        self.set_interval(2.0, self._refresh_active_panel)

    def _refresh_active_panel(self) -> None:
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
        for panel_id in ["#queue-panel", "#history-panel", "#system-panel"]:
            panel = self.query_one(panel_id)
            if hasattr(panel, "refresh_data"):
                panel.refresh_data()
