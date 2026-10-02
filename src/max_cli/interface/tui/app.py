from datetime import datetime

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widget import Widget
from textual.widgets import Footer

from max_cli.interface.tui.commands import GROUP_PAGES, ActionCommands
from max_cli.interface.tui.messages import OpenFile, OpenPage
from max_cli.interface.tui.theme import MAX_CYBER, THEME_NAME
from max_cli.interface.tui.tool_pages import TOOL_PAGES
from max_cli.interface.tui.ui_prefs import load_prefs, save_pref
from max_cli.interface.tui.widgets.activity_panel import ActivityPanel
from max_cli.interface.tui.widgets.ai_panel import AIPanel
from max_cli.interface.tui.widgets.download_panel import DownloadPanel
from max_cli.interface.tui.widgets.extras_panel import ExtrasPanel
from max_cli.interface.tui.widgets.home_panel import HomePanel
from max_cli.interface.tui.widgets.jobs_drawer import JobsDrawer
from max_cli.interface.tui.widgets.settings_panel import SettingsPanel
from max_cli.interface.tui.widgets.sidebar import (
    SECTION_KEYS,
    SECTIONS,
    SETTINGS_KEY,
    SETTINGS_KEY_NAME,
    Badge,
    Sidebar,
)
from max_cli.interface.tui.widgets.tool_page import ToolPage

# Panels whose data changes on its own (queue, history, disk use ...).
REFRESHABLE_PANEL_IDS = (
    "#activity-panel",
    "#home-panel",
)
# Below this width the sidebar shows icons only.
AUTO_COMPACT_COLUMNS = 100
BACK_HISTORY_LIMIT = 20
BADGE_REFRESH_SECONDS = 2.0
REMOVED_SETTINGS_NOTICE_SECONDS = 12
PREF_LAST_PAGE = "last_page"
PREF_THEME = "theme"
# Pages that were merged away, and where a saved last page now goes.
RENAMED_PAGES = {
    "config": "settings",
    "system": "settings",
    "analytics": "home",
    # Every action has its group's page now (PLANS/active/dashboard-tool-pages.md).
    "tools": "home",
    # Queue and History became the Activity page's tabs.
    "queue": "activity",
    "history": "activity",
    # The AI page with the agent replaced Chat (2026-10-02).
    "chat": "ai",
}
# True when you left the sidebar showing names. A new name, not the earlier
# "sidebar_collapsed": that one was saved while icons were the default, and
# must not keep the sidebar folded now that it starts open (2026-10-02).
PREF_SIDEBAR_OPEN = "sidebar_open"
# Shown on the help screen after the page list.
GLOBAL_KEYS = [
    ("Esc", "Back to the sidebar"),
    ("Alt+Left", "Previous page"),
    ("J", "Show or hide running and queued jobs"),
    ("Ctrl+B", "Collapse or expand the sidebar"),
    ("Ctrl+P", "Find any action or page by name; themes"),
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

    COMMANDS = App.COMMANDS | {ActionCommands}

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("question_mark", "help", "Help"),
        ("ctrl+b", "toggle_sidebar", "Sidebar"),
        Binding("escape", "focus_sidebar", "Sidebar", show=False),
        Binding("alt+left", "previous_page", "Back", show=False),
        ("j", "toggle_jobs", "Jobs"),
        # Number keys (and "," for Settings) jump to pages. Typing in an
        # input still types them: the focused input handles the key first.
        *(
            Binding(
                SETTINGS_KEY_NAME if key == SETTINGS_KEY else key,
                f"goto('{section_id}')",
                show=False,
            )
            for section_id, key in SECTION_KEYS.items()
        ),
    ]

    CSS = """
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

    /* Every page scrolls when it's taller than the terminal. Pages start
       hidden; navigate() shows one. Shown all at once for the first frame,
       a page that takes focus on show (Download) grabbed the keyboard. */
    #content > * {
        display: none;
        padding: 1 2;
        height: 1fr;
        overflow-y: auto;
        background: $panel;
    }

    /* The AI page scrolls its conversation itself, so the input under it
       stays in view. */
    #content > #ai-panel {
        overflow-y: hidden;
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
    /* The Download page pages its history instead of scrolling it; the rule
       above would make it a tall inner scroll area. */
    #download-history-table, #history-table, #undo-table {
        height: auto;
        min-height: 0;
        border: none;
    }

    Button {
        min-width: 12;
    }
    /* The sidebar's expand button is one character; the app CSS wins over
       the sidebar's own styles, so the exception lives here. */
    Sidebar #sidebar-toggle {
        min-width: 5;
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
                for spec in TOOL_PAGES:
                    yield ToolPage(spec, id=f"{spec.page_id}-panel")
                yield ActivityPanel(id="activity-panel")
                yield ExtrasPanel(id="extras-panel")
                yield SettingsPanel(id="settings-panel")
                yield AIPanel(id="ai-panel")
        yield JobsDrawer(id="jobs")
        yield Footer()

    def __init__(self) -> None:
        super().__init__()
        self.register_theme(MAX_CYBER)
        saved = load_prefs().get(PREF_THEME)
        self.theme = saved if saved in self.available_themes else THEME_NAME

    def on_mount(self) -> None:
        prefs = load_prefs()
        # Ctrl+P can switch themes; remember the choice.
        self.theme_changed_signal.subscribe(
            self, lambda theme: save_pref(PREF_THEME, theme.name)
        )
        self._back: list[str] = []
        self._current = ""
        # The sidebar starts open, then stays as you last left it.
        self._user_compact = not prefs.get(PREF_SIDEBAR_OPEN, True)
        # Failures that happen from now on get a badge on History.
        self._history_seen = datetime.now().isoformat()
        self._apply_compact()
        start_page = str(prefs.get(PREF_LAST_PAGE) or "home")
        start_page = RENAMED_PAGES.get(start_page, start_page)
        known = {section_id for section_id, _icon, _label in SECTIONS}
        self.navigate(start_page if start_page in known else "home", remember=False)
        self.query_one(Sidebar).focus_nav()
        self._point_out_removed_settings()
        self.set_interval(2.0, self._refresh_active_panel)
        self.set_interval(BADGE_REFRESH_SECONDS, self._refresh_badges)
        # Run queued work while the dashboard is open: "Queue for later" and
        # tasks left from earlier runs. Nothing started this before, so
        # queued downloads stayed pending.
        from max_cli.core.engines.task_manager import get_task_manager

        self._task_manager = get_task_manager()
        self._task_manager.start_worker()

    def _point_out_removed_settings(self) -> None:
        from max_cli.common.settings_file import removed_settings_in_file

        removed = removed_settings_in_file()
        if removed:
            self.notify(
                f"~/.max_config.env sets {', '.join(removed)}, which Max no longer "
                f"uses. Settings ({SETTINGS_KEY}) > Maintenance removes them.",
                severity="warning",
                timeout=REMOVED_SETTINGS_NOTICE_SECONDS,
            )

    def on_unmount(self) -> None:
        if hasattr(self, "_task_manager"):
            self._task_manager.stop_worker(wait=False)

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
        if section_id == "activity":
            self._history_seen = datetime.now().isoformat()

    def action_goto(self, section_id: str) -> None:
        self.navigate(section_id)

    def open_action(self, action_id: str) -> None:
        """Show an action on its page, its form ready to fill (Ctrl+P)."""
        group, _, name = action_id.partition(".")
        page_id = GROUP_PAGES[group]
        self.navigate(page_id)
        page = self.query_one(f"#{page_id}-panel")
        if isinstance(page, ToolPage):
            page.show_action(name, focus=True)
        elif isinstance(page, ExtrasPanel):
            page.show_action(name)

    def action_previous_page(self) -> None:
        if self._back:
            self.navigate(self._back.pop(), remember=False)

    def action_focus_sidebar(self) -> None:
        self.query_one(Sidebar).focus_nav()

    def action_toggle_jobs(self) -> None:
        self.query_one(JobsDrawer).toggle()

    def on_jobs_drawer_show(self, message: JobsDrawer.Show) -> None:
        self.query_one(JobsDrawer).show_jobs()

    def action_help(self) -> None:
        from max_cli.interface.tui.widgets.dialogs import HelpScreen

        rows: list[tuple[str, str]] = [("", "Pages")]
        rows += [(SECTION_KEYS[sid], label) for sid, _icon, label in SECTIONS]
        rows += [("", "Everywhere"), *GLOBAL_KEYS]
        self.push_screen(HelpScreen(rows))

    def _narrow(self) -> bool:
        return self.size.width < AUTO_COMPACT_COLUMNS

    def _apply_compact(self) -> None:
        sidebar = self.query_one(Sidebar)
        if self._narrow():
            sidebar.set_compact(True, can_expand=False)
        else:
            sidebar.set_compact(self._user_compact)

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
        # One badge for Activity: new failures matter more than a queue.
        failures = 0 if self._current == "activity" else self._new_failures()
        if failures:
            sidebar.set_badge("activity", Badge("failed", failures))
        else:
            sidebar.set_badge("activity", Badge("waiting", self._waiting_tasks()))

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
        if self._narrow():
            return  # names don't fit; the button says so
        self._user_compact = not self._user_compact
        save_pref(PREF_SIDEBAR_OPEN, not self._user_compact)
        self._apply_compact()

    def on_sidebar_toggle_requested(self, message: Sidebar.ToggleRequested) -> None:
        self.action_toggle_sidebar()

    def action_refresh(self) -> None:
        for panel in self._refreshable_panels():
            if hasattr(panel, "refresh_data"):
                panel.refresh_data()

    def on_sidebar_section_selected(self, message: Sidebar.SectionSelected) -> None:
        self.navigate(message.section_id)

    def on_open_file(self, message: OpenFile) -> None:
        """A page hands a file to the page made for its kind."""
        page = self.query_one(f"#{message.page_id}-panel", ToolPage)
        self.navigate(message.page_id)
        page.open_file(message.path)

    def on_open_page(self, message: OpenPage) -> None:
        self.navigate(message.section_id)
        if message.tab and message.section_id == "activity":
            self.query_one(ActivityPanel).show_tab(message.tab)
