from textual import on
from textual.events import Message
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, Label, ProgressBar, Static

from max_cli.interface.tui.activity_log import ActivityLog


class HomePanel(Vertical):
    QUICK_ACTIONS = [
        {
            "category": "grab",
            "command": "download",
            "icon": "\u2b07",
            "label": "Download Media",
            "tab": "download",
        },
        {
            "category": "files",
            "command": "smart-sort",
            "icon": "\U0001f4c1",
            "label": "Smart Sort Files",
            "tab": "files",
        },
        {
            "category": "ai",
            "command": "ask",
            "icon": "\U0001f916",
            "label": "Ask AI",
            "tab": "chat",
        },
    ]

    CATEGORY_COLORS = {
        "grab": "green",
        "files": "yellow",
        "ai": "purple",
    }

    def compose(self):
        yield Static("[bold cyan]> Welcome to Max CLI[/bold cyan]", id="home-title")

        with Horizontal(id="home-status-bar"):
            with Vertical(classes="status-metric"):
                yield Static("[bold]CPU[/bold]", classes="metric-label")
                yield ProgressBar(total=100, show_eta=False, id="stat-cpu-bar")
                yield Static("", id="stat-cpu-text", classes="metric-value")
            with Vertical(classes="status-metric"):
                yield Static("[bold]Memory[/bold]", classes="metric-label")
                yield ProgressBar(total=100, show_eta=False, id="stat-mem-bar")
                yield Static("", id="stat-mem-text", classes="metric-value")
            with Vertical(classes="status-metric"):
                yield Static("[bold]Disk[/bold]", classes="metric-label")
                yield ProgressBar(total=100, show_eta=False, id="stat-disk-bar")
                yield Static("", id="stat-disk-text", classes="metric-value")

        with Horizontal(id="home-stats-row"):
            yield Vertical(
                Static("0", id="stat-commands", classes="stat-number"),
                Static("Commands", classes="stat-label"),
                classes="stat-card",
            )
            yield Vertical(
                Static("0", id="stat-downloads", classes="stat-number"),
                Static("Downloads", classes="stat-label"),
                classes="stat-card",
            )
            yield Vertical(
                Static("0", id="stat-queue", classes="stat-number"),
                Static("Queue", classes="stat-label"),
                classes="stat-card",
            )
            yield Vertical(
                Static("0 B", id="stat-cache", classes="stat-number"),
                Static("Cached", classes="stat-label"),
                classes="stat-card",
            )

        yield Label("Quick Actions", id="home-subtitle")

        with Horizontal(id="home-cards"):
            for action in self.QUICK_ACTIONS:
                btn_id = f"btn-{action['category']}-{action['command']}"
                color = self.CATEGORY_COLORS.get(action["category"], "accent")
                yield Vertical(
                    Static(f"[bold]{action['icon']}[/bold]"),
                    Static(action["label"], id=f"label-{btn_id}"),
                    Button("> Open", id=btn_id, variant="default"),
                    classes=f"home-card home-card-{color}",
                )

        yield Static("[bold]> Recent Activity[/bold]", id="home-activity-title")
        yield ScrollableContainer(
            Static("", id="home-activity-list"), id="home-activity-scroll"
        )

    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        self._update_system_bar()
        self._update_stats()
        self._load_recent_activity()

    def _update_system_bar(self) -> None:
        try:
            import psutil

            cpu = psutil.cpu_percent(interval=0)
            mem = psutil.virtual_memory()
        except Exception:
            return

        cpu_label = "green" if cpu < 60 else ("yellow" if cpu < 85 else "red")
        mem_pct = mem.percent
        mem_label = "green" if mem_pct < 60 else ("yellow" if mem_pct < 85 else "red")

        mem_total_gb = mem.total / (1024**3)
        mem_used_gb = mem.used / (1024**3)

        try:
            disk = psutil.disk_usage("/")
            disk_pct = disk.percent
            disk_label = (
                "green" if disk_pct < 60 else ("yellow" if disk_pct < 85 else "red")
            )
            disk_total_gb = disk.total / (1024**3)
            disk_used_gb = disk.used / (1024**3)
        except Exception:
            disk_pct = 0
            disk_label = "green"
            disk_total_gb = 0
            disk_used_gb = 0

        self.query_one("#stat-cpu-bar", ProgressBar).update(progress=cpu)
        self.query_one("#stat-cpu-text", Static).update(
            f"[{cpu_label}]{cpu:.0f}%[/{cpu_label}]"
        )
        self.query_one("#stat-mem-bar", ProgressBar).update(progress=mem_pct)
        self.query_one("#stat-mem-text", Static).update(
            f"[{mem_label}]{mem_pct:.0f}% ({mem_used_gb:.1f}/{mem_total_gb:.1f} GB)[/{mem_label}]"
        )
        self.query_one("#stat-disk-bar", ProgressBar).update(progress=disk_pct)
        self.query_one("#stat-disk-text", Static).update(
            f"[{disk_label}]{disk_pct:.0f}% ({disk_used_gb:.1f}/{disk_total_gb:.1f} GB)[/{disk_label}]"
        )

    def _update_stats(self) -> None:
        from max_cli.core.engines.daemon_manager import DaemonManager

        daemon = DaemonManager()
        q_stats = daemon.get_stats()

        activity = ActivityLog()
        a_stats = activity.get_stats()

        total_commands = a_stats.get("success", 0) + a_stats.get("failed", 0)
        downloads = a_stats.get("download", 0)  # type: ignore[arg-type]
        queue_depth = q_stats.get("pending", 0) + q_stats.get("running", 0)

        self.query_one("#stat-commands", Static).update(str(total_commands))
        self.query_one("#stat-downloads", Static).update(str(downloads))

        self.query_one("#stat-queue", Static).update(str(queue_depth))
        if queue_depth > 0:
            self.query_one("#stat-queue", Static).update(
                f"[yellow]{queue_depth}[/yellow]"
            )

        try:
            from max_cli.common.cache import get_default_cache
            from max_cli.common.utils import format_size

            cache = get_default_cache()
            cache_size = cache.get_size()
            self.query_one("#stat-cache", Static).update(format_size(cache_size))
        except Exception:
            pass

    def _load_recent_activity(self) -> None:
        activity = ActivityLog()
        entries = activity.get_entries(limit=10)

        lines = []
        for entry in entries:
            icon = "\u2713" if entry.status == "success" else "\u2717"
            color = "green" if entry.status == "success" else "red"
            action = entry.action.replace("_", " ").title()
            ts = (entry.timestamp or "")[11:19] if entry.timestamp else ""
            details = str(
                entry.details.get(
                    "url", entry.details.get("target", entry.details.get("params", ""))
                )
            )
            if len(details) > 45:
                details = details[:42] + "..."
            lines.append(
                f"[dim]{ts}[/dim] [{color}]{icon}[/{color}] {action}: {details}"
            )

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
