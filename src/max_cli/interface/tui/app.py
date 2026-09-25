from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Footer

from max_cli.interface.tui.widgets.analytics_panel import AnalyticsPanel
from max_cli.interface.tui.widgets.chat_panel import ChatPanel
from max_cli.interface.tui.widgets.config_panel import ConfigPanel
from max_cli.interface.tui.widgets.download_panel import DownloadPanel
from max_cli.interface.tui.widgets.files_panel import FilesPanel
from max_cli.interface.tui.widgets.history_panel import HistoryPanel
from max_cli.interface.tui.widgets.home_panel import HomePanel
from max_cli.interface.tui.widgets.queue_panel import QueuePanel
from max_cli.interface.tui.widgets.sidebar import Sidebar
from max_cli.interface.tui.widgets.system_panel import SystemPanel


class MaxDashboardApp(App):
    """Interactive dashboard for Max CLI."""

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("ctrl+b", "toggle_sidebar", "Sidebar"),
    ]

    CSS = """
    $primary: #0ea5e9;
    $accent: #8b5cf6;
    $surface: #1e293b;
    $boost: #334155;
    $panel: #0f172a;
    $border: #334155;
    $success: #22c55e;
    $warning: #eab308;
    $error: #ef4446;
    $text-muted: #64748b;

    MaxDashboardApp {
        layout: vertical;
        background: $panel;
    }

    #main-horizontal {
        height: 1fr;
    }

    #content {
        width: 1fr;
        height: 1fr;
    }

    #content > * {
        padding: 1 2;
        height: 1fr;
    }

    Footer {
        dock: bottom;
        height: auto;
    }

    DataTable {
        height: 1fr;
        border: solid $border;
    }

    Button {
        min-width: 12;
    }
    #sidebar .sidebar-btn {
        min-width: 0;
    }
    Button:hover {
        text-style: bold;
    }
    #sidebar .sidebar-btn {
        min-width: 0;
    }

    /* ── Shared bottom action bars ──────────────────────── */
    #queue-actions, #history-controls, #config-actions,
    #files-actions, #history-actions,
    #storage-actions, #quick-actions, #system-actions {
        height: auto;
        margin-top: 1;
        dock: bottom;
    }
    #storage-actions, #quick-actions, #system-actions {
        dock: none;
    }

    /* ── Config Panel ───────────────────────────────────── */
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
        background: $surface;
        padding: 0 1;
    }

    /* ══════════════════════════════════════════════════════
       HOME PANEL
       ══════════════════════════════════════════════════════ */

    #home-title {
        text-style: bold;
        padding: 0 1;
        margin-bottom: 0;
    }

    #home-subtitle {
        margin: 1 0 1 0;
        padding: 0 1;
        text-style: bold;
    }

    #home-status-bar {
        height: auto;
        margin: 1 0;
    }

    .status-metric {
        width: 1fr;
        height: auto;
        margin: 0 1;
        padding: 1;
        border: round $border;
        background: $surface;
    }
    .status-metric:hover {
        border: round $primary;
        background: $boost;
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

    #home-stats-row {
        height: auto;
        margin: 1 0;
    }

    .stat-card {
        width: 1fr;
        height: auto;
        border: round $border;
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

    #home-cards {
        height: auto;
    }

    .home-card {
        width: 1fr;
        height: auto;
        border: round $border;
        background: $surface;
        padding: 1;
        text-align: center;
        margin: 0 1;
    }
    .home-card:hover {
        border: round $primary;
        background: $boost;
    }
    .home-card Button {
        width: 100%;
        margin-top: 1;
    }
    .home-card Button:hover {
        text-style: bold;
    }

    .home-card-green  { border-left: heavy $success; }
    .home-card-yellow { border-left: heavy $warning; }
    .home-card-purple { border-left: heavy $accent;  }
    .home-card-green:hover,
    .home-card-yellow:hover,
    .home-card-purple:hover {
        background: $boost;
    }

    #home-activity-scroll {
        height: 1fr;
        border: round $border;
        background: $surface;
        padding: 0 1;
    }

    #home-activity-title {
        margin-top: 1;
    }

    #home-panel {
        overflow-y: auto;
    }

    /* ══════════════════════════════════════════════════════
       FILES PANEL
       ══════════════════════════════════════════════════════ */

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


    /* ══════════════════════════════════════════════════════
       CHAT PANEL
       ══════════════════════════════════════════════════════ */

    #chat-scroll {
        height: 1fr;
        border: solid $border;
        background: $surface;
    }
    #chat-messages {
        padding: 1;
    }

    .chat-msg {
        margin: 1 0;
        padding: 1;
        border: round $border;
    }
    .chat-msg-max {
        background: $surface;
        border: round $border;
    }
    .chat-msg-user {
        background: $boost;
        border: round $border;
        margin-left: 4;
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

    /* ══════════════════════════════════════════════════════
       ANALYTICS PANEL
       ══════════════════════════════════════════════════════ */

    #analytics-sys-title {
        text-style: bold;
        margin-top: 0;
    }
    #analytics-sys-info {
        height: auto;
        border: round $border;
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
        border: round $border;
        background: $surface;
        padding: 1;
    }

    .analytics-section-title {
        text-style: bold;
        margin-bottom: 1;
        border-bottom: solid $accent;
    }

    #analytics-cat-title {
        text-style: bold;
        margin-top: 1;
    }
    #analytics-category-bars {
        height: auto;
        border: round $border;
        background: $surface;
        padding: 1;
        margin: 1 0;
    }

    /* ══════════════════════════════════════════════════════
       SYSTEM PANEL
       ══════════════════════════════════════════════════════ */

    #system-info {
        height: auto;
        border: round $border;
        background: $surface;
        padding: 1;
        margin: 1 0;
    }
    #disk-title, #storage-title, #quick-actions-title, #system-log-title {
        text-style: bold;
        margin-top: 1;
    }
    #disk-progress {
        margin: 0 1;
    }
    #system-disk {
        height: auto;
        border: round $border;
        background: $surface;
        padding: 1;
        margin: 1 0;
    }
    #storage-details {
        height: auto;
        border: round $border;
        background: $surface;
        padding: 1;
        margin: 1 0;
    }

    /* ══════════════════════════════════════════════════════
       QUEUE PANEL
       ══════════════════════════════════════════════════════ */

    #queue-title {
        text-style: bold;
    }
    #queue-hint {
        color: $text-muted;
        margin: 0 1;
    }
    #queue-status {
        margin: 0 1;
        color: $text-muted;
    }

    /* ══════════════════════════════════════════════════════
       HISTORY PANEL
       ══════════════════════════════════════════════════════ */

    #history-title {
        text-style: bold;
    }
    #history-detail {
        height: auto;
        border: round $border;
        background: $surface;
        padding: 1;
        margin: 1 0;
    }
    #history-count {
        color: $text-muted;
        margin: 0 0 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="main-horizontal"):
            yield Sidebar(id="sidebar")
            with Container(id="content"):
                yield HomePanel(id="home-panel")
                yield DownloadPanel(id="download-panel")
                yield QueuePanel(id="queue-panel")
                yield HistoryPanel(id="history-panel")
                yield FilesPanel(id="files-panel")
                yield AnalyticsPanel(id="analytics-panel")
                yield ConfigPanel(id="config-panel")
                yield SystemPanel(id="system-panel")
                yield ChatPanel(id="chat-panel")
        yield Footer()

    def on_mount(self) -> None:
        sidebar = self.query_one(Sidebar)
        sidebar.set_active("home")
        self._show_panel("home")
        self.set_interval(2.0, self._refresh_active_panel)

    def _show_panel(self, section_id: str) -> None:
        for panel_id in [
            "home-panel",
            "download-panel",
            "queue-panel",
            "history-panel",
            "files-panel",
            "analytics-panel",
            "config-panel",
            "system-panel",
            "chat-panel",
        ]:
            widget = self.query_one(f"#{panel_id}")
            widget.display = False
        target_id = f"{section_id}-panel"
        try:
            target = self.query_one(f"#{target_id}")
            target.display = True
        except Exception:
            self.query_one("#home-panel").display = True

    def _refresh_active_panel(self) -> None:
        for panel_id, section in [
            ("#queue-panel", "queue"),
            ("#history-panel", "history"),
            ("#system-panel", "system"),
            ("#files-panel", "files"),
            ("#home-panel", "home"),
            ("#analytics-panel", "analytics"),
        ]:
            panel = self.query_one(panel_id)
            if panel.display:
                if hasattr(panel, "refresh_data"):
                    panel.refresh_data()
                break

    def action_toggle_sidebar(self) -> None:
        self.query_one(Sidebar).toggle_mode()

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

    def on_sidebar_section_selected(self, message: Sidebar.SectionSelected) -> None:
        sidebar = self.query_one(Sidebar)
        sidebar.set_active(message.section_id)
        self._show_panel(message.section_id)

    def action_switch_home(self) -> None:
        sidebar = self.query_one(Sidebar)
        sidebar.set_active("home")
        self._show_panel("home")

    def action_switch_download(self) -> None:
        sidebar = self.query_one(Sidebar)
        sidebar.set_active("download")
        self._show_panel("download")

    def action_switch_queue(self) -> None:
        sidebar = self.query_one(Sidebar)
        sidebar.set_active("queue")
        self._show_panel("queue")

    def action_switch_history(self) -> None:
        sidebar = self.query_one(Sidebar)
        sidebar.set_active("history")
        self._show_panel("history")

    def action_switch_files(self) -> None:
        sidebar = self.query_one(Sidebar)
        sidebar.set_active("files")
        self._show_panel("files")

    def action_switch_analytics(self) -> None:
        sidebar = self.query_one(Sidebar)
        sidebar.set_active("analytics")
        self._show_panel("analytics")

    def action_switch_config(self) -> None:
        sidebar = self.query_one(Sidebar)
        sidebar.set_active("config")
        self._show_panel("config")

    def action_switch_system(self) -> None:
        sidebar = self.query_one(Sidebar)
        sidebar.set_active("system")
        self._show_panel("system")

    def action_switch_chat(self) -> None:
        sidebar = self.query_one(Sidebar)
        sidebar.set_active("chat")
        self._show_panel("chat")

    def on_home_panel_command_selected(
        self, message: HomePanel.CommandSelected
    ) -> None:
        tab_map = {
            "grab": "download",
            "files": "files",
            "ai": "chat",
        }
        target = tab_map.get(message.category)
        if target:
            sidebar = self.query_one(Sidebar)
            sidebar.set_active(target)
            self._show_panel(target)
