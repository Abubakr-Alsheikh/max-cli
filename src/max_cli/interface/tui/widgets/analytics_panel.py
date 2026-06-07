import platform
import sys
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from max_cli.interface.tui.activity_log import ActivityLog


class AnalyticsPanel(Vertical):
    """Live analytics and system monitoring panel."""

    MAX_CLI_DIR = Path.home() / ".max_cli"

    CATEGORY_COLORS = {
        "download": "green",
        "task": "blue",
        "command": "yellow",
        "file_op": "magenta",
        "ai": "purple",
        "grab": "green",
    }

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold cyan]> Analytics Dashboard[/bold cyan]",
            id="analytics-title",
        )

        yield Static("[bold]System Resources[/bold]", id="analytics-sys-title")
        yield Static("", id="analytics-sys-info")

        with Horizontal(id="analytics-stats-row"):
            yield Vertical(
                Static(
                    "[bold]Activity Stats[/bold]",
                    classes="analytics-section-title",
                ),
                Static("", id="analytics-activity-stats"),
                classes="analytics-section",
            )
            yield Vertical(
                Static("[bold]Storage[/bold]", classes="analytics-section-title"),
                Static("", id="analytics-storage-stats"),
                classes="analytics-section",
            )

        yield Static("[bold]Activity by Category[/bold]", id="analytics-cat-title")
        yield Static("", id="analytics-category-bars")

    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        self._update_system_resources()
        self._update_activity_stats()
        self._update_storage_stats()
        self._update_category_bars()

    def _update_system_resources(self) -> None:
        try:
            import psutil

            cpu = psutil.cpu_percent(interval=0)
            cpu_count = psutil.cpu_count()
            mem = psutil.virtual_memory()
            disk_root = psutil.disk_usage("/")
        except Exception:
            self.query_one("#analytics-sys-info", Static).update(
                "  [yellow]psutil not available. Install with: pip install max-cli[tui][/yellow]"
            )
            return

        mem_total_gb = mem.total / (1024**3)
        mem_used_gb = mem.used / (1024**3)
        mem_pct = mem.percent

        disk_total_gb = disk_root.total / (1024**3)
        disk_used_gb = disk_root.used / (1024**3)
        disk_pct = disk_root.percent

        from max_cli.common.utils import format_size

        max_cli_size = 0
        if self.MAX_CLI_DIR.exists():
            max_cli_size = sum(
                p.stat().st_size for p in self.MAX_CLI_DIR.rglob("*") if p.is_file()
            )

        try:
            from importlib.metadata import version

            max_version = version("max-cli")
        except Exception:
            max_version = "unknown"

        python_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        plat = f"{platform.system()} {platform.release()} ({platform.machine()})"

        cpu_color = "green" if cpu < 60 else ("yellow" if cpu < 85 else "red")
        mem_color = "green" if mem_pct < 60 else ("yellow" if mem_pct < 85 else "red")
        disk_color = (
            "green" if disk_pct < 60 else ("yellow" if disk_pct < 85 else "red")
        )

        self.query_one("#analytics-sys-info", Static).update(
            f"  CPU:   [{cpu_color}]{'█' * int(cpu / 5)}{'░' * (20 - int(cpu / 5))} {cpu:.0f}%[/{cpu_color}]  ({cpu_count} cores)\n"
            f"  Mem:   [{mem_color}]{'█' * int(mem_pct / 5)}{'░' * (20 - int(mem_pct / 5))} {mem_pct:.0f}%[/{mem_color}]  ({format_size(mem_used_gb * 1024**3)} / {format_size(mem_total_gb * 1024**3)})\n"
            f"  Disk:  [{disk_color}]{'█' * int(disk_pct / 5)}{'░' * (20 - int(disk_pct / 5))} {disk_pct:.0f}%[/{disk_color}]  ({format_size(disk_used_gb * 1024**3)} / {format_size(disk_total_gb * 1024**3)})\n"
            f"  Python: {python_ver}  |  Max CLI: {max_version}  |  {plat}\n"
            f"  Max Dir: {self.MAX_CLI_DIR}  ({format_size(max_cli_size)})"
        )

    def _update_activity_stats(self) -> None:
        activity = ActivityLog()
        stats = activity.get_stats()

        total = stats.get("total", 0)
        success = stats.get("success", 0)
        failed = stats.get("failed", 0)
        rate = (success / total * 100) if total > 0 else 0

        self.query_one("#analytics-activity-stats", Static).update(
            f"  Total:    {total}\n"
            f"  Success:  [green]{success}[/green]\n"
            f"  Failed:   [red]{failed}[/red]\n"
            f"  Rate:     {rate:.0f}%"
        )

    def _update_storage_stats(self) -> None:
        from max_cli.common.cache import get_default_cache
        from max_cli.common.utils import format_size
        from max_cli.core.engines.file_organizer import FileOrganizer

        cache = get_default_cache()
        cache_size = cache.get_size()
        cache_count = cache.count()

        organizer = FileOrganizer()
        backup_dir = organizer.get_backup_dir()
        backup_count = len(list(backup_dir.glob("*"))) if backup_dir.exists() else 0
        backup_size = (
            sum(p.stat().st_size for p in backup_dir.rglob("*") if p.is_file())
            if backup_dir.exists()
            else 0
        )

        txn_dir = Path.home() / ".max_cli" / "transactions"
        txn_count = len(list(txn_dir.glob("*.json"))) if txn_dir.exists() else 0

        self.query_one("#analytics-storage-stats", Static).update(
            f"  Cache:   {format_size(cache_size)} ({cache_count} items)\n"
            f"  Backups: {format_size(backup_size)} ({backup_count} files)\n"
            f"  Logs:    {txn_count} transactions"
        )

    def _update_category_bars(self) -> None:
        activity = ActivityLog()
        entries = activity.get_entries(limit=1000)

        counts: dict[str, int] = {}
        for entry in entries:
            cat = entry.category or "other"
            counts[cat] = counts.get(cat, 0) + 1

        if not counts:
            self.query_one("#analytics-category-bars", Static).update(
                "  [dim]No activity recorded yet[/dim]"
            )
            return

        total = sum(counts.values())
        cat_order = sorted(counts.items(), key=lambda x: x[1], reverse=True)

        lines = []
        for cat, count in cat_order:
            pct = (count / total) * 100
            bar_len = int(pct / 5)
            color = self.CATEGORY_COLORS.get(cat, "accent")
            label = cat.replace("_", " ").title()
            lines.append(
                f"  {label:<12} [{color}]{'█' * bar_len}{'░' * (20 - bar_len)}[/{color}]  {pct:.0f}%  ({count})"
            )

        self.query_one("#analytics-category-bars", Static).update("\n".join(lines))
