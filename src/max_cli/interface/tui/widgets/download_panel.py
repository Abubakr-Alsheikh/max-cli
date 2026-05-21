"""Interactive download panel for the TUI dashboard."""

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    RadioButton,
    RadioSet,
    Select,
    Static,
)


class DownloadPanel(Vertical):
    DEFAULT_CSS = """
    DownloadPanel {
        height: 1fr;
    }
    #download-form {
        padding: 0 1;
    }
    #download-type-row, #download-quality-row {
        margin: 1 0;
    }
    #download-options {
        margin: 1 0;
    }
    #output-row {
        margin: 1 0;
    }
    #download-actions {
        margin: 1 0;
    }
    #download-status {
        margin: 1 0;
        padding: 0 1;
    }
    #recent-title {
        margin: 1 0 0 0;
        padding: 0 1;
    }
    #recent-scroll {
        height: 8;
        border: solid $primary-darken-2;
        margin: 0 1;
    }
    #recent-list {
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("[bold cyan]Download Media[/bold cyan]", id="download-title")

        with Vertical(id="download-form"):
            yield Label("URL:", id="url-label")
            yield Input(
                placeholder="https://youtube.com/watch?v=...",
                id="download-url",
            )

            yield Label("Type:", id="type-label")
            with RadioSet(id="download-type"):
                yield RadioButton("Video", id="type-video", value=True)
                yield RadioButton("Audio Only", id="type-audio")

            yield Label("Quality:", id="quality-label")
            yield Select(
                [
                    ("360p", "ss"),
                    ("480p", "s"),
                    ("720p", "m"),
                    ("1080p", "h"),
                    ("4K", "x"),
                ],
                value="h",
                id="download-quality",
                allow_blank=False,
            )

            yield Label("Resolution (px, optional):", id="resolution-label")
            yield Input(
                placeholder="e.g. 1080",
                id="download-resolution",
                type="integer",
            )

            with Horizontal(id="download-options"):
                yield Checkbox("Subtitles", id="download-subtitles")
                yield Checkbox("Metadata", id="download-metadata", value=True)
                yield Checkbox("No Playlist", id="download-no-playlist")

            yield Label("Output:", id="output-label")
            with Horizontal(id="output-row"):
                yield Input(
                    value=str(Path.home() / "Max Downloads"),
                    id="download-output",
                )
                yield Button("Browse", id="btn-browse-output", variant="default")

            with Horizontal(id="download-actions"):
                yield Button("Download Now", id="btn-download", variant="success")
                yield Button("Add to Queue", id="btn-queue", variant="primary")

        yield Static("Status: Ready", id="download-status")

        yield Static("[bold]Recent Downloads[/bold]", id="recent-title")
        yield ScrollableContainer(
            Static("", id="recent-list"),
            id="recent-scroll",
        )

    def on_mount(self) -> None:
        self._load_recent_downloads()

    @on(Button.Pressed, "#btn-download")
    def _on_download(self) -> None:
        url = self.query_one("#download-url", Input).value.strip()
        if not url:
            self._set_status("Please enter a URL", "error")
            return

        self._set_status("Downloading...", "info")
        self._execute_download(queue=False)

    @on(Button.Pressed, "#btn-queue")
    def _on_queue(self) -> None:
        url = self.query_one("#download-url", Input).value.strip()
        if not url:
            self._set_status("Please enter a URL", "error")
            return

        self._set_status("Added to queue", "success")
        self._execute_download(queue=True)

    def _execute_download(self, queue: bool) -> None:
        from max_cli.interface.tui.command_executor import CommandExecutor

        executor = CommandExecutor()
        values = self._collect_form_values()

        try:
            result = executor.execute(
                category="grab",
                command="download",
                values=values,
                queue=queue,
            )

            if result.success:
                status_msg = "Queued" if queue else "Downloaded"
                self._set_status(
                    f"{status_msg}: {values.get('url', '')[:50]}", "success"
                )
                self._load_recent_downloads()
            else:
                self._set_status(f"Failed: {result.error}", "error")

        except Exception as e:
            self._set_status(f"Error: {e}", "error")

    def _collect_form_values(self) -> dict:
        url = self.query_one("#download-url", Input).value.strip()
        is_audio = self.query_one("#type-audio", RadioButton).value
        quality = self.query_one("#download-quality", Select).value
        resolution = self.query_one("#download-resolution", Input).value.strip()
        subtitles = self.query_one("#download-subtitles", Checkbox).value
        metadata = self.query_one("#download-metadata", Checkbox).value
        no_playlist = self.query_one("#download-no-playlist", Checkbox).value
        output = self.query_one("#download-output", Input).value.strip()

        return {
            "url": url,
            "audio_only": is_audio,
            "quality": quality if quality != Select.BLANK else "h",
            "resolution": int(resolution) if resolution else None,
            "subtitles": subtitles,
            "include_metadata": metadata,
            "no_playlist": no_playlist,
            "output_path": output,
        }

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

    def _load_recent_downloads(self) -> None:
        from max_cli.interface.tui.activity_log import ActivityLog

        activity = ActivityLog()
        entries = activity.get_entries(limit=10, category_filter="grab")

        lines = []
        for entry in entries:
            icon = "+" if entry.status == "success" else "x"
            color = "green" if entry.status == "success" else "red"
            url = entry.details.get("url", "")
            details = url[:40] if url else entry.action
            lines.append(f"[{color}]{icon}[/{color}] {details}")

        widget = self.query_one("#recent-list", Static)
        if lines:
            widget.update("\n".join(lines))
        else:
            widget.update("[dim]No recent downloads[/dim]")
