"""Download page: paste a link, see what it is, pick a quality, download.

Simple mode shows only the link, a preview with quality choices and the
folder. Advanced mode adds every other `grab download` option, taken from the
command catalog. Each download gets its own row with progress and a real
Cancel. See PLANS/active/grab-page-redesign.md.
"""

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from rich.markup import escape
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    ProgressBar,
    RadioButton,
    RadioSet,
    Static,
)

from max_cli.common.utils import format_size
from max_cli.config import settings
from max_cli.core.catalog import get_action
from max_cli.core.engines.download_history import DownloadHistory
from max_cli.interface.tui.ui_prefs import load_prefs, save_pref
from max_cli.interface.tui.widgets.action_form import ActionForm

GRAB_ACTION_ID = "grab.download"
# Advanced mode shows these catalog options. The quality choices above them
# already cover quality, media type and (for odd heights) resolution.
ADVANCED_FIELDS = (
    "resolution",
    "playlist_items",
    "no_playlist",
    "subtitles",
    "include_metadata",
    "strip_playlist",
    "player_client",
)
PROGRESS_REFRESH_SECONDS = 0.25
SLOT_POLL_SECONDS = 0.2
MODE_PREF = "download_mode"
FOLDER_PREF = "download_folder"


@dataclass
class QualityChoice:
    label: str
    values: dict[str, Any]  # quality / resolution / media_type for grab.download


DEFAULT_CHOICES = [
    QualityChoice("Best", {"media_type": "video", "quality": "x"}),
    QualityChoice("1080p", {"media_type": "video", "quality": "h"}),
    QualityChoice("720p", {"media_type": "video", "quality": "m"}),
    QualityChoice("480p", {"media_type": "video", "quality": "s"}),
    QualityChoice("Audio (MP3)", {"media_type": "audio", "quality": "h"}),
]


def _with_size(label: str, size: Optional[int]) -> str:
    return f"{label} ~{format_size(size)}" if size else label


def choices_for(media: Any) -> list[QualityChoice]:
    """Quality choices for a probed video: its real heights, sizes, and audio."""
    choices = [QualityChoice("Best", {"media_type": "video", "quality": "x"})]
    for option in media.qualities:
        values: dict[str, Any] = {"media_type": "video"}
        if option.quality_code:
            values["quality"] = option.quality_code
        else:
            values["resolution"] = option.height
        choices.append(
            QualityChoice(_with_size(option.label, option.size_bytes), values)
        )
    choices.append(
        QualityChoice(
            _with_size("Audio (MP3)", media.audio_size_bytes),
            {"media_type": "audio", "quality": "h"},
        )
    )
    return choices


def _default_choice_index(choices: list[QualityChoice]) -> int:
    last = DownloadHistory().get_last_settings()
    wants_audio = last.get("audio_only", settings.GRAB_DEFAULT_TYPE == "audio")
    quality = last.get("quality") or settings.GRAB_QUALITY
    for index, choice in enumerate(choices):
        if wants_audio and choice.values.get("media_type") == "audio":
            return index
        if not wants_audio and choice.values.get("quality") == quality:
            return index
    return 0


def _duration(seconds: Optional[float]) -> str:
    if not seconds:
        return ""
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes}:{secs:02}"


@dataclass
class DownloadJob:
    job_id: int
    url: str
    values: dict[str, Any]
    title: str
    cancel: threading.Event = field(default_factory=threading.Event)
    output_folder: Optional[Path] = None


class DownloadRow(Vertical):
    """One download: title, progress bar, speed and time left, and its buttons."""

    DEFAULT_CSS = """
    DownloadRow {
        height: auto;
        border: round $border;
        padding: 0 1;
        margin-bottom: 1;
    }
    DownloadRow .row-head {
        height: auto;
    }
    DownloadRow .row-title {
        width: 1fr;
    }
    DownloadRow .row-info {
        color: $text-muted;
    }
    DownloadRow Button {
        min-width: 12;
    }
    """

    def __init__(self, job: DownloadJob) -> None:
        super().__init__(id=f"job-{job.job_id}")
        self.job = job

    def compose(self) -> ComposeResult:
        with Horizontal(classes="row-head"):
            yield Static(escape(self.job.title), classes="row-title")
            yield Button("Cancel", id=f"cancel-{self.job.job_id}", variant="error")
        yield ProgressBar(total=100, show_eta=False)
        yield Static("Waiting for a free slot...", classes="row-info")

    def _info(self, text: str) -> None:
        self.query_one(".row-info", Static).update(text)

    def set_title(self, title: str) -> None:
        self.job.title = title
        self.query_one(".row-title", Static).update(escape(title))

    def set_started(self) -> None:
        self._info("Starting...")

    def set_progress(self, percent: float, speed: float, eta: int) -> None:
        self.query_one(ProgressBar).progress = percent
        parts = [f"{percent:.0f}%"]
        if speed:
            parts.append(f"{format_size(speed)}/s")
        if eta:
            parts.append(f"{_duration(eta)} left")
        self._info("  ".join(parts))

    def _swap_button(
        self, label: str, button_id: str, variant: str = "default"
    ) -> None:
        head = self.query_one(".row-head", Horizontal)
        for button in head.query(Button):
            button.remove()
        head.mount(Button(label, id=button_id, variant=variant))  # type: ignore[arg-type]  # variant is one of Textual's literals

    def set_done(self, message: str, size_bytes: int) -> None:
        self.query_one(ProgressBar).progress = 100
        size = f"  {format_size(size_bytes)}" if size_bytes else ""
        self._info(f"[green]Done.[/green] {escape(message)}{size}")
        self._swap_button("Open folder", f"open-{self.job.job_id}", "success")

    def set_failed(self, error: str) -> None:
        self._info(f"[red]Failed:[/red] {escape(error)}")
        self._swap_button("Retry", f"retry-{self.job.job_id}", "warning")

    def set_cancelled(self) -> None:
        self._info("[yellow]Cancelled.[/yellow] Partial files were removed.")
        self._swap_button("Retry", f"retry-{self.job.job_id}", "warning")


class DownloadPanel(Vertical):
    """The Download page."""

    DEFAULT_CSS = """
    DownloadPanel {
        height: 1fr;
        overflow-y: auto;
        padding: 0 1;
    }
    #dl-header, #dl-link-row, #dl-folder-row, #dl-actions {
        height: auto;
    }
    #dl-title {
        width: 1fr;
    }
    #dl-mode {
        layout: horizontal;
        height: auto;
        width: auto;
    }
    #dl-url, #dl-output {
        width: 1fr;
    }
    #dl-preview {
        height: auto;
        border: round $accent;
        padding: 0 1;
        margin: 1 0;
    }
    #dl-preview-meta {
        color: $text-muted;
    }
    #dl-quality {
        layout: horizontal;
        height: auto;
        width: 100%;
    }
    #dl-folder-row Label {
        padding: 1 1 0 0;
    }
    #dl-advanced {
        height: auto;
        border: round $border;
        margin: 1 0;
    }
    #dl-status {
        margin: 1 0;
    }
    #dl-jobs {
        height: auto;
    }
    .section-title {
        margin-top: 1;
        text-style: bold;
    }
    #download-history-table {
        height: auto;
        max-height: 16;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._action = get_action(GRAB_ACTION_ID)
        self._choices: list[QualityChoice] = list(DEFAULT_CHOICES)
        self._jobs: dict[int, DownloadJob] = {}
        self._next_job_id = 1
        self._slots = threading.BoundedSemaphore(settings.GRAB_MAX_CONCURRENT)

    # --- layout ---------------------------------------------------------

    def compose(self) -> ComposeResult:
        prefs = load_prefs()
        advanced = prefs.get(MODE_PREF) == "advanced"
        with Horizontal(id="dl-header"):
            yield Static("[bold cyan]Download[/bold cyan]", id="dl-title")
            with RadioSet(id="dl-mode"):
                yield RadioButton("Simple", id="mode-simple", value=not advanced)
                yield RadioButton("Advanced", id="mode-advanced", value=advanced)
        with Horizontal(id="dl-link-row"):
            yield Input(
                placeholder="Paste a YouTube link (Ctrl+V), then press Enter",
                id="dl-url",
            )
            yield Button("Check", id="btn-check")
        yield Static("", id="dl-duplicate")
        with Vertical(id="dl-preview"):
            yield Static(
                "[dim]Paste a link and press Check to see what it is.[/dim]",
                id="dl-preview-title",
            )
            yield Static("", id="dl-preview-meta")
            yield Label("Quality")
            yield self._quality_set(self._choices)
        with Horizontal(id="dl-folder-row"):
            yield Label("Save to")
            yield Input(
                value=prefs.get(FOLDER_PREF) or str(settings.GRAB_DEFAULT_PATH),
                id="dl-output",
            )
            yield Button("Browse", id="btn-browse-output")
        with Vertical(id="dl-advanced"):
            yield ActionForm(self._action, include=ADVANCED_FIELDS, embedded=True)
        with Horizontal(id="dl-actions"):
            yield Button("Download", id="btn-download", variant="success")
            yield Button("Add to queue", id="btn-queue", variant="primary")
        yield Static("", id="dl-status")
        yield Static("Downloads", classes="section-title")
        with Vertical(id="dl-jobs"):
            yield Static("[dim]Nothing downloading.[/dim]", id="dl-jobs-empty")
        yield Static("History", classes="section-title")
        yield DataTable(id="download-history-table", cursor_type="row")
        with Horizontal():
            yield Button("Clear history", id="btn-clear-history")

    def _quality_set(self, choices: list[QualityChoice]) -> RadioSet:
        selected = _default_choice_index(choices)
        return RadioSet(
            *[
                RadioButton(choice.label, value=index == selected)
                for index, choice in enumerate(choices)
            ],
            id="dl-quality",
        )

    def on_mount(self) -> None:
        self._sync_mode()
        self._load_history()

    # --- mode -------------------------------------------------------------

    def _advanced(self) -> bool:
        return self.query_one("#mode-advanced", RadioButton).value

    def _sync_mode(self) -> None:
        self.query_one("#dl-advanced").display = self._advanced()

    @on(RadioSet.Changed, "#dl-mode")
    def _on_mode(self) -> None:
        self._sync_mode()
        save_pref(MODE_PREF, "advanced" if self._advanced() else "simple")

    # --- link and preview -------------------------------------------------

    def _url(self) -> str:
        return self.query_one("#dl-url", Input).value.strip()

    @on(Input.Changed, "#dl-url")
    def _on_url_changed(self, event: Input.Changed) -> None:
        url = event.value.strip()
        warning = self.query_one("#dl-duplicate", Static)
        existing = DownloadHistory().is_already_downloaded(url) if url else None
        if existing:
            title = escape(existing.get("title") or url)
            warning.update(f"[yellow]You downloaded this before: {title}[/yellow]")
        else:
            warning.update("")

    @on(Input.Submitted, "#dl-url")
    @on(Button.Pressed, "#btn-check")
    def _on_check(self) -> None:
        url = self._url()
        if not url:
            self._set_status("[yellow]Paste a link first.[/yellow]")
            return
        self.query_one("#dl-preview-title", Static).update(
            "[cyan]Checking the link...[/cyan]"
        )
        self.query_one("#dl-preview-meta", Static).update("")
        self.run_worker(
            lambda: self._probe(url), thread=True, exclusive=True, group="probe"
        )

    def _probe(self, url: str) -> None:
        from max_cli.core.operations import grab

        try:
            media = grab.probe(url)
        except Exception as e:
            self.app.call_from_thread(self._show_probe_error, str(e))
            return
        self.app.call_from_thread(self._show_preview, media)

    def _show_probe_error(self, error: str) -> None:
        self.query_one("#dl-preview-title", Static).update(
            f"[red]Couldn't read this link.[/red] {escape(error)}"
        )

    def _show_preview(self, media: Any) -> None:
        title = self.query_one("#dl-preview-title", Static)
        meta = self.query_one("#dl-preview-meta", Static)
        if media.is_playlist:
            title.update(f"[bold]{escape(media.title)}[/bold]")
            meta.update(
                f"Playlist, {len(media.entries)} items"
                + (f"  by {escape(media.uploader)}" if media.uploader else "")
                + ". All items will be downloaded."
            )
            self.call_later(self._set_choices, list(DEFAULT_CHOICES))
            return
        title.update(f"[bold]{escape(media.title)}[/bold]")
        details = [escape(media.uploader), _duration(media.duration)]
        meta.update("  ".join(part for part in details if part))
        self.call_later(self._set_choices, choices_for(media))

    async def _set_choices(self, choices: list[QualityChoice]) -> None:
        self._choices = choices
        # Wait for the old set to go, or the new one's id clashes with it.
        await self.query_one("#dl-quality", RadioSet).remove()
        await self.query_one("#dl-preview", Vertical).mount(self._quality_set(choices))

    def _chosen(self) -> QualityChoice:
        index = self.query_one("#dl-quality", RadioSet).pressed_index
        return (
            self._choices[index]
            if 0 <= index < len(self._choices)
            else self._choices[0]
        )

    # --- folder -----------------------------------------------------------

    @on(Button.Pressed, "#btn-browse-output")
    def _on_browse(self) -> None:
        from max_cli.interface.tui.widgets.dialogs import PathPicker

        field = self.query_one("#dl-output", Input)
        start = Path(field.value).expanduser() if field.value else Path.home()

        def _picked(path: Optional[Path]) -> None:
            if path is not None:
                field.value = str(path)

        self.app.push_screen(PathPicker(start, pick_folder=True), _picked)

    # --- download ---------------------------------------------------------

    def _download_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {"url": self._url()}
        output = self.query_one("#dl-output", Input).value.strip()
        if output:
            values["output"] = output
        values.update(self._chosen().values)
        if self._advanced():
            form = self.query_one("#dl-advanced ActionForm", ActionForm)
            for name, value in form.values().items():
                if value not in (None, ""):
                    values[name] = value
        return values

    def _set_status(self, text: str) -> None:
        self.query_one("#dl-status", Static).update(text)

    @on(Button.Pressed, "#btn-download")
    def _on_download(self) -> None:
        from max_cli.common.exceptions import MaxError
        from max_cli.core.catalog.runner import coerce_args

        values = self._download_values()
        try:
            coerce_args(self._action, values)
        except MaxError as e:
            self._set_status(f"[red]{escape(str(e))}[/red]")
            return
        folder = self.query_one("#dl-output", Input).value.strip()
        if folder:
            save_pref(FOLDER_PREF, folder)
        self._start_job(values)
        self.query_one("#dl-url", Input).value = ""
        self._set_status("")

    @on(Button.Pressed, "#btn-queue")
    def _on_queue(self) -> None:
        from max_cli.common.exceptions import MaxError
        from max_cli.core.catalog.runner import enqueue_action

        try:
            task = enqueue_action(self._action, self._download_values())
        except MaxError as e:
            self._set_status(f"[red]{escape(str(e))}[/red]")
            return
        self._set_status(f"[green]Added to the queue[/green] (ID: {task.id}).")

    def _title_for(self, url: str) -> str:
        from max_cli.core.operations import grab

        return grab._cached_title(url) or url

    def _start_job(self, values: dict[str, Any]) -> DownloadJob:
        job = DownloadJob(
            job_id=self._next_job_id,
            url=values["url"],
            values=values,
            title=self._title_for(values["url"]),
        )
        self._next_job_id += 1
        self._jobs[job.job_id] = job
        self.query_one("#dl-jobs-empty").display = False
        self.query_one("#dl-jobs", Vertical).mount(DownloadRow(job))
        self.run_worker(lambda: self._run_job(job), thread=True, group="downloads")
        return job

    def _row(self, job: DownloadJob) -> DownloadRow:
        return self.query_one(f"#job-{job.job_id}", DownloadRow)

    def _row_call(self, job: DownloadJob, method: str, *args: Any) -> None:
        """Update a job's row. Workers call this through call_from_thread."""
        getattr(self._row(job), method)(*args)

    def _run_job(self, job: DownloadJob) -> None:
        """Runs in a thread worker: wait for a slot, download, report back."""
        from max_cli.common.exceptions import OperationCancelled
        from max_cli.core.catalog.runner import run_action

        while not self._slots.acquire(timeout=SLOT_POLL_SECONDS):
            if job.cancel.is_set():
                self.app.call_from_thread(self._row_call, job, "set_cancelled")
                return
        try:
            if job.cancel.is_set():
                self.app.call_from_thread(self._row_call, job, "set_cancelled")
                return
            self.app.call_from_thread(self._row_call, job, "set_started")
            last_update = 0.0

            def on_progress(status: dict[str, Any]) -> None:
                nonlocal last_update
                title = (status.get("info_dict") or {}).get("title")
                if title and title != job.title:
                    self.app.call_from_thread(self._row_call, job, "set_title", title)
                if status.get("status") != "downloading":
                    return
                now = time.monotonic()
                if now - last_update < PROGRESS_REFRESH_SECONDS:
                    return
                last_update = now
                total = (
                    status.get("total_bytes") or status.get("total_bytes_estimate") or 0
                )
                percent = (
                    status.get("downloaded_bytes", 0) / total * 100 if total else 0.0
                )
                self.app.call_from_thread(
                    self._row_call,
                    job,
                    "set_progress",
                    percent,
                    float(status.get("speed") or 0),
                    int(status.get("eta") or 0),
                )

            try:
                result = run_action(
                    self._action,
                    job.values,
                    should_cancel=job.cancel.is_set,
                    progress_hook=on_progress,
                )
            except OperationCancelled:
                self.app.call_from_thread(self._row_call, job, "set_cancelled")
            except Exception as e:
                self.app.call_from_thread(self._row_call, job, "set_failed", str(e))
            else:
                if result.output_files:
                    job.output_folder = result.output_files[0].parent
                self.app.call_from_thread(
                    self._row_call,
                    job,
                    "set_done",
                    result.message,
                    int(result.details.get("size_bytes") or 0),
                )
        finally:
            self._slots.release()
            self.app.call_from_thread(self._load_history)

    @on(Button.Pressed)
    def _on_row_button(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        kind, _, number = button_id.partition("-")
        if kind not in ("cancel", "retry", "open") or not number.isdigit():
            return
        job = self._jobs.get(int(number))
        if job is None:
            return
        event.stop()
        if kind == "cancel":
            job.cancel.set()
            event.button.disabled = True
            event.button.label = "Cancelling..."
        elif kind == "retry":
            self._row(job).remove()
            self._start_job(dict(job.values))
        elif kind == "open":
            from max_cli.common.utils import open_in_file_manager

            folder = job.output_folder or Path(
                job.values.get("output") or settings.GRAB_DEFAULT_PATH
            )
            open_in_file_manager(Path(folder).expanduser())

    # --- history ----------------------------------------------------------

    def _load_history(self) -> None:
        table = self.query_one("#download-history-table", DataTable)
        table.clear(columns=True)
        table.add_column("", width=2)
        table.add_column("Title", width=40)
        table.add_column("Size", width=10)
        table.add_column("Source", width=16)
        table.add_column("When", width=10)
        for entry in DownloadHistory().get_recent(limit=50):
            ok = entry.get("status") == "completed"
            files = entry.get("output_files") or []
            title = entry.get("title") or (Path(files[0]).name if files else "")
            table.add_row(
                "[green]✓[/green]" if ok else "[red]✗[/red]",
                escape(title),
                format_size(entry.get("file_size") or 0)
                if entry.get("file_size")
                else "-",
                entry.get("domain", ""),
                self._format_relative_time(entry.get("timestamp", "")),
            )

    @on(Button.Pressed, "#btn-clear-history")
    def _on_clear_history(self) -> None:
        from max_cli.interface.tui.widgets.dialogs import ConfirmDialog

        def _answered(confirmed: Optional[bool]) -> None:
            if not confirmed:
                return
            count = DownloadHistory().clear_history()
            self._load_history()
            self._set_status(f"Cleared {count} history entries.")

        self.app.push_screen(
            ConfirmDialog(
                "Clear the download history? Your files stay where they are."
            ),
            _answered,
        )

    @staticmethod
    def _format_relative_time(timestamp_raw: str) -> str:
        if not timestamp_raw:
            return ""
        try:
            seconds = (
                datetime.now() - datetime.fromisoformat(timestamp_raw)
            ).total_seconds()
        except (ValueError, TypeError):
            return ""
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            return f"{int(seconds // 60)}m ago"
        if seconds < 86400:
            return f"{int(seconds // 3600)}h ago"
        return f"{int(seconds // 86400)}d ago"
