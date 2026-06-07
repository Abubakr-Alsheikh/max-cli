from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, TabbedContent, TabPane

from max_cli.interface.tui.widgets.chat_panel import ChatPanel
from max_cli.interface.tui.widgets.config_panel import ConfigPanel
from max_cli.interface.tui.widgets.download_panel import DownloadPanel
from max_cli.interface.tui.widgets.files_panel import FilesPanel
from max_cli.interface.tui.widgets.history_panel import HistoryPanel
from max_cli.interface.tui.widgets.analytics_panel import AnalyticsPanel
from max_cli.interface.tui.widgets.home_panel import HomePanel
from max_cli.interface.tui.widgets.queue_panel import QueuePanel
from max_cli.interface.tui.widgets.system_panel import SystemPanel


class MaxDashboardApp(App):
    """Interactive dashboard for Max CLI."""

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
    ]

    CSS = """
    MaxDashboardApp {
        layout: vertical;
    }
    TabbedContent {
        height: 1fr;
    }
    TabbedContent > TabPane {
        padding: 0 1;
        overflow-y: auto;
    }
    QueuePanel, HistoryPanel, ConfigPanel, SystemPanel, DownloadPanel, FilesPanel, HomePanel, ChatPanel, AnalyticsPanel {
        padding: 1 2;
    }

    /* ── General Widgets ───────────────────────────── */
    DataTable {
        height: 1fr;
        border: solid $accent;
    }
    Footer {
        dock: bottom;
        height: auto;
    }
    Button {
        min-width: 12;
    }
    Button:hover {
        text-style: bold;
    }

    /* ── Queue / History / Config shared ───────────── */
    #queue-actions, #history-controls, #config-actions, #files-actions, #form-actions, #history-actions {
        height: auto;
        margin-top: 1;
        dock: bottom;
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
        height: 8;
        border: solid $border;
    }

    /* ── Home Panel — Status Bar ───────────────────── */
    #home-status-bar {
        height: auto;
        margin: 1 0;
    }
    .status-metric {
        width: 1fr;
        height: auto;
        margin: 0 1;
        padding: 1;
        border: round $surface;
        background: $surface;
    }
    .status-metric:hover {
        border: round $accent;
    }
    .metric-label {
        text-style: bold;
        margin-bottom: 0;
        padding: 0 0;
    }
    .metric-value {
        text-align: right;
        margin-top: 0;
        padding: 0 0;
    }

    /* ── Home Panel — Stat Cards ───────────────────── */
    #home-stats-row {
        height: auto;
        margin: 1 0;
    }
    .stat-card {
        width: 1fr;
        height: auto;
        border: round $surface;
        background: $surface;
        padding: 1;
        text-align: center;
        margin: 0 1;
    }
    .stat-card:hover {
        border: round $primary;
        background: $boost;
    }
    .stat-number {
        text-style: bold;
        text-align: center;
    }
    .stat-label {
        text-align: center;
        color: $text-muted;
    }

    /* ── Home Panel — Quick Action Cards ───────────── */
    #home-cards {
        height: auto;
    }
    .home-card {
        width: 1fr;
        height: auto;
        border: round $surface;
        background: $surface;
        padding: 1;
        text-align: center;
        margin: 0 1;
    }
    .home-card:hover {
        border: heavy $primary;
        background: $boost;
    }
    .home-card Button {
        width: 100%;
        margin-top: 1;
    }
    .home-card Button:hover {
        text-style: bold;
    }
    .home-card-grab { border: round $success; }
    .home-card-files { border: round $warning; }
    .home-card-ai { border: round $accent; }
    .home-card-grab:hover, .home-card-files:hover, .home-card-ai:hover {
        background: $boost;
    }
    #home-activity-scroll {
        height: 1fr;
        border: round $surface;
        background: $surface;
        padding: 0 1;
    }
    #home-title {
        text-style: bold;
        padding: 0 1;
        margin-bottom: 0;
    }
    #home-subtitle {
        margin: 0 0 1 0;
        padding: 0 1;
    }
    #home-activity-title {
        margin-top: 1;
    }
    #home-panel {
        overflow-y: auto;
    }

    /* ── Files Panel ───────────────────────────────── */
    #files-nav {
        height: auto;
        margin-bottom: 1;
    }
    #filter-label, #sort-label {
        margin: 0 0 0 1;
    }
    #files-filter {
        width: 20;
    }
    #files-sort {
        width: 16;
    }
    #files-count {
        margin: 0 0 0 1;
    }

    /* ── Download Panel ────────────────────────────── */
    #download-options {
        height: auto;
        margin: 1 0;
    }
    #output-row {
        height: auto;
        margin-bottom: 1;
    }
    #download-actions {
        height: auto;
        margin: 1 0;
    }
    #recent-scroll {
        height: 8;
        border: solid $border;
    }

    /* ── Chat Panel ────────────────────────────────── */
    #chat-scroll {
        height: 1fr;
        border: solid $border;
    }
    #chat-messages {
        padding: 1;
    }
    .chat-msg {
        margin: 1 0;
        padding: 1;
    }
    .chat-msg-max {
        background: $surface;
    }
    .chat-msg-user {
        background: $boost;
    }
    #chat-suggestions {
        height: auto;
        margin: 1 0;
    }
    #chat-suggestions Button {
        margin: 0 1;
    }
    #chat-input-row {
        height: auto;
        dock: bottom;
    }
    #chat-input {
        width: 1fr;
    }

    /* ── Analytics Panel ───────────────────────────── */
    #analytics-sys-info {
        height: auto;
        border: round $surface;
        background: $surface;
        padding: 1;
        margin: 1 0;
    }
    #analytics-stats-row {
        height: auto;
        grid-size: 2;
        grid-gutter: 1;
    }
    .analytics-section {
        height: auto;
        border: round $surface;
        background: $surface;
        padding: 1;
    }
    .analytics-section-title {
        text-style: bold;
        margin-bottom: 1;
        border-bottom: solid $accent;
    }
    #analytics-category-bars {
        height: auto;
        border: round $surface;
        background: $surface;
        padding: 1;
        margin: 1 0;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="home"):
            with TabPane("Home", id="home"):
                yield HomePanel(id="home-panel")
            with TabPane("Download", id="download"):
                yield DownloadPanel(id="download-panel")
            with TabPane("Queue", id="queue"):
                yield QueuePanel(id="queue-panel")
            with TabPane("History", id="history"):
                yield HistoryPanel(id="history-panel")
            with TabPane("Files", id="files"):
                yield FilesPanel(id="files-panel")
            with TabPane("Analytics", id="analytics"):
                yield AnalyticsPanel(id="analytics-panel")
            with TabPane("Config", id="config"):
                yield ConfigPanel(id="config-panel")
            with TabPane("System", id="system"):
                yield SystemPanel(id="system-panel")
            with TabPane("AI Chat", id="chat"):
                yield ChatPanel(id="chat-panel")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(2.0, self._refresh_active_panel)

    def _refresh_active_panel(self) -> None:
        active = self.query_one(TabbedContent).active
        panel_map = {
            "queue": "#queue-panel",
            "history": "#history-panel",
            "system": "#system-panel",
            "files": "#files-panel",
            "home": "#home-panel",
            "analytics": "#analytics-panel",
        }
        if active in panel_map:
            panel = self.query_one(panel_map[active])
            if hasattr(panel, "refresh_data"):
                panel.refresh_data()

    def action_refresh(self) -> None:
        for panel_id in [
            "#queue-panel",
            "#history-panel",
            "#system-panel",
            "#files-panel",
            "#home-panel",
            "#analytics-panel",
        ]:
            panel = self.query_one(panel_id)
            if hasattr(panel, "refresh_data"):
                panel.refresh_data()

    def action_switch_home(self) -> None:
        self.query_one("TabbedContent").active = "home"

    def action_switch_download(self) -> None:
        self.query_one("TabbedContent").active = "download"

    def action_switch_queue(self) -> None:
        self.query_one("TabbedContent").active = "queue"

    def action_switch_history(self) -> None:
        self.query_one("TabbedContent").active = "history"

    def action_switch_files(self) -> None:
        self.query_one("TabbedContent").active = "files"

    def action_switch_config(self) -> None:
        self.query_one("TabbedContent").active = "config"

    def action_switch_system(self) -> None:
        self.query_one("TabbedContent").active = "system"

    def action_switch_chat(self) -> None:
        self.query_one("TabbedContent").active = "ai-chat"

    def on_home_panel_command_selected(
        self, message: HomePanel.CommandSelected
    ) -> None:
        tabs = self.query_one(TabbedContent)
        tab_map = {
            "grab": "download",
            "files": "files",
            "ai": "chat",
        }
        if message.category in tab_map:
            tabs.active = tab_map[message.category]
