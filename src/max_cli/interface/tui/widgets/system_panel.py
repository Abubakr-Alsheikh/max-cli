import platform
import shutil
import sys
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, ProgressBar, Static

from max_cli.core.engines.daemon_manager import DaemonManager


class SystemPanel(Vertical):
    """System information and disk usage panel."""

    MAX_CLI_DIR = Path.home() / ".max_cli"

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold cyan]\U0001f5a5 System Information[/bold cyan]", id="system-title"
        )
        yield Static("", id="system-info")
        yield Static("[bold]Disk Usage[/bold]", id="disk-title")
        yield ProgressBar(total=100, show_eta=False, id="disk-progress")
        yield Static("", id="system-disk")
        yield Static("[bold]Storage Management[/bold]", id="storage-title")
        yield Static("", id="storage-details")
        with Horizontal(id="storage-actions"):
            yield Button("Clear Cache", id="btn-clear-cache", variant="default")
            yield Button("Cleanup Backups", id="btn-cleanup-backups", variant="default")
            yield Button("Clean Transactions", id="btn-clean-txn", variant="default")
        yield Static("[bold]Quick Actions[/bold]", id="quick-actions-title")
        with Horizontal(id="quick-actions"):
            yield Button("Clear Queues", id="btn-clear-queues", variant="error")
            yield Button("Reset Config", id="btn-reset-config", variant="error")
        with Horizontal(id="system-actions"):
            yield Button("\U0001f504 Refresh", id="btn-refresh", variant="primary")
        yield Static("[bold]Recent Activity[/bold]", id="system-log-title")
        yield ScrollableContainer(Static("", id="system-log"), id="log-scroll")

    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        self._update_system_info()
        self._update_disk_usage()
        self._update_storage_info()
        self._update_recent_log()

    def _update_system_info(self) -> None:
        info_widget = self.query_one("#system-info", Static)

        try:
            from importlib.metadata import version

            max_version = version("max-cli")
        except Exception:
            max_version = "unknown"

        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        platform_info = platform.system()
        platform_release = platform.release()
        arch = platform.machine()

        info_widget.update(
            f"  [bold]Max CLI:[/bold] {max_version}\n"
            f"  [bold]Python:[/bold] {python_version}\n"
            f"  [bold]Platform:[/bold] {platform_info} {platform_release} ({arch})\n"
            f"  [bold]Max Dir:[/bold] {self.MAX_CLI_DIR}"
        )

    def _update_disk_usage(self) -> None:
        disk_widget = self.query_one("#system-disk", Static)
        progress_bar = self.query_one("#disk-progress", ProgressBar)

        if self.MAX_CLI_DIR.exists():
            total_size = self._get_dir_size(self.MAX_CLI_DIR)
            usage = shutil.disk_usage(self.MAX_CLI_DIR)
            pct = (usage.used / usage.total) * 100 if usage.total > 0 else 0

            progress_bar.update(progress=pct)

            disk_widget.update(
                f"  Data Size:         {self._format_bytes(total_size)}\n"
                f"  Disk Usage:        {usage.used / (1024**3):.1f} GB / "
                f"{usage.total / (1024**3):.1f} GB ({pct:.0f}%)\n"
                f"  Free Space:        {usage.free / (1024**3):.1f} GB"
            )
        else:
            progress_bar.update(progress=0)
            disk_widget.update("  Max CLI directory not found.")

        daemon = DaemonManager()
        stats = daemon.get_stats()
        history = daemon.get_history(limit=1)
        last_task = history[0] if history else None

        summary_lines = [
            "",
            f"  Queue: {stats.get('total', 0)} tasks "
            f"({stats.get('running', 0)} running, {stats.get('pending', 0)} pending)",
        ]
        if last_task:
            status_color = "green" if last_task.status.value == "completed" else "red"
            summary_lines.append(
                f"  Last task: {last_task.title or last_task.type.value} "
                f"[{status_color}]{last_task.status.value}[/]"
            )

        current = disk_widget.content or ""
        disk_widget.update(str(current) + "\n".join(summary_lines))

    def _update_storage_info(self) -> None:
        widget = self.query_one("#storage-details", Static)

        from max_cli.common.cache import get_default_cache
        from max_cli.core.engines.file_organizer import FileOrganizer

        cache = get_default_cache()
        cache_size = cache.get_size()

        organizer = FileOrganizer()
        backup_dir = organizer.get_backup_dir()
        backup_count = len(list(backup_dir.glob("*"))) if backup_dir.exists() else 0
        backup_size = self._get_dir_size(backup_dir) if backup_dir.exists() else 0

        txn_dir = Path.home() / ".max_cli" / "transactions"
        txn_count = len(list(txn_dir.glob("*.json"))) if txn_dir.exists() else 0

        widget.update(
            f"  Cache: {self._format_bytes(cache_size)} ({cache.count()} items)\n"
            f"  Backups: {backup_count} files ({self._format_bytes(backup_size)})\n"
            f"  Transactions: {txn_count} groups"
        )

    def _update_recent_log(self) -> None:
        log_widget = self.query_one("#system-log", Static)
        log_file = DaemonManager.DAEMON_LOG_FILE

        if log_file.exists():
            lines = log_file.read_text(encoding="utf-8").strip().split("\n")
            last_50 = lines[-50:]
            colored_lines = []
            for line in last_50:
                lower = line.lower()
                if "error" in lower or "exception" in lower or "fail" in lower:
                    colored_lines.append(f"[red]{line}[/red]")
                elif "warn" in lower:
                    colored_lines.append(f"[yellow]{line}[/yellow]")
                elif "success" in lower or "complete" in lower:
                    colored_lines.append(f"[green]{line}[/green]")
                else:
                    colored_lines.append(line)
            log_widget.update("\n".join(colored_lines))
        else:
            log_widget.update("  No daemon log found.")

    @on(Button.Pressed, "#btn-clear-cache")
    def _on_clear_cache(self) -> None:
        from max_cli.common.cache import get_default_cache

        cache = get_default_cache()
        count = cache.clear()
        self._update_storage_info()
        self.notify(f"Cleared {count} cached items", severity="information")

    @on(Button.Pressed, "#btn-cleanup-backups")
    def _on_cleanup_backups(self) -> None:
        from max_cli.core.engines.file_organizer import FileOrganizer

        organizer = FileOrganizer()
        count = organizer.cleanup_old_backups(days=30)
        self._update_storage_info()
        self.notify(f"Removed {count} old backups", severity="information")

    @on(Button.Pressed, "#btn-clean-txn")
    def _on_clean_txn(self) -> None:
        from max_cli.common.transaction_log import TransactionLog

        count = TransactionLog.cleanup_all()
        self._update_storage_info()
        self.notify(f"Cleaned {count} old transactions", severity="information")

    @on(Button.Pressed, "#btn-clear-queues")
    def _on_clear_queues(self) -> None:
        daemon = DaemonManager()
        daemon.clear()
        self.notify("All queues cleared", severity="information")

    @on(Button.Pressed, "#btn-reset-config")
    def _on_reset_config(self) -> None:
        env_path = Path.home() / ".max_config.env"
        if env_path.exists():
            env_path.unlink()
        self.notify("Config reset to defaults", severity="warning")

    @on(Button.Pressed, "#btn-refresh")
    def _on_refresh(self) -> None:
        self.refresh_data()

    @staticmethod
    def _get_dir_size(path: Path) -> int:
        total = 0
        if path.is_dir():
            for p in path.rglob("*"):
                if p.is_file():
                    total += p.stat().st_size
        return total

    @staticmethod
    def _format_bytes(size: float) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
