from textual import on
from textual.events import Message
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, Label, Static

from max_cli.interface.tui.activity_log import ActivityLog


class HomePanel(Vertical):
    QUICK_ACTIONS = [
        {
            "category": "grab",
            "command": "download",
            "icon": "\u2b07",
            "label": "Download Media",
        },
        {
            "category": "video",
            "command": "compress",
            "icon": "\U0001f4e6",
            "label": "Compress Video",
        },
        {
            "category": "video",
            "command": "to-audio",
            "icon": "\U0001f3b5",
            "label": "Extract Audio",
        },
        {
            "category": "images",
            "command": "compress",
            "icon": "\U0001f5bc",
            "label": "Compress Images",
        },
        {
            "category": "files",
            "command": "smart-sort",
            "icon": "\U0001f4c1",
            "label": "Smart Sort Files",
        },
        {
            "category": "pdf",
            "command": "merge",
            "icon": "\U0001f4c4",
            "label": "Merge PDFs",
        },
        {
            "category": "audio",
            "command": "set",
            "icon": "\U0001f3f7",
            "label": "Set Audio Metadata",
        },
        {"category": "ai", "command": "ask", "icon": "\U0001f916", "label": "Ask AI"},
    ]

    def compose(self):
        yield Static("[bold cyan]Welcome to Max CLI[/bold cyan]", id="home-title")
        yield Label(
            "[dim]Quick Actions \u2014 click to launch[/dim]", id="home-subtitle"
        )

        with Horizontal(id="home-cards"):
            for action in self.QUICK_ACTIONS:
                btn_id = f"btn-{action['category']}-{action['command']}"
                yield Vertical(
                    Static(f"[bold]{action['icon']}[/bold]"),
                    Static(action["label"], id=f"label-{btn_id}"),
                    Button("Launch", id=btn_id, variant="default"),
                    classes="home-card",
                )

        yield Static("", id="home-stats")

        yield Static("[bold]Recent Activity[/bold]", id="home-activity-title")
        yield ScrollableContainer(
            Static("", id="home-activity-list"), id="home-activity-scroll"
        )

    def on_mount(self) -> None:
        self._update_stats()
        self._load_recent_activity()

    def _update_stats(self) -> None:
        from datetime import datetime

        from max_cli.core.engines.daemon_manager import DaemonManager
        from max_cli.interface.tui.activity_log import ActivityLog

        daemon = DaemonManager()
        stats = daemon.get_stats()

        activity = ActivityLog()
        today = datetime.now().strftime("%Y-%m-%d")
        today_entries = [
            e
            for e in activity.get_entries(limit=1000)
            if e.timestamp and e.timestamp.startswith(today) and e.category == "grab"
        ]

        stats_widget = self.query_one("#home-stats", Static)
        stats_widget.update(
            f"  Queue: {stats.get('pending', 0)} pending  |  "
            f"Downloads today: {len(today_entries)}  |  "
            f"Failed: {stats.get('failed', 0)}"
        )

    def _load_recent_activity(self) -> None:
        activity = ActivityLog()
        entries = activity.get_entries(limit=10)

        lines = []
        for entry in entries:
            icon = "\u2713" if entry.status == "success" else "\u2717"
            color = "green" if entry.status == "success" else "red"
            action = entry.action.replace("_", " ").title()
            details = str(
                entry.details.get(
                    "url", entry.details.get("target", entry.details.get("params", ""))
                )
            )
            if len(details) > 40:
                details = details[:37] + "..."
            lines.append(f"[{color}]{icon}[/{color}] {action}: {details}")

        widget = self.query_one("#home-activity-list", Static)
        if lines:
            widget.update("\n".join(lines))
        else:
            widget.update("[dim]No recent activity[/dim]")

    class CommandSelected(Message):
        def __init__(self, category: str, command: str) -> None:
            super().__init__()
            self.category = category
            self.command = command

    @on(Button.Pressed)
    def _on_card_click(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id and btn_id.startswith("btn-"):
            parts = btn_id.split("-", 2)
            if len(parts) == 3:
                category, command = parts[1], parts[2]
                self.post_message(
                    HomePanel.CommandSelected(category=category, command=command)
                )
