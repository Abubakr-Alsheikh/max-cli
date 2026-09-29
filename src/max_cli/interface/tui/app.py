from datetime import datetime

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widget import Widget
from textual.widgets import Footer

from max_cli.interface.tui.ui_prefs import load_prefs, save_pref
from max_cli.interface.tui.widgets.analytics_panel import AnalyticsPanel
from max_cli.interface.tui.widgets.chat_panel import ChatPanel
from max_cli.interface.tui.widgets.config_panel import ConfigPanel
from max_cli.interface.tui.widgets.download_panel import DownloadPanel
from max_cli.interface.tui.widgets.files_panel import FilesPanel
from max_cli.interface.tui.widgets.history_panel import HistoryPanel
from max_cli.interface.tui.widgets.home_panel import HomePanel
from max_cli.interface.tui.widgets.queue_panel import QueuePanel
from max_cli.interface.tui.widgets.sidebar import (
    SECTION_KEYS,
    SECTIONS,
    Badge,
    Sidebar,
)
from max_cli.interface.tui.widgets.system_panel import SystemPanel
from max_cli.interface.tui.widgets.tools_panel import ToolsPanel

# Panels whose data changes on its own (queue, history, disk use ...).
REFRESHABLE_PANEL_IDS = (
    "#queue-panel",
    "#history-panel",
    "#system-panel",
    "#files-panel",
    "#home-panel",
    "#analytics-panel",
)
# Below this width the sidebar shows icons only.
AUTO_COMPACT_COLUMNS = 100
BACK_HISTORY_LIMIT = 20
BADGE_REFRESH_SECONDS = 2.0
PREF_LAST_PAGE = "last_page"
PREF_SIDEBAR_COMPACT = "sidebar_compact"
# Shown on the help screen after the page list.
GLOBAL_KEYS = [
    ("Esc", "Back to the sidebar"),
    ("Alt+Left", "Previous page"),
    ("Ctrl+B", "Collapse or expand the sidebar"),
    ("Ctrl+P", "Command palette: themes and more"),
    ("r", "Refresh this page"),
    ("?", "This help"),
    ("q", "Quit"),
]


def _app_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("max-cli")
    except PackageNotFoundError:
        return ""


class MaxDashboardApp(App):
    """Interactive dashboard for Max CLI."""

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("question_mark", "help", "Help"),
        ("ctrl+b", "toggle_sidebar", "Sidebar"),
        Binding("escape", "focus_sidebar", "Sidebar", show=False),
        Binding("alt+left", "previous_page", "Back", show=False),
        # Number keys jump to pages. Typing in an input still types digits:
        # the focused input handles the key first.
        *(
            Binding(key, f"goto('{section_id}')", show=False)
            for section_id, key in SECTION_KEYS.items()
        ),
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

    /* Screen paints the theme's near-black $background by default. Any spot
       not yet repainted during a scroll showed through as a black block. */
    Screen {
        background: $panel;
    }

    #main-horizontal {
        height: 1fr;
    }

    #content {
        width: 1fr;
        height: 1fr;
    }

    /* Every page scrolls when it's taller than the terminal. */
    #content > * {
        padding: 1 2;
        height: 1fr;
        overflow-y: auto;
        background: $panel;
    }

    Footer {
        dock: bottom;
        height: auto;
    }

    DataTable {
        height: 1fr;
        min-height: 8;
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
    /* Inner scroll areas keep a usable height; the page scrolls around them. */
    #config-scroll, #chat-scroll {
        min-height: 6;
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

    /* A fixed height: a 1fr scroll area inside a scrolling page gets squeezed
       and resized on every reflow, and fights the page for the mouse wheel. */
    #home-activity-scroll {
        height: 12;
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
            yield Sidebar(id="sidebar", version=_app_version())
            with Container(id="content"):
                yield HomePanel(id="home-panel")
                yield DownloadPanel(id="download-panel")
                yield QueuePanel(id="queue-panel")
                yield HistoryPanel(id="history-panel")
                yield FilesPanel(id="files-panel")
                yield ToolsPanel(id="tools-panel")
                yield AnalyticsPanel(id="analytics-panel")
                yield ConfigPanel(id="config-panel")
                yield SystemPanel(id="system-panel")
                yield ChatPanel(id="chat-panel")
        yield Footer()

    def on_mount(self) -> None:
        prefs = load_prefs()
        self._back: list[str] = []
        self._current = ""
        self._user_compact = bool(prefs.get(PREF_SIDEBAR_COMPACT, False))
        # Failures that happen from now on get a badge on History.
        self._history_seen = datetime.now().isoformat()
        self._apply_compact()
        start_page = prefs.get(PREF_LAST_PAGE)
        known = {section_id for section_id, _icon, _label in SECTIONS}
        self.navigate(start_page if start_page in known else "home", remember=False)
        self.query_one(Sidebar).focus_nav()
        self.set_interval(2.0, self._refresh_active_panel)
        self.set_interval(BADGE_REFRESH_SECONDS, self._refresh_badges)

    # --- navigation ----------------------------------------------------------

    def navigate(self, section_id: str, remember: bool = True) -> None:
        """Show a page, mark it in the sidebar and remember it for next time."""
        if section_id == self._current:
            return
        if remember and self._current:
            self._back.append(self._current)
            del self._back[:-BACK_HISTORY_LIMIT]
        self._current = section_id
        self.query_one(Sidebar).set_active(section_id)
        self._show_panel(section_id)
        save_pref(PREF_LAST_PAGE, section_id)
        if section_id == "history":
            self._history_seen = datetime.now().isoformat()
            self.query_one(Sidebar).set_badge("history", None)

    def action_goto(self, section_id: str) -> None:
        self.navigate(section_id)

    def action_previous_page(self) -> None:
        if self._back:
            self.navigate(self._back.pop(), remember=False)

    def action_focus_sidebar(self) -> None:
        self.query_one(Sidebar).focus_nav()

    def action_help(self) -> None:
        from max_cli.interface.tui.widgets.dialogs import HelpScreen

        rows: list[tuple[str, str]] = [("", "Pages")]
        rows += [(SECTION_KEYS[sid], label) for sid, _icon, label in SECTIONS]
        rows += [("", "Everywhere"), *GLOBAL_KEYS]
        self.push_screen(HelpScreen(rows))

    def _apply_compact(self) -> None:
        narrow = self.size.width < AUTO_COMPACT_COLUMNS
        self.query_one(Sidebar).set_compact(self._user_compact or narrow)

    def on_resize(self, event: events.Resize) -> None:
        if hasattr(self, "_user_compact"):
            self._apply_compact()

    # --- badges --------------------------------------------------------------

    def on_download_panel_running_changed(
        self, message: DownloadPanel.RunningChanged
    ) -> None:
        self.query_one(Sidebar).set_badge("download", Badge("running", message.running))

    def _refresh_badges(self) -> None:
        sidebars = self.query(Sidebar)
        if not sidebars:
            return  # shutting down
        sidebar = sidebars.first()
        sidebar.set_badge("queue", Badge("waiting", self._waiting_tasks()))
        if self._current != "history":
            sidebar.set_badge("history", Badge("failed", self._new_failures()))

    @staticmethod
    def _waiting_tasks() -> int:
        from max_cli.core.engines.task_manager import get_task_manager

        manager = get_task_manager()
        manager.refresh()
        stats = manager.get_stats()
        return int(stats.get("pending", 0)) + int(stats.get("running", 0))

    def _new_failures(self) -> int:
        from max_cli.interface.tui.activity_log import ActivityLog

        failed = ActivityLog().get_entries(
            status_filter="failed", date_from=self._history_seen
        )
        return len(failed)

    def _show_panel(self, section_id: str) -> None:
        for known_id, _icon, _label in SECTIONS:
            self.query_one(f"#{known_id}-panel").display = False
        target_id = f"{section_id}-panel"
        try:
            target = self.query_one(f"#{target_id}")
            target.display = True
        except Exception:
            self.query_one("#home-panel").display = True

    def _refreshable_panels(self) -> list[Widget]:
        """Panels with live data, in refresh order.

        Empty once the app starts shutting down and its widgets are gone; the
        2-second refresh timer can still fire then.
        """
        return [
            panel
            for panel_id in REFRESHABLE_PANEL_IDS
            for panel in self.query(panel_id)
        ]

    def _refresh_active_panel(self) -> None:
        for panel in self._refreshable_panels():
            if panel.display:
                if hasattr(panel, "refresh_data"):
                    panel.refresh_data()
                break

    def action_toggle_sidebar(self) -> None:
        self._user_compact = not self.query_one(Sidebar).compact
        save_pref(PREF_SIDEBAR_COMPACT, self._user_compact)
        self.query_one(Sidebar).set_compact(self._user_compact)

    def action_refresh(self) -> None:
        for panel in self._refreshable_panels():
            if hasattr(panel, "refresh_data"):
                panel.refresh_data()

    def on_sidebar_section_selected(self, message: Sidebar.SectionSelected) -> None:
        self.navigate(message.section_id)

    def on_files_panel_open_action(self, message: FilesPanel.OpenAction) -> None:
        """The Files page hands a selected file to a Tools form."""
        self.navigate("tools")
        self.query_one(ToolsPanel).open_action(message.action_id, **message.values)

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
            self.navigate(target)
