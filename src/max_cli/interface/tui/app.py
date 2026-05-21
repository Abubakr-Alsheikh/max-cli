from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, TabbedContent, TabPane

from max_cli.interface.tui.widgets.chat_panel import ChatPanel
from max_cli.interface.tui.widgets.config_panel import ConfigPanel
from max_cli.interface.tui.widgets.download_panel import DownloadPanel
from max_cli.interface.tui.widgets.files_panel import FilesPanel
from max_cli.interface.tui.widgets.history_panel import HistoryPanel
from max_cli.interface.tui.widgets.home_panel import HomePanel
from max_cli.interface.tui.widgets.queue_panel import QueuePanel
from max_cli.interface.tui.widgets.system_panel import SystemPanel
from max_cli.interface.tui.widgets.tools_panel import ToolsPanel


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
    }
    QueuePanel, HistoryPanel, ConfigPanel, SystemPanel, DownloadPanel, FilesPanel, ToolsPanel, HomePanel, ChatPanel {
        padding: 1 2;
    }
    DataTable {
        height: 1fr;
        border: solid $accent;
    }
    #queue-actions, #history-controls, #config-actions, #files-actions, #form-actions {
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
    .home-card {
        width: 1fr;
        height: auto;
        border: solid $accent;
        padding: 1 2;
        margin: 0 1;
        text-align: center;
    }
    .home-card:hover {
        border: solid $primary;
    }
    .home-card Button {
        width: 100%;
        margin-top: 1;
    }
    #tools-layout {
        height: 1fr;
    }
    #tools-tree-panel {
        width: 25;
        border: solid $border;
    }
    #tools-form-panel {
        width: 1fr;
        padding: 0 1;
    }
    #files-nav {
        height: auto;
        margin-bottom: 1;
    }
    #files-footer {
        height: auto;
        margin-top: 1;
    }
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
            with TabPane("Tools", id="tools"):
                yield ToolsPanel(id="tools-panel")
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
        ]:
            panel = self.query_one(panel_id)
            if hasattr(panel, "refresh_data"):
                panel.refresh_data()
