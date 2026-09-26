"""Download page: paste a link, see what it is, pick a format and quality, download.

- Pasting a link checks it: title, channel, length, and the qualities the
  video really has, with sizes. A playlist lists its items to tick.
  Several links pasted at once become one download each.
- Simple mode shows only that. Advanced mode adds every other `grab
  download` option, taken from the command catalog.
- Each download gets a row with progress and a Cancel that really stops it.
  History sits in the next tab.

See PLANS/active/grab-page-redesign.md.
"""

import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.content import Content
from textual.timer import Timer
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    ProgressBar,
    SelectionList,
    Static,
    TabbedContent,
    TabPane,
)

from max_cli.common.utils import format_size
from max_cli.config import settings
from max_cli.core.catalog import get_action
from max_cli.core.engines.download_history import DownloadHistory
from max_cli.interface.tui.text import markup
from max_cli.interface.tui.ui_prefs import load_prefs, save_pref
from max_cli.interface.tui.widgets.action_form import ActionForm

GRAB_ACTION_ID = "grab.download"
# Advanced mode shows these catalog options. The Format and Quality buttons
# already cover media type, quality and (for odd heights) resolution.
ADVANCED_FIELDS = (
    "resolution",
    "subtitles",
    "include_metadata",
    "no_playlist",
    "strip_playlist",
    "player_client",
)
LINK_PATTERN = re.compile(r"https?://\S+")
AUTO_CHECK_SECONDS = 0.6
PROGRESS_REFRESH_SECONDS = 0.25
SLOT_POLL_SECONDS = 0.2
HISTORY_LIMIT = 50
PREVIEW_LINK_LIMIT = 8
MODE_PREF = "download_mode"
FOLDER_PREF = "download_folder"
FORMAT_PREF = "download_format"


@dataclass
class QualityChoice:
    label: str
    values: dict[str, Any]  # quality / resolution for grab.download


VIDEO_CHOICES = [
    QualityChoice("Best", {"quality": "x"}),
    QualityChoice("1080p", {"quality": "h"}),
    QualityChoice("720p", {"quality": "m"}),
    QualityChoice("480p", {"quality": "s"}),
    QualityChoice("360p", {"quality": "ss"}),
]
# The bitrates network_engine.QUALITY_MAP gives yt-dlp's MP3 conversion.
AUDIO_CHOICES = [
    QualityChoice("Best · 320 kbps", {"quality": "x"}),
    QualityChoice("High · 192 kbps", {"quality": "h"}),
    QualityChoice("Medium · 128 kbps", {"quality": "m"}),
    QualityChoice("Small · 64 kbps", {"quality": "s"}),
]


def short_size(size_bytes: float) -> str:
    """Rounded size for labels: 296 MB, 1.2 GB, 850 KB."""
    for unit, scale in (("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)):
        if size_bytes >= scale:
            value = size_bytes / scale
            return f"{value:.1f} {unit}" if value < 10 else f"{value:.0f} {unit}"
    return f"{size_bytes:.0f} B"


def _with_size(label: str, size: Optional[int]) -> str:
    return f"{label} · {short_size(size)}" if size else label


def video_choices_for(media: Any) -> list[QualityChoice]:
    """Choices for a checked video: Best, then each height it offers, with sizes."""
    choices = [QualityChoice("Best", {"quality": "x"})]
    for option in media.qualities:
        values: dict[str, Any] = (
            {"quality": option.quality_code}
            if option.quality_code
            else {"resolution": option.height}
        )
        choices.append(
            QualityChoice(_with_size(option.label, option.size_bytes), values)
        )
    return choices


def playlist_items(selected: list[int], total: int) -> Optional[str]:
    """yt-dlp's playlist_items for the ticked items: None for all, else "1-3,7"."""
    if len(selected) == total:
        return None
    ranges: list[list[int]] = []
    for index in sorted(selected):
        if ranges and ranges[-1][1] == index - 1:
            ranges[-1][1] = index
        else:
            ranges.append([index, index])
    return ",".join(
        str(start) if start == end else f"{start}-{end}" for start, end in ranges
    )


def _duration(seconds: Optional[float]) -> str:
    if not seconds:
        return ""
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes}:{secs:02}"


def _relative_time(timestamp_raw: str) -> str:
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


@dataclass
class DownloadJob:
    job_id: int
    url: str
    values: dict[str, Any]
    title: str
    cancel: threading.Event = field(default_factory=threading.Event)
    output_folder: Optional[Path] = None
    finished: bool = False


class DownloadRow(Vertical):
    """One download: title and button on top, then progress and details."""

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
        text-style: bold;
        padding-top: 1;
    }
    DownloadRow ProgressBar, DownloadRow ProgressBar Bar {
        width: 1fr;
    }
    DownloadRow .row-info {
        color: $text-muted;
    }
    DownloadRow Button {
        min-width: 14;
    }
    """

    def __init__(self, job: DownloadJob) -> None:
        super().__init__(id=f"job-{job.job_id}")
        self.job = job

    def compose(self) -> ComposeResult:
        with Horizontal(classes="row-head"):
            yield Static(Content(self.job.title), classes="row-title")
            yield Button("Cancel", id=f"cancel-{self.job.job_id}", variant="error")
        yield ProgressBar(total=100, show_eta=False, show_percentage=False)
        yield Static("Waiting for a free slot...", classes="row-info")

    def _info(self, text: "str | Content") -> None:
        self.query_one(".row-info", Static).update(text)

    def set_title(self, title: str) -> None:
        self.job.title = title
        self.query_one(".row-title", Static).update(Content(title))

    def set_started(self) -> None:
        self._info("Starting...")

    def set_progress(self, percent: float, speed: float, eta: int) -> None:
        self.query_one(ProgressBar).progress = percent
        parts = [f"{percent:.0f}%"]
        if speed:
            parts.append(f"{format_size(speed)}/s")
        if eta:
            parts.append(f"{_duration(eta)} left")
        self._info("  ·  ".join(parts))

    def _swap_button(
        self, label: str, button_id: str, variant: str = "default"
    ) -> None:
        head = self.query_one(".row-head", Horizontal)
        for button in head.query(Button):
            button.remove()
        head.mount(Button(label, id=button_id, variant=variant))  # type: ignore[arg-type]  # variant is one of Textual's literals

    def set_done(self, message: str, size_bytes: int) -> None:
        self.job.finished = True
        self.query_one(ProgressBar).progress = 100
        size = f"  ·  {format_size(size_bytes)}" if size_bytes else ""
        self._info(
            markup("[green]Done.[/green] $message$size", message=message, size=size)
        )
        self._swap_button("Open folder", f"open-{self.job.job_id}", "success")

    def set_failed(self, error: str) -> None:
        self.job.finished = True
        self.query_one(ProgressBar).display = False
        self._info(markup("[red]Failed:[/red] $error", error=error))
        self._swap_button("Retry", f"retry-{self.job.job_id}", "warning")

    def set_cancelled(self) -> None:
        self.job.finished = True
        self.query_one(ProgressBar).display = False
        self._info(
            Content.from_markup(
                "[yellow]Cancelled.[/yellow] Partial files were removed."
            )
        )
        self._swap_button("Retry", f"retry-{self.job.job_id}", "warning")


class DownloadPanel(Vertical):
    """The Download page."""

    DEFAULT_CSS = """
    DownloadPanel {
        height: 1fr;
        overflow-y: auto;
        padding: 0 1;
    }
    #dl-header {
        height: 3;
    }
    #dl-title {
        width: 1fr;
        padding-top: 1;
        text-style: bold;
        color: $accent;
    }
    .segmented {
        width: auto;
        height: 3;
    }
    .segmented Button, .chip {
        min-width: 10;
        margin: 0;
        border: tall $boost;
        background: $surface;
    }
    .segmented Button.-selected, .chip.-selected {
        background: $accent;
        text-style: bold;
        border: tall $accent;
    }
    .card {
        height: auto;
        border: round $border;
        border-title-color: $accent;
        border-title-style: bold;
        padding: 0 1;
        margin-bottom: 1;
    }
    #dl-link-row, #dl-folder-row, #dl-format-row, #dl-actions,
    #dl-playlist-actions, #dl-quality-row {
        height: auto;
    }
    #dl-url, #dl-output {
        width: 1fr;
    }
    #dl-preview-title {
        text-style: bold;
    }
    #dl-preview-meta, #dl-duplicate, .field-name {
        color: $text-muted;
    }
    .field-name {
        width: 10;
        padding-top: 1;
    }
    #dl-quality {
        grid-size: 3;
        grid-gutter: 0 1;
        grid-rows: 3;
        height: auto;
        width: 1fr;
    }
    #dl-quality .chip {
        width: 100%;
    }
    #dl-playlist {
        height: auto;
        max-height: 14;
    }
    #dl-advanced ActionForm {
        height: auto;
    }
    #btn-download {
        width: 1fr;
        max-width: 64;
    }
    #dl-status {
        margin-top: 1;
    }
    #dl-tabs {
        height: auto;
        margin-top: 1;
    }
    #dl-jobs-empty {
        color: $text-muted;
        padding: 1 0;
    }
    #dl-jobs {
        height: auto;
    }
    #download-history-table {
        height: auto;
        max-height: 16;
    }
    #dl-history-actions {
        height: auto;
        margin-top: 1;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._action = get_action(GRAB_ACTION_ID)
        prefs = load_prefs()
        self._advanced = prefs.get(MODE_PREF) == "advanced"
        self._format = prefs.get(FORMAT_PREF) or settings.GRAB_DEFAULT_TYPE
        self._video_choices: list[QualityChoice] = list(VIDEO_CHOICES)
        # The pick per format, by its grab values, so it survives a new list.
        self._chosen: dict[str, dict[str, Any]] = {
            "video": self._default_video_values(),
            "audio": AUDIO_CHOICES[1].values,
        }
        self._media: Any = None  # the checked MediaInfo, if any
        self._checked_text = ""  # the link box text that _media belongs to
        self._check_timer: Optional[Timer] = None
        self._jobs: dict[int, DownloadJob] = {}
        self._next_job_id = 1
        self._slots = threading.BoundedSemaphore(settings.GRAB_MAX_CONCURRENT)
        self._history: list[dict[str, Any]] = []

    # --- layout ---------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Horizontal(id="dl-header"):
            yield Static("⬇  Download", id="dl-title")
            with Horizontal(id="dl-mode", classes="segmented"):
                yield Button("Simple", id="mode-simple")
                yield Button("Advanced", id="mode-advanced")

        with Vertical(id="dl-link-card", classes="card"):
            with Horizontal(id="dl-link-row"):
                yield Input(
                    placeholder="Paste a YouTube link, or several (Ctrl+V)",
                    id="dl-url",
                )
                yield Button("Check", id="btn-check")
            yield Static("", id="dl-duplicate")

        with Vertical(id="dl-preview", classes="card"):
            yield Static(
                "Paste a link and Max checks it for you. You can also download right away.",
                id="dl-preview-title",
            )
            yield Static("", id="dl-preview-meta")
            with Horizontal(id="dl-format-row"):
                yield Label("Format", classes="field-name")
                with Horizontal(classes="segmented"):
                    yield Button("Video", id="fmt-video")
                    yield Button("Audio (MP3)", id="fmt-audio")
            with Horizontal(id="dl-quality-row"):
                yield Label("Quality", classes="field-name")
                yield Grid(id="dl-quality")
            yield SelectionList[int](id="dl-playlist")
            with Horizontal(id="dl-playlist-actions"):
                yield Button("Select all", id="btn-pl-all")
                yield Button("Select none", id="btn-pl-none")

        with Vertical(id="dl-advanced", classes="card"):
            yield ActionForm(self._action, include=ADVANCED_FIELDS, embedded=True)

        with Horizontal(id="dl-folder-row"):
            yield Label("Save to", classes="field-name")
            yield Input(
                value=load_prefs().get(FOLDER_PREF) or str(settings.GRAB_DEFAULT_PATH),
                id="dl-output",
            )
            yield Button("Change...", id="btn-browse-output")

        with Horizontal(id="dl-actions"):
            yield Button("⬇ Download", id="btn-download", variant="success")
            yield Button("Queue for later", id="btn-queue")
        yield Static("", id="dl-status")

        with TabbedContent(id="dl-tabs"):
            with TabPane("Downloads", id="tab-active"):
                yield Static(
                    "No downloads yet. Paste a link above to start.",
                    id="dl-jobs-empty",
                )
                yield Vertical(id="dl-jobs")
            with TabPane("History", id="tab-history"):
                yield DataTable(id="download-history-table", cursor_type="row")
                with Horizontal(id="dl-history-actions"):
                    yield Button("Download again", id="btn-history-again")
                    yield Button("Open folder", id="btn-history-open")
                    yield Button(
                        "Clear history", id="btn-clear-history", variant="error"
                    )

    async def on_mount(self) -> None:
        self.query_one("#dl-link-card").border_title = "Link"
        self.query_one("#dl-preview").border_title = "What you'll get"
        self.query_one("#dl-advanced").border_title = "Advanced options"
        self.query_one("#dl-duplicate").display = False
        self._sync_mode()
        self._sync_format_buttons()
        self._show_playlist(False)
        await self._render_choices()
        self._load_history()

    def on_show(self) -> None:
        self.query_one("#dl-url", Input).focus()

    # --- mode and format --------------------------------------------------

    def _sync_mode(self) -> None:
        self.query_one("#dl-advanced").display = self._advanced
        self.query_one("#mode-simple").set_class(not self._advanced, "-selected")
        self.query_one("#mode-advanced").set_class(self._advanced, "-selected")

    @on(Button.Pressed, "#mode-simple, #mode-advanced")
    def _on_mode(self, event: Button.Pressed) -> None:
        self._advanced = event.button.id == "mode-advanced"
        self._sync_mode()
        save_pref(MODE_PREF, "advanced" if self._advanced else "simple")

    def _sync_format_buttons(self) -> None:
        self.query_one("#fmt-video").set_class(self._format == "video", "-selected")
        self.query_one("#fmt-audio").set_class(self._format == "audio", "-selected")

    @on(Button.Pressed, "#fmt-video, #fmt-audio")
    async def _on_format(self, event: Button.Pressed) -> None:
        self._format = "audio" if event.button.id == "fmt-audio" else "video"
        save_pref(FORMAT_PREF, self._format)
        self._sync_format_buttons()
        await self._render_choices()

    # --- quality chips ----------------------------------------------------

    def _choices(self) -> list[QualityChoice]:
        return AUDIO_CHOICES if self._format == "audio" else self._video_choices

    @staticmethod
    def _default_video_values() -> dict[str, Any]:
        last = DownloadHistory().get_last_settings()
        return {"quality": last.get("quality") or settings.GRAB_QUALITY}

    def _chosen_index(self) -> int:
        choices = self._choices()
        for index, choice in enumerate(choices):
            if choice.values == self._chosen[self._format]:
                return index
        return 0

    async def _render_choices(self) -> None:
        grid = self.query_one("#dl-quality", Grid)
        await grid.remove_children()
        choices = self._choices()
        chosen = self._chosen_index()
        self._chosen[self._format] = choices[chosen].values
        await grid.mount_all(
            Button(
                choice.label,
                id=f"chip-{index}",
                classes="chip -selected" if index == chosen else "chip",
            )
            for index, choice in enumerate(choices)
        )
        self._sync_download_label()

    @on(Button.Pressed, ".chip")
    def _on_chip(self, event: Button.Pressed) -> None:
        index = int((event.button.id or "chip-0").split("-")[1])
        self._chosen[self._format] = self._choices()[index].values
        for chip in self.query(".chip"):
            chip.set_class(chip.id == event.button.id, "-selected")
        self._sync_download_label()

    def _chosen_choice(self) -> QualityChoice:
        return self._choices()[self._chosen_index()]

    # --- link and preview -------------------------------------------------

    def _links(self) -> list[str]:
        text = self.query_one("#dl-url", Input).value
        return LINK_PATTERN.findall(text) or ([text.strip()] if text.strip() else [])

    @on(Input.Changed, "#dl-url")
    def _on_url_changed(self, event: Input.Changed) -> None:
        links = self._links()
        existing = (
            DownloadHistory().is_already_downloaded(links[0])
            if len(links) == 1
            else None
        )
        warning = self.query_one("#dl-duplicate", Static)
        warning.display = existing is not None
        if existing:
            warning.update(
                markup(
                    "[yellow]You downloaded this before:[/yellow] $title",
                    title=existing.get("title") or links[0],
                )
            )
        if self._check_timer is not None:
            self._check_timer.stop()
        if links and LINK_PATTERN.match(links[0]) and event.value != self._checked_text:
            self._check_timer = self.set_timer(AUTO_CHECK_SECONDS, self._check)
        self._sync_download_label()

    @on(Input.Submitted, "#dl-url")
    def _on_url_submitted(self) -> None:
        """Enter checks the link; Enter again on a checked link downloads it."""
        text = self.query_one("#dl-url", Input).value
        if self._media is not None and text == self._checked_text:
            self._on_download()
        else:
            self._check()

    @on(Button.Pressed, "#btn-check")
    def _check(self) -> None:
        if self._check_timer is not None:
            self._check_timer.stop()
        text = self.query_one("#dl-url", Input).value
        links = self._links()
        if not links:
            self._set_status(
                Content.from_markup("[yellow]Paste a link first.[/yellow]")
            )
            return
        self._checked_text = text
        if len(links) > 1:
            self._show_many(links)
            return
        self._set_preview(Content.from_markup("[cyan]Checking the link...[/cyan]"), "")
        url = links[0]
        self.run_worker(
            lambda: self._probe(url, text), thread=True, exclusive=True, group="probe"
        )

    def _probe(self, url: str, text: str) -> None:
        from max_cli.core.operations import grab

        try:
            media = grab.probe(url)
        except Exception as e:
            self.app.call_from_thread(self._show_probe_error, str(e))
            return
        self.app.call_from_thread(self._show_media, media, text)

    def _set_preview(self, title: "str | Content", meta: "str | Content") -> None:
        self.query_one("#dl-preview-title", Static).update(title)
        self.query_one("#dl-preview-meta", Static).update(meta)

    def _show_probe_error(self, error: str) -> None:
        self._media = None
        self._set_preview(
            Content.from_markup("[red]Couldn't read this link.[/red]"), Content(error)
        )

    def _show_many(self, links: list[str]) -> None:
        self._media = None
        self._show_playlist(False)
        self._video_choices = list(VIDEO_CHOICES)
        self.call_later(self._render_choices)
        shown = "\n".join(links[:PREVIEW_LINK_LIMIT])
        more = "\n..." if len(links) > PREVIEW_LINK_LIMIT else ""
        self._set_preview(f"{len(links)} links", Content(shown + more))

    def _show_media(self, media: Any, text: str) -> None:
        if self.query_one("#dl-url", Input).value != text:
            return  # the link changed while we were checking
        self._media = media
        if media.is_playlist:
            meta = [media.uploader, f"Playlist · {len(media.entries)} items"]
            self._video_choices = list(VIDEO_CHOICES)
            self._fill_playlist(media)
        else:
            meta = [media.uploader, _duration(media.duration)]
            self._video_choices = video_choices_for(media)
            self._show_playlist(False)
        self._set_preview(
            Content(media.title), Content("  ·  ".join(part for part in meta if part))
        )
        self.call_later(self._render_choices)

    # --- playlist ---------------------------------------------------------

    def _show_playlist(self, visible: bool) -> None:
        self.query_one("#dl-playlist").display = visible
        self.query_one("#dl-playlist-actions").display = visible

    def _fill_playlist(self, media: Any) -> None:
        playlist = self.query_one("#dl-playlist", SelectionList)
        playlist.clear_options()
        playlist.add_options(
            (
                Content(
                    f"{entry.index:>3}.  {entry.title}  {_duration(entry.duration)}"
                ),
                entry.index,
                True,
            )
            for entry in media.entries
        )
        self._show_playlist(True)

    @on(Button.Pressed, "#btn-pl-all")
    def _on_select_all(self) -> None:
        self.query_one("#dl-playlist", SelectionList).select_all()

    @on(Button.Pressed, "#btn-pl-none")
    def _on_select_none(self) -> None:
        self.query_one("#dl-playlist", SelectionList).deselect_all()

    @on(SelectionList.SelectedChanged, "#dl-playlist")
    def _on_playlist_changed(self) -> None:
        self._sync_download_label()

    # --- download ---------------------------------------------------------

    def _selected_items(self) -> Optional[list[int]]:
        if self._media is None or not self._media.is_playlist:
            return None
        return list(self.query_one("#dl-playlist", SelectionList).selected)

    def _sync_download_label(self) -> None:
        label_parts = self._chosen_choice().label.split(" · ")
        what = label_parts[0] if self._format == "video" else "MP3"
        size = (
            label_parts[1] if len(label_parts) > 1 and self._format == "video" else ""
        )
        label = f"⬇ Download {what}" + (f" · {size}" if size else "")
        selected = self._selected_items()
        if selected is not None:
            total = len(self._media.entries)
            label = f"⬇ Download {len(selected)} of {total} items · {what}"
        elif len(self._links()) > 1:
            label = f"⬇ Download {len(self._links())} links · {what}"
        self.query_one("#btn-download", Button).label = label

    def _values_for(self, url: str) -> dict[str, Any]:
        values: dict[str, Any] = {"url": url, "media_type": self._format}
        output = self.query_one("#dl-output", Input).value.strip()
        if output:
            values["output"] = output
        values.update(self._chosen_choice().values)
        selected = self._selected_items()
        if selected is not None:
            items = playlist_items(selected, len(self._media.entries))
            if items:
                values["playlist_items"] = items
        if self._advanced:
            form = self.query_one("#dl-advanced ActionForm", ActionForm)
            for name, value in form.values().items():
                if value not in (None, ""):
                    values[name] = value
        return values

    def _set_status(self, text: "str | Content") -> None:
        self.query_one("#dl-status", Static).update(text)

    def _validated(self) -> Optional[list[dict[str, Any]]]:
        from max_cli.common.exceptions import MaxError
        from max_cli.core.catalog.runner import coerce_args

        links = self._links()
        if not links:
            self._set_status(
                Content.from_markup("[yellow]Paste a link first.[/yellow]")
            )
            return None
        if self._selected_items() == []:
            self._set_status(
                Content.from_markup("[yellow]Tick at least one playlist item.[/yellow]")
            )
            return None
        all_values = [self._values_for(url) for url in links]
        try:
            for values in all_values:
                coerce_args(self._action, values)
        except MaxError as e:
            self._set_status(markup("[red]$error[/red]", error=e))
            return None
        return all_values

    @on(Button.Pressed, "#btn-download")
    def _on_download(self) -> None:
        all_values = self._validated()
        if all_values is None:
            return
        folder = self.query_one("#dl-output", Input).value.strip()
        if folder:
            save_pref(FOLDER_PREF, folder)
        for values in all_values:
            self._start_job(values)
        self.query_one("#dl-tabs", TabbedContent).active = "tab-active"
        self._set_status("")
        self._reset_link()

    @on(Button.Pressed, "#btn-queue")
    def _on_queue(self) -> None:
        from max_cli.core.catalog.runner import enqueue_action

        all_values = self._validated()
        if all_values is None:
            return
        for values in all_values:
            enqueue_action(self._action, values)
        self._set_status(
            Content.from_markup(
                f"[green]Added {len(all_values)} to the queue.[/green] "
                "The Queue page shows them."
            )
        )
        self._reset_link()

    def _reset_link(self) -> None:
        self._media = None
        self._checked_text = ""
        self.query_one("#dl-url", Input).value = ""
        self._show_playlist(False)
        self._set_preview("Paste another link, or several.", "")

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
        self._sync_tab_counts()
        self.run_worker(lambda: self._run_job(job), thread=True, group="downloads")
        return job

    def _row(self, job: DownloadJob) -> DownloadRow:
        return self.query_one(f"#job-{job.job_id}", DownloadRow)

    def _row_call(self, job: DownloadJob, method: str, *args: Any) -> None:
        """Update a job's row. Workers call this through call_from_thread."""
        getattr(self._row(job), method)(*args)
        self._sync_tab_counts()

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
                done = status.get("downloaded_bytes", 0)
                self.app.call_from_thread(
                    self._row_call,
                    job,
                    "set_progress",
                    done / total * 100 if total else 0.0,
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

    def _sync_tab_counts(self) -> None:
        running = sum(not job.finished for job in self._jobs.values())
        tabs = self.query_one("#dl-tabs", TabbedContent)
        tabs.get_tab("tab-active").label = (
            f"Downloads ({running} running)" if running else "Downloads"
        )
        tabs.get_tab("tab-history").label = f"History ({len(self._history)})"

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
            del self._jobs[job.job_id]
            self._start_job(dict(job.values))
        elif kind == "open":
            self._open_folder(job.output_folder or job.values.get("output"))

    @staticmethod
    def _open_folder(folder: Any) -> None:
        from max_cli.common.utils import open_in_file_manager

        open_in_file_manager(Path(folder or settings.GRAB_DEFAULT_PATH).expanduser())

    # --- folder -----------------------------------------------------------

    @on(Button.Pressed, "#btn-browse-output")
    def _on_browse(self) -> None:
        from max_cli.interface.tui.widgets.dialogs import PathPicker

        folder_input = self.query_one("#dl-output", Input)
        start = (
            Path(folder_input.value).expanduser() if folder_input.value else Path.home()
        )

        def _picked(path: Optional[Path]) -> None:
            if path is not None:
                folder_input.value = str(path)

        self.app.push_screen(PathPicker(start, pick_folder=True), _picked)

    # --- history ----------------------------------------------------------

    def _load_history(self) -> None:
        self._history = DownloadHistory().get_recent(limit=HISTORY_LIMIT)
        table = self.query_one("#download-history-table", DataTable)
        table.clear(columns=True)
        table.add_column("", width=2)
        table.add_column("Title", width=46)
        table.add_column("Size", width=10)
        table.add_column("Source", width=16)
        table.add_column("When", width=10)
        for entry in self._history:
            ok = entry.get("status") == "completed"
            files = entry.get("output_files") or []
            title = entry.get("title") or (Path(files[0]).name if files else "")
            size = entry.get("file_size") or 0
            table.add_row(
                Content.from_markup("[green]✓[/green]" if ok else "[red]✗[/red]"),
                Content(title),
                format_size(size) if size else "-",
                entry.get("domain", ""),
                _relative_time(entry.get("timestamp", "")),
            )
        self._sync_tab_counts()

    def _selected_history(self) -> Optional[dict[str, Any]]:
        table = self.query_one("#download-history-table", DataTable)
        if not self._history or table.cursor_row < 0:
            return None
        return self._history[min(table.cursor_row, len(self._history) - 1)]

    @on(Button.Pressed, "#btn-history-again")
    def _on_history_again(self) -> None:
        entry = self._selected_history()
        if entry is None:
            return
        self.query_one("#dl-url", Input).value = entry.get("url", "")
        self._check()

    @on(Button.Pressed, "#btn-history-open")
    def _on_history_open(self) -> None:
        entry = self._selected_history()
        if entry is None:
            return
        files = entry.get("output_files") or []
        self._open_folder(Path(files[0]).parent if files else entry.get("output_path"))

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
