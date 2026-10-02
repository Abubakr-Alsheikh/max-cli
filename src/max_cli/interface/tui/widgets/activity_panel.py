"""The Activity page: what Max is doing and what it did, in three tabs.

- Queue: running, waiting and finished tasks (`queue_panel.QueuePanel`).
- History: every action the dashboard ran (`history_panel.HistoryPanel`).
- Undo: the file changes Max recorded, and Undo (`undo_panel.UndoPanel`).

It replaced the separate Queue and History pages (PLANS/active/
dashboard-tool-pages.md), which freed a number key. Other pages open a tab
with `messages.OpenPage("activity", tab="history")`.
"""

from typing import Any

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.content import Content
from textual.widgets import Static, TabbedContent, TabPane

from max_cli.interface.tui.widgets.history_panel import HistoryPanel
from max_cli.interface.tui.widgets.queue_panel import QueuePanel
from max_cli.interface.tui.widgets.undo_panel import UndoPanel

TAB_PREFIX = "activity-"
TABS = ("queue", "history", "undo")


class ActivityPanel(Vertical):
    """Queue, History and Undo as tabs of one page."""

    DEFAULT_CSS = """
    #activity-header {
        height: 3;
        margin-bottom: 1;
    }
    ActivityPanel TabPane {
        padding: 1 0 0 0;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(self._brand(), id="activity-header")
        with TabbedContent(initial=f"{TAB_PREFIX}queue", id="activity-tabs"):
            with TabPane("Queue", id=f"{TAB_PREFIX}queue"):
                yield QueuePanel(id="queue-panel", brand=False)
            with TabPane("History", id=f"{TAB_PREFIX}history"):
                yield HistoryPanel(id="history-panel")
            with TabPane("Undo", id=f"{TAB_PREFIX}undo"):
                yield UndoPanel(id="undo-panel")

    @staticmethod
    def _brand() -> Content:
        return Content.assemble(
            ("◢◤ ", "bold $secondary"),
            ("ACTIVITY", "bold $primary"),
            (" // WHAT MAX IS DOING AND DID\n", "bold"),
            (
                "Queue: running and waiting tasks  ·  History: every action  ·  "
                "Undo: put files back",
                "$text-muted",
            ),
        )

    @property
    def tab(self) -> str:
        """The open tab: "queue", "history" or "undo"."""
        active = self.query_one("#activity-tabs", TabbedContent).active
        return active.removeprefix(TAB_PREFIX)

    def show_tab(self, tab: str) -> None:
        if tab in TABS:
            self.query_one(
                "#activity-tabs", TabbedContent
            ).active = f"{TAB_PREFIX}{tab}"

    def refresh_data(self) -> None:
        """The app's 2-second refresh: only the open tab reads its data."""
        panel: Any = self.query_one(f"#{self.tab}-panel")
        panel.refresh_data()

    @on(TabbedContent.TabActivated, "#activity-tabs")
    def _on_tab(self, event: TabbedContent.TabActivated) -> None:
        event.stop()
        # The tab's content shows with old data until its first refresh.
        self.refresh_data()
