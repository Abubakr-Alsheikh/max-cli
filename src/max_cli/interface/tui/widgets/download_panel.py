"""Interactive download panel for the TUI dashboard."""

from datetime import datetime
from pathlib import Path
from typing import Any

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Input,
    Label,
    ProgressBar,
    RadioButton,
    RadioSet,
    Select,
    Static,
)
from textual.worker import Worker, WorkerState

from max_cli.config import settings
from max_cli.core.engines.download_history import DownloadHistory

_BITRATE_OPTIONS = {
    "64k": "ss",
    "128k": "s",
    "192k": "m",
    "320k": "x",
}
_BITRATE_LABELS = list(_BITRATE_OPTIONS.keys())


class DownloadPanel(Vertical):
    """Download media panel with form, progress, and history."""

    _progress_active: reactive[bool] = reactive(False)

    DEFAULT_CSS = """
    DownloadPanel {
        height: 1fr;
        overflow-y: auto;
        padding: 0 1;
    }

    #download-url {
        width: 1fr;
        margin: 1 0;
    }

    #download-type {
        margin: 0 0 1 0;
    }

    #download-quality-section,
    #download-bitrate-section {
        height: auto;
        margin: 0 0 1 0;
    }
    #download-quality-section > Label,
    #download-bitrate-section > Label {
        width: 10;
        margin-right: 1;
    }
    #download-quality-section > Select {
        width: 16;
        margin-right: 2;
    }
    #download-quality-section > Input {
        width: 10;
    }

    #download-options {
        height: auto;
        margin: 0 0 1 0;
    }
    #download-options Checkbox {
        margin-right: 2;
    }

    #output-row {
        height: auto;
        margin: 0 0 1 0;
    }
    #output-row Input {
        width: 1fr;
    }

    #download-actions {
        height: auto;
        margin: 1 0;
    }
    #btn-download {
        width: 1fr;
    }
    #btn-queue {
        width: 1fr;
    }

    #download-progress-section {
        height: auto;
        border: solid $accent;
        background: $surface;
        padding: 1;
        margin: 1 0;
    }
    #download-progress-filename {
        text-style: bold;
        margin: 1 0;
    }
    #download-progress-info {
        height: auto;
    }

    #download-status {
        height: auto;
        margin: 1 0;
    }

    #download-history-title {
        margin: 1 0 0 0;
        border-bottom: solid $accent;
    }
    #download-history-table {
        height: auto;
        min-height: 5;
    }

    #download-duplicate-warning {
        height: auto;
        margin: 0 0 1 0;
    }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._current_url: str = ""
        self._cancel_requested: bool = False

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static("[bold]Download Media[/bold]", id="download-title")

        yield Input(
            placeholder="https://youtube.com/watch?v=...",
            id="download-url",
        )
        yield Static("", id="download-duplicate-warning")

        yield Label("Type:")
        with RadioSet(id="download-type"):
            is_audio_default = settings.GRAB_DEFAULT_TYPE == "audio"
            yield RadioButton("Video", id="type-video", value=not is_audio_default)
            yield RadioButton("Audio Only", id="type-audio", value=is_audio_default)

        with Horizontal(id="download-quality-section"):
            yield Label("Quality:")
            quality_map: dict[str, str] = {
                "ss": "ss",
                "s": "s",
                "m": "m",
                "h": "h",
                "x": "x",
            }
            default_quality = quality_map.get(settings.GRAB_QUALITY.lower()[0], "h")
            yield Select(
                [
                    ("360p", "ss"),
                    ("480p", "s"),
                    ("720p", "m"),
                    ("1080p", "h"),
                    ("4K", "x"),
                ],
                value=default_quality,
                id="download-quality",
                allow_blank=False,
            )
            yield Label("Res:")
            yield Input(
                placeholder="px",
                id="download-resolution",
                type="integer",
            )

        with Horizontal(id="download-bitrate-section"):
            yield Label("Bitrate:")
            default_bitrate = (
                settings.GRAB_QUALITY.lower()[0]
                if settings.GRAB_QUALITY.lower()[0] in ("ss", "s", "m", "h", "x")
                else "m"
            )
            bitrate_labels = {"ss": "64k", "s": "128k", "m": "192k", "x": "320k"}
            yield Select(
                [(b, b) for b in _BITRATE_LABELS],
                value=bitrate_labels.get(default_bitrate, "192k"),
                id="download-bitrate",
                allow_blank=False,
            )

        with Horizontal(id="download-options"):
            yield Checkbox("Subtitles", id="download-subtitles")
            yield Checkbox(
                "Metadata",
                id="download-metadata",
                value=settings.GRAB_INCLUDE_METADATA,
            )
            yield Checkbox("No Playlist", id="download-no-playlist")

        with Horizontal(id="output-row"):
            yield Input(
                value=str(settings.GRAB_DEFAULT_PATH),
                id="download-output",
            )
            yield Button("Browse", id="btn-browse-output", variant="default")

        with Horizontal(id="download-actions"):
            yield Button("Download Now", id="btn-download", variant="primary")
            yield Button("Queue", id="btn-queue", variant="default")

        with Vertical(id="download-progress-section"):
            yield ProgressBar(id="download-progress-bar", total=100)
            yield Static("", id="download-progress-filename")
            with Horizontal(id="download-progress-info"):
                yield Static("", id="download-progress-speed")
                yield Button("Cancel", id="btn-cancel-download", variant="error")

        yield Static("Status: Ready", id="download-status")
        yield Static("[bold]History[/bold]", id="download-history-title")
        yield DataTable(id="download-history-table", cursor_type="row")
        with Horizontal(id="download-history-actions"):
            yield Button("Clear History", id="btn-clear-history", variant="default")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        self._apply_last_settings()
        self._sync_visibility()
        self._load_history()

    def _sync_visibility(self) -> None:
        is_audio = self.query_one("#type-audio", RadioButton).value
        self.query_one("#download-quality-section").display = not is_audio
        self.query_one("#download-bitrate-section").display = is_audio

    @on(RadioSet.Changed, "#download-type")
    def _on_type_changed(self, event: RadioSet.Changed) -> None:
        is_audio = event.pressed.id == "type-audio"
        self.query_one("#download-quality-section").display = not is_audio
        self.query_one("#download-bitrate-section").display = is_audio

    def _apply_last_settings(self) -> None:
        history = DownloadHistory()
        last = history.get_last_settings()
        if not last:
            return

        audio_only = last.get("audio_only", False)
        quality = last.get("quality", "")
        subtitles = last.get("subtitles", False)
        include_metadata = last.get("include_metadata", settings.GRAB_INCLUDE_METADATA)
        no_playlist = last.get("no_playlist", False)
        last_bitrate = last.get("bitrate", "")

        if audio_only:
            self.query_one("#type-audio", RadioButton).value = True
            self.query_one("#type-video", RadioButton).value = False

        quality_map = {"ss": "ss", "s": "s", "m": "m", "h": "h", "x": "x"}
        if quality in quality_map:
            self.query_one("#download-quality", Select).value = quality

        if last_bitrate in _BITRATE_OPTIONS:
            self.query_one("#download-bitrate", Select).value = last_bitrate

        self.query_one("#download-subtitles", Checkbox).value = subtitles
        self.query_one("#download-metadata", Checkbox).value = include_metadata
        self.query_one("#download-no-playlist", Checkbox).value = no_playlist

    # ------------------------------------------------------------------
    # URL Input — duplicate detection
    # ------------------------------------------------------------------

    @on(Input.Changed, "#download-url")
    def _on_url_changed(self, event: Input.Changed) -> None:
        url = event.value.strip()
        warning = self.query_one("#download-duplicate-warning", Static)
        if not url:
            warning.update("")
            return

        history = DownloadHistory()
        existing = history.is_already_downloaded(url)
        if existing:
            title = existing.get("title", url)
            warning.update(f"[yellow]\u26a0 Previously downloaded: {title}[/yellow]")
            last_output = history.get_last_output_path(url)
            if last_output:
                self.query_one("#download-output", Input).value = last_output
        else:
            warning.update("")

    # ------------------------------------------------------------------
    # Button Handlers
    # ------------------------------------------------------------------

    @on(Button.Pressed, "#btn-download")
    def _on_download(self) -> None:
        self._start_download(queue=False)

    @on(Button.Pressed, "#btn-queue")
    def _on_queue(self) -> None:
        self._start_download(queue=True)

    @on(Button.Pressed, "#btn-browse-output")
    def _on_browse_output(self) -> None:
        self.notify("Type or paste the output directory path", severity="information")

    @on(Button.Pressed, "#btn-cancel-download")
    def _on_cancel_download(self) -> None:
        self._cancel_requested = True
        self._set_status("Cancelling...", "warning")

    @on(Button.Pressed, "#btn-clear-history")
    def _on_clear_history(self) -> None:
        history = DownloadHistory()
        count = history.clear_history()
        self._load_history()
        self._set_status(f"Cleared {count} history entries", "info")

    # ------------------------------------------------------------------
    # Download Execution
    # ------------------------------------------------------------------

    def _start_download(self, queue: bool) -> None:
        url = self.query_one("#download-url", Input).value.strip()
        if not url:
            self._set_status("Please enter a URL", "error")
            return

        values = self._collect_form_values()
        self._current_url = url
        self._cancel_requested = False

        self._progress_active = True
        self.query_one("#download-progress-bar", ProgressBar).progress = 0
        self.query_one("#download-progress-filename", Static).update("")
        self.query_one("#download-progress-speed", Static).update("")

        self.query_one("#btn-download", Button).disabled = True
        self.query_one("#btn-queue", Button).disabled = True

        from max_cli.common.events import get_emitter

        get_emitter().subscribe(self._on_download_event)

        self.app.run_worker(
            lambda: self._download_worker(values=values, queue=queue),
            name="_download_worker",
            thread=True,
        )

    def _download_worker(self, values: dict[str, Any], queue: bool) -> dict[str, Any]:
        from max_cli.interface.tui.command_executor import CommandExecutor

        executor = CommandExecutor()
        result = executor.execute(
            category="grab",
            command="download",
            values=values,
            queue=queue,
        )
        return {"result": result, "values": values, "queue": queue}

    # ------------------------------------------------------------------
    # Progress Events
    # ------------------------------------------------------------------

    def _on_download_event(self, event: Any) -> None:
        from max_cli.common.events import (
            DownloadCompleteEvent,
            DownloadProgressEvent,
        )

        if isinstance(event, DownloadProgressEvent) and event.url == self._current_url:
            self.app.call_from_thread(self._update_progress_ui, event)
        elif (
            isinstance(event, DownloadCompleteEvent) and event.url == self._current_url
        ):
            self.app.call_from_thread(
                self._set_status,
                f"Download complete: {event.filename}",
                "success",
            )

    def _update_progress_ui(self, event: Any) -> None:
        if self._cancel_requested:
            return

        self.query_one(
            "#download-progress-bar", ProgressBar
        ).progress = event.percentage
        self.query_one("#download-progress-filename", Static).update(
            f"Downloading: {event.filename or '...'}"
        )

        speed_str = (
            self._format_speed(event.speed)
            if hasattr(event, "speed") and event.speed
            else ""
        )
        eta_str = ""
        if hasattr(event, "eta") and event.eta:
            eta_str = f"ETA: {event.eta}s"
        parts = [p for p in [speed_str, eta_str] if p]
        self.query_one("#download-progress-speed", Static).update(
            " | ".join(parts) if parts else ""
        )
        self.query_one("#download-status", Static).update(
            f"[cyan]Status: Downloading... {event.percentage:.1f}%[/cyan]"
        )

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.name == "_download_worker":
            if event.state == WorkerState.SUCCESS:
                result = event.worker.result
                if isinstance(result, dict):
                    self._on_download_finished(result)
            elif event.state == WorkerState.ERROR:
                error = (
                    str(event.worker.error) if event.worker.error else "Unknown error"
                )
                self._on_download_error(error)

    def _on_download_finished(self, data: dict[str, Any]) -> None:
        from max_cli.common.events import get_emitter

        get_emitter().unsubscribe(self._on_download_event)

        result = data.get("result")
        values = data.get("values", {})

        history = DownloadHistory()
        output_files: list[str] = []
        if result and hasattr(result, "output_files"):
            output_files = result.output_files or []

        if result and hasattr(result, "success") and result.success:
            history.record_download(
                url=values.get("url", ""),
                title="",
                output_files=output_files,
                settings_used=values,
                file_size=0,
                status="completed",
            )
        else:
            history.record_download(
                url=values.get("url", ""),
                title="",
                output_files=[],
                settings_used=values,
                file_size=0,
                status="failed",
            )

        self._progress_active = False

        if result and result.success:
            self._set_status(f"Downloaded: {values.get('url', '')[:50]}", "success")
        else:
            err = (
                result.error if result and hasattr(result, "error") else "Unknown error"
            )
            self._set_status(f"Failed: {err}", "error")

        self._load_history()
        self.query_one("#btn-download", Button).disabled = False
        self.query_one("#btn-queue", Button).disabled = False

    def _on_download_error(self, error: str) -> None:
        from max_cli.common.events import get_emitter

        get_emitter().unsubscribe(self._on_download_event)
        self._progress_active = False
        self._set_status(f"Error: {error}", "error")
        self.query_one("#btn-download", Button).disabled = False
        self.query_one("#btn-queue", Button).disabled = False

    # ------------------------------------------------------------------
    # Reactive watcher
    # ------------------------------------------------------------------

    def watch__progress_active(self, active: bool) -> None:
        section = self.query_one("#download-progress-section", Vertical)
        section.display = active

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _load_history(self) -> None:
        history = DownloadHistory()
        entries = history.get_recent(limit=50)
        table = self.query_one("#download-history-table", DataTable)

        table.clear()
        table.add_column("Status", width=4)
        table.add_column("File", width=30)
        table.add_column("Size", width=10)
        table.add_column("Source", width=20)
        table.add_column("When", width=12)

        for entry in entries:
            status_icon = "\u2713" if entry.get("status") == "completed" else "\u2717"
            status_color = "green" if entry.get("status") == "completed" else "red"

            filename = ""
            output_files = entry.get("output_files", [])
            if output_files:
                filename = Path(output_files[0]).name

            size = self._format_size(entry.get("file_size", 0))
            domain = entry.get("domain", "")

            rel_time = self._format_relative_time(entry.get("timestamp", ""))

            table.add_row(
                f"[{status_color}]{status_icon}[/{status_color}]",
                filename,
                size,
                domain,
                rel_time,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_size(bytes_val: int) -> str:
        if not bytes_val:
            return "-"
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(bytes_val)
        unit = "B"
        for u in units:
            unit = u
            if size < 1024.0:
                break
            size /= 1024.0
        if unit == "B":
            return f"{int(size)} {unit}"
        return f"{size:.1f} {unit}"

    @staticmethod
    def _format_speed(speed: float) -> str:
        if speed <= 0:
            return ""
        return DownloadPanel._format_size(int(speed)) + "/s"

    @staticmethod
    def _format_relative_time(timestamp_raw: str) -> str:
        if not timestamp_raw:
            return ""
        try:
            dt = datetime.fromisoformat(timestamp_raw)
            delta = datetime.now() - dt
            seconds = delta.total_seconds()
            if seconds < 60:
                return "just now"
            if seconds < 3600:
                return f"{int(seconds // 60)}m ago"
            if seconds < 86400:
                return f"{int(seconds // 3600)}h ago"
            return f"{int(seconds // 86400)}d ago"
        except (ValueError, TypeError):
            return ""

    def _set_status(self, message: str, level: str = "info") -> None:
        status = self.query_one("#download-status", Static)
        colors = {
            "success": "green",
            "error": "red",
            "info": "cyan",
            "warning": "yellow",
        }
        color = colors.get(level, "white")
        status.update(f"[{color}]Status: {message}[/{color}]")

    def _collect_form_values(self) -> dict[str, Any]:
        url = self.query_one("#download-url", Input).value.strip()
        is_audio = self.query_one("#type-audio", RadioButton).value
        quality = self.query_one("#download-quality", Select).value
        bitrate_val = self.query_one("#download-bitrate", Select).value
        resolution = self.query_one("#download-resolution", Input).value.strip()
        subtitles = self.query_one("#download-subtitles", Checkbox).value
        metadata = self.query_one("#download-metadata", Checkbox).value
        no_playlist = self.query_one("#download-no-playlist", Checkbox).value
        output = self.query_one("#download-output", Input).value.strip()

        if is_audio:
            selected = str(bitrate_val) if bitrate_val != Select.BLANK else "192k"
            eff_quality = _BITRATE_OPTIONS.get(selected, "m")
        else:
            eff_quality = str(quality) if quality != Select.BLANK else "h"

        return {
            "url": url,
            "audio_only": is_audio,
            "quality": eff_quality,
            "bitrate": bitrate_val if is_audio else "",
            "resolution": int(resolution) if resolution else None,
            "subtitles": subtitles,
            "include_metadata": metadata,
            "no_playlist": no_playlist,
            "output_path": output,
        }
