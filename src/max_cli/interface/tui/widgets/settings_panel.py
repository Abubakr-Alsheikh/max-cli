"""Settings page: what Max does by default, and upkeep of its data.

It replaces the Config, System and Analytics pages. Only settings that some
code reads appear here, each with a control that fits it: a hidden API key
with Show, lists for choices, checkboxes, a folder picker. Save checks the
values, writes only the changed keys to ~/.max_config.env and applies them
to the running app.

MAINTENANCE shows versions, whether FFmpeg is found, the size of
~/.max_cli, and clears the cache, old undo backups and old undo logs, each
after a confirmation.
"""

import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.content import Content
from textual.widgets import Button, Checkbox, Input, Label, Select, Static

from max_cli.common.utils import format_size
from max_cli.config import Settings, settings
from max_cli.interface.tui.text import markup

KEEP_DAYS = 30
# Settings also loads this file from the current folder, after the saved one.
LOCAL_ENV_FILE = ".env"
SECRET_HIDDEN_LABEL = "Show"
SECRET_SHOWN_LABEL = "Hide"


@dataclass(frozen=True)
class SettingField:
    name: str  # the Settings field
    label: str
    kind: str  # text, secret, path, int, bool or choice
    help: str
    choices: tuple[tuple[str, str], ...] = ()  # (label, saved value)
    wide: bool = False  # takes both columns of its card


CARDS: tuple[tuple[str, str, tuple[SettingField, ...]], ...] = (
    (
        "AI",
        "settings-ai",
        (
            SettingField(
                "OPENAI_API_KEY",
                "API key",
                "secret",
                "Your OpenAI key, or an OpenRouter or Gemini key with its base URL.",
                wide=True,
            ),
            SettingField(
                "OPENAI_BASE_URL",
                "Base URL",
                "text",
                "Empty for OpenAI. OpenRouter: https://openrouter.ai/api/v1",
                wide=True,
            ),
            SettingField(
                "AI_MODEL", "Chat model", "text", "For ask, chat and analyze."
            ),
            SettingField(
                "AI_IMAGE_MODEL",
                "Image model",
                "text",
                "For creating and editing images.",
            ),
            SettingField(
                "OLLAMA_ENABLED",
                "Use Ollama on this computer instead",
                "bool",
                "Runs a local model; no API key needed.",
                wide=True,
            ),
            SettingField(
                "OLLAMA_BASE_URL", "Ollama URL", "text", "Where Ollama listens."
            ),
            SettingField("OLLAMA_MODEL", "Ollama model", "text", "For example llama3."),
        ),
    ),
    (
        "DOWNLOADS",
        "settings-downloads",
        (
            SettingField(
                "GRAB_DEFAULT_PATH", "Save to", "path", "Where downloads go.", wide=True
            ),
            SettingField(
                "GRAB_DEFAULT_TYPE",
                "Format",
                "choice",
                "What a download gets when you don't pick.",
                (("Video", "video"), ("Audio (MP3)", "audio")),
            ),
            SettingField(
                "GRAB_QUALITY",
                "Quality",
                "choice",
                "Video height, or the MP3 bitrate for audio.",
                (
                    ("360p", "ss"),
                    ("480p", "s"),
                    ("720p", "m"),
                    ("1080p", "h"),
                    ("Best (up to 4K)", "x"),
                ),
            ),
            SettingField(
                "GRAB_MAX_CONCURRENT",
                "Downloads at once",
                "choice",
                "On the Download page. Applies the next time max starts.",
                tuple((str(count), str(count)) for count in range(1, 9)),
            ),
            SettingField(
                "GRAB_INCLUDE_METADATA",
                "Embed title, artist and thumbnail",
                "bool",
                "Tags the file so players show them.",
            ),
            SettingField(
                "GRAB_STRIP_PLAYLIST",
                "Single videos drop the playlist part of their link",
                "bool",
                "So a video link from a playlist gets only that video.",
                wide=True,
            ),
        ),
    ),
    (
        "IMAGES",
        "settings-images",
        (
            SettingField(
                "DEFAULT_QUALITY",
                "Image quality (1-100)",
                "int",
                "For compress and convert, when you don't pick one.",
            ),
            SettingField(
                "MAX_WORKERS",
                "Images at once (1-16)",
                "int",
                "More is faster and uses more memory.",
            ),
        ),
    ),
)
FIELDS = {field.name: field for _title, _id, fields in CARDS for field in fields}
# Settings no code reads, so the page leaves them out. A test fails when code
# starts reading one of them, or when a new setting is neither shown nor here.
UNUSED = frozenset(
    {
        "APP_NAME",
        "BATCH_SIZE",
        "CONFIRM_DESTRUCTIVE",
        "DOWNLOAD_TIMEOUT",
        "GRAB_AUDIO_FORMAT",
        "GRAB_QUEUE_ENABLED",
        "MAX_RETRIES",
        "PROGRESS_BAR",
        "VERBOSE",
    }
)
# Settings read once at start-up; a change applies the next time max starts.
APPLY_ON_RESTART = frozenset({"GRAB_MAX_CONCURRENT"})
# Optional settings: an empty box removes them from the file.
OPTIONAL = frozenset({"OPENAI_API_KEY", "OPENAI_BASE_URL"})


def saved_text(name: str) -> Optional[str]:
    """A setting's current value as the text the file holds; None when unset."""
    value = getattr(settings, name)
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def validate_changes(changes: dict[str, Optional[str]]) -> Settings:
    """Settings with `changes` applied. Raises pydantic's ValidationError."""
    return Settings(**changes)  # type: ignore[arg-type]  # pydantic parses the text


def _error_text(error: Any) -> str:
    """The first problem in a pydantic ValidationError, in the page's words."""
    first = error.errors()[0]
    name = str(first["loc"][0]) if first.get("loc") else ""
    label = FIELDS[name].label if name in FIELDS else name
    return f"{label}: {first['msg']}"


class SettingsPanel(Vertical):
    """The Settings page."""

    DEFAULT_CSS = """
    #settings-header {
        height: 3;
        margin-bottom: 1;
    }
    #settings-brand {
        width: 1fr;
        height: 3;
    }
    SettingsPanel .settings-card {
        height: auto;
        background: $surface;
        border: round $border;
        border-title-color: $primary;
        border-title-style: bold;
        padding: 0 1;
        margin-bottom: 1;
    }
    SettingsPanel .settings-card:focus-within {
        border: round $primary;
    }
    SettingsPanel .settings-grid {
        grid-size: 2;
        grid-gutter: 0 2;
        grid-rows: auto;
        height: auto;
        margin-bottom: 1;
    }
    SettingsPanel .setting {
        height: auto;
    }
    SettingsPanel .setting.-wide {
        column-span: 2;
    }
    SettingsPanel .setting-label {
        color: $text-muted;
        text-style: bold;
        margin-top: 1;
    }
    SettingsPanel .setting-row {
        height: auto;
    }
    SettingsPanel .setting-row Input {
        width: 1fr;
    }
    SettingsPanel Checkbox {
        margin-top: 1;
        border: none;
        padding: 0;
        background: transparent;
    }
    SettingsPanel Checkbox > .toggle--button {
        color: $border;
        background: $boost;
    }
    SettingsPanel Checkbox.-on > .toggle--button {
        color: $success;
        background: $boost;
    }
    #settings-bar {
        height: auto;
        margin-bottom: 1;
    }
    #settings-status {
        width: 1fr;
        padding: 1 2;
    }
    SettingsPanel .upkeep-row {
        height: auto;
    }
    SettingsPanel .upkeep-text {
        width: 1fr;
        padding-top: 1;
    }
    SettingsPanel .upkeep-row Button {
        min-width: 16;
    }
    #upkeep-about {
        margin: 1 0;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._saved: dict[str, Optional[str]] = {}

    # --- layout -------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Horizontal(id="settings-header"):
            yield Static(self._brand(), id="settings-brand")
        for title, card_id, fields in CARDS:
            with Vertical(id=card_id, classes="settings-card") as card:
                card.border_title = title
                with Grid(classes="settings-grid"):
                    for field in fields:
                        yield self._field(field)
        with Horizontal(id="settings-bar"):
            yield Button("Save changes", id="btn-save-settings", variant="success")
            yield Button("Discard", id="btn-discard-settings")
            yield Static("", id="settings-status")
        with Vertical(id="settings-upkeep", classes="settings-card") as upkeep:
            upkeep.border_title = "MAINTENANCE"
            yield Static("", id="upkeep-about")
            yield from self._upkeep_row("upkeep-ffmpeg", None)
            yield from self._upkeep_row("upkeep-data", ("Open folder", "btn-open-data"))
            yield from self._upkeep_row(
                "upkeep-cache", ("Clear cache", "btn-clear-cache")
            )
            yield from self._upkeep_row(
                "upkeep-backups", (f"Remove {KEEP_DAYS}+ days", "btn-clean-backups")
            )
            yield from self._upkeep_row(
                "upkeep-undo", (f"Remove {KEEP_DAYS}+ days", "btn-clean-undo")
            )
            yield from self._upkeep_row(
                "upkeep-file", ("Reset settings", "btn-reset-settings")
            )

    @staticmethod
    def _brand() -> Content:
        return Content.assemble(
            ("◢◤ ", "bold $secondary"),
            ("SETTINGS", "bold $primary"),
            (" // DEFAULTS AND UPKEEP\n", "bold"),
            (
                "Saved to ~/.max_config.env  ·  the CLI uses the same settings",
                "$text-muted",
            ),
        )

    def _field(self, field: SettingField) -> Vertical:
        widget_id = f"set-{field.name}"
        classes = "setting -wide" if field.wide else "setting"
        if field.kind == "bool":
            box = Checkbox(field.label, id=widget_id)
            box.tooltip = field.help
            return Vertical(box, classes=classes)
        label = Label(field.label.upper(), classes="setting-label")
        if field.kind == "choice":
            control: Any = Select(list(field.choices), allow_blank=False, id=widget_id)
        elif field.kind in ("secret", "path"):
            text_input = Input(
                id=widget_id, password=field.kind == "secret", placeholder=field.help
            )
            button = (
                Button(SECRET_HIDDEN_LABEL, id=f"reveal-{field.name}")
                if field.kind == "secret"
                else Button("Change...", id=f"browse-{field.name}")
            )
            control = Horizontal(text_input, button, classes="setting-row")
        else:
            control = Input(
                id=widget_id,
                type="integer" if field.kind == "int" else "text",
                placeholder=field.help,
            )
        holder = Vertical(label, control, classes=classes)
        holder.tooltip = field.help
        return holder

    @staticmethod
    def _upkeep_row(text_id: str, button: Optional[tuple[str, str]]) -> ComposeResult:
        with Horizontal(classes="upkeep-row"):
            yield Static("", id=text_id, classes="upkeep-text")
            if button:
                yield Button(button[0], id=button[1])

    def on_mount(self) -> None:
        self._load()
        self.run_worker(self._measure, thread=True, group="settings-upkeep")

    # --- values -------------------------------------------------------------

    def _load(self) -> None:
        """Fill every control from the running settings."""
        self._saved = {name: saved_text(name) for name in FIELDS}
        with self.app.batch_update():
            for name, text in self._saved.items():
                self._set_control(name, text)
        self._sync_dirty()

    def _set_control(self, name: str, text: Optional[str]) -> None:
        widget = self.query_one(f"#set-{name}")
        if isinstance(widget, Checkbox):
            widget.value = text == "true"
        elif isinstance(widget, Select):
            widget.value = (
                text if text in dict(FIELDS[name].choices).values() else Select.BLANK
            )
        elif isinstance(widget, Input):
            widget.value = text or ""

    def _control_text(self, name: str) -> Optional[str]:
        widget = self.query_one(f"#set-{name}")
        if isinstance(widget, Checkbox):
            return "true" if widget.value else "false"
        if isinstance(widget, Select):
            return None if widget.is_blank() else str(widget.value)
        text = widget.value.strip() if isinstance(widget, Input) else ""
        if not text and name in OPTIONAL:
            return None
        return text

    def changes(self) -> dict[str, Optional[str]]:
        """Settings whose control differs from the saved value."""
        return {
            name: text
            for name in FIELDS
            if (text := self._control_text(name)) != self._saved.get(name)
        }

    def _sync_dirty(self) -> None:
        count = len(self.changes())
        self.query_one("#btn-save-settings", Button).disabled = count == 0
        self.query_one("#btn-discard-settings", Button).disabled = count == 0
        status = (
            Content.styled(
                f"{count} unsaved change{'s' if count != 1 else ''}", "bold $warning"
            )
            if count
            else Content.styled("Everything saved.", "$text-muted")
        )
        self.query_one("#settings-status", Static).update(status)

    @on(Input.Changed)
    @on(Checkbox.Changed)
    @on(Select.Changed)
    def _on_edit(self) -> None:
        if self._saved:
            self._sync_dirty()

    @on(Button.Pressed, "#btn-save-settings")
    def _on_save(self) -> None:
        from pydantic import ValidationError

        from max_cli.common.settings_file import update_settings_file

        changes = self.changes()
        if not changes:
            return
        try:
            checked = validate_changes(changes)
        except ValidationError as e:
            self.query_one("#settings-status", Static).update(
                markup("[bold $error]$problem[/]", problem=_error_text(e))
            )
            return
        update_settings_file(changes)
        for name in changes:
            setattr(settings, name, getattr(checked, name))
        later = sorted(APPLY_ON_RESTART & set(changes))
        self._load()
        note = " Downloads at once applies the next time max starts." if later else ""
        self.notify(
            f"Saved {len(changes)} setting{'s' if len(changes) != 1 else ''}.{note}"
        )

    @on(Button.Pressed, "#btn-discard-settings")
    def _on_discard(self) -> None:
        self._load()

    @on(Button.Pressed, "#reveal-OPENAI_API_KEY")
    def _on_reveal(self, event: Button.Pressed) -> None:
        key_input = self.query_one("#set-OPENAI_API_KEY", Input)
        key_input.password = not key_input.password
        event.button.label = (
            SECRET_HIDDEN_LABEL if key_input.password else SECRET_SHOWN_LABEL
        )

    @on(Button.Pressed, "#browse-GRAB_DEFAULT_PATH")
    def _on_browse(self) -> None:
        from max_cli.interface.tui.widgets.dialogs import PathPicker

        folder_input = self.query_one("#set-GRAB_DEFAULT_PATH", Input)
        start = (
            Path(folder_input.value).expanduser() if folder_input.value else Path.home()
        )

        def _picked(path: Optional[Path]) -> None:
            if path is not None:
                folder_input.value = str(path)

        self.app.push_screen(PathPicker(start, pick_folder=True), _picked)

    # --- maintenance ----------------------------------------------------------

    def _measure(self) -> None:
        """Runs in a thread: FFmpeg's check runs the binary, sizes walk folders."""
        from max_cli.common.cache import get_default_cache
        from max_cli.common.exceptions import ResourceNotFoundError
        from max_cli.common.ffmpeg_resolver import FFmpegResolver
        from max_cli.common.transaction_log import TransactionLog

        try:
            ffmpeg: Optional[Path] = FFmpegResolver().resolve(auto_download=False)
        except ResourceNotFoundError:
            ffmpeg = None
        data_dir = Path.home() / ".max_cli"
        cache = get_default_cache()
        backups = data_dir / "backups"
        facts = {
            "ffmpeg": ffmpeg,
            "data_size": _folder_size(data_dir),
            "cache": (cache.get_size(), cache.count()),
            "backups": (
                len(_files_in(backups, recursive=False)),
                _folder_size(backups),
            ),
            "undo": len(TransactionLog.list_groups()),
        }
        self.app.call_from_thread(self._show_upkeep, facts)

    def _show_upkeep(self, facts: dict[str, Any]) -> None:
        def line(title: str, *parts: tuple[str, str]) -> Content:
            return Content.assemble((f"{title:<13}", "bold $accent"), *parts)

        muted = "$text-muted"
        ffmpeg = facts["ffmpeg"]
        cache_size, cache_items = facts["cache"]
        backup_count, backup_size = facts["backups"]
        with self.app.batch_update():
            self.query_one("#upkeep-about", Static).update(_about())
            self.query_one("#upkeep-ffmpeg", Static).update(
                line("FFMPEG", ("✓ found  ", "bold $success"), (str(ffmpeg), muted))
                if ffmpeg
                else line(
                    "FFMPEG",
                    ("! not found  ", "bold $warning"),
                    (
                        "Max offers to download it the first time a video tool needs it.",
                        muted,
                    ),
                )
            )
            self.query_one("#upkeep-data", Static).update(
                line(
                    "DATA",
                    (format_size(facts["data_size"]), "bold"),
                    (f"  in {Path.home() / '.max_cli'}", muted),
                )
            )
            self.query_one("#upkeep-cache", Static).update(
                line(
                    "CACHE",
                    (format_size(cache_size), "bold"),
                    (
                        f"  ·  {cache_items} saved answers (AI replies, link checks)",
                        muted,
                    ),
                )
            )
            self.query_one("#upkeep-backups", Static).update(
                line(
                    "UNDO BACKUPS",
                    (format_size(backup_size), "bold"),
                    (f"  ·  {backup_count} files kept so deletes can be undone", muted),
                )
            )
            self.query_one("#upkeep-undo", Static).update(
                line(
                    "UNDO LOG",
                    (f"{facts['undo']} groups", "bold"),
                    ("  ·  what `max files undo` can reverse", muted),
                )
            )
            self.query_one("#upkeep-file", Static).update(self._settings_line(line))

    @staticmethod
    def _settings_line(line: Callable[..., Content]) -> Content:
        """How many settings are saved, and any a local .env overrides."""
        from max_cli.common.settings_file import read_settings_file

        muted = "$text-muted"
        saved = len(read_settings_file())
        # Settings loads ./.env after ~/.max_config.env, so the .env wins.
        shadowed = sorted(set(read_settings_file(Path(LOCAL_ENV_FILE))) & set(FIELDS))
        if shadowed:
            return line(
                "SETTINGS",
                (f"{saved} saved  ", "bold"),
                ("! ", "bold $warning"),
                (
                    f"{LOCAL_ENV_FILE} in this folder sets {', '.join(shadowed)}"
                    " and wins over this page",
                    "$warning",
                ),
            )
        return line(
            "SETTINGS",
            (f"{saved} saved", "bold"),
            ("  ·  Reset removes ~/.max_config.env; defaults apply", muted),
        )

    def _confirm(self, question: str, action: Callable[[], str]) -> None:
        """Ask, then run `action` and show the sentence it returns."""
        from max_cli.interface.tui.widgets.dialogs import ConfirmDialog

        def _answered(confirmed: Optional[bool]) -> None:
            if confirmed:
                self.notify(action())
                self.run_worker(self._measure, thread=True, group="settings-upkeep")

        self.app.push_screen(ConfirmDialog(question), _answered)

    @on(Button.Pressed, "#btn-open-data")
    def _on_open_data(self) -> None:
        from max_cli.common.utils import open_in_file_manager

        open_in_file_manager(Path.home() / ".max_cli")

    @on(Button.Pressed, "#btn-clear-cache")
    def _on_clear_cache(self) -> None:
        def clear() -> str:
            from max_cli.common.cache import get_default_cache

            count = get_default_cache().clear()
            return f"Cleared {count} cached answers."

        self._confirm(
            "Clear the cache? AI answers and link checks are fetched again next time.",
            clear,
        )

    @on(Button.Pressed, "#btn-clean-backups")
    def _on_clean_backups(self) -> None:
        def clean() -> str:
            from max_cli.core.engines.file_organizer import FileOrganizer

            count = FileOrganizer().cleanup_old_backups(days=KEEP_DAYS)
            return f"Removed {count} backups older than {KEEP_DAYS} days."

        self._confirm(
            f"Remove undo backups older than {KEEP_DAYS} days? Deletes from before "
            "then can't be undone any more.",
            clean,
        )

    @on(Button.Pressed, "#btn-clean-undo")
    def _on_clean_undo(self) -> None:
        def clean() -> str:
            from max_cli.common.transaction_log import TransactionLog

            count = TransactionLog.cleanup_all(days=KEEP_DAYS)
            return f"Removed {count} undo groups older than {KEEP_DAYS} days."

        self._confirm(
            f"Remove undo records older than {KEEP_DAYS} days? `max files undo` "
            "can't reverse those changes any more.",
            clean,
        )

    @on(Button.Pressed, "#btn-reset-settings")
    def _on_reset(self) -> None:
        def reset() -> str:
            from max_cli.common.settings_file import settings_file_path

            path = settings_file_path()
            if path.exists():
                path.unlink()
            fresh = Settings()
            for name in Settings.model_fields:
                setattr(settings, name, getattr(fresh, name))
            self._load()
            return "Settings reset to the defaults."

        self._confirm(
            "Reset every setting to its default? This removes ~/.max_config.env, "
            "including your API key.",
            reset,
        )


def _about() -> Content:
    from importlib.metadata import PackageNotFoundError, version

    try:
        max_version = version("max-cli")
    except PackageNotFoundError:
        max_version = "unknown"
    python = ".".join(str(part) for part in sys.version_info[:3])
    return Content.assemble(
        ("MAX CLI ", "bold $primary"),
        (max_version, "bold"),
        (f"  ·  Python {python}", "$text-muted"),
        (
            f"  ·  {platform.system()} {platform.release()} ({platform.machine()})",
            "$text-muted",
        ),
    )


def _files_in(folder: Path, recursive: bool = True) -> list[Path]:
    """The files under `folder`, skipping any that vanish during the walk.

    The task store saves by writing a temporary file and renaming it, so a
    file listed a moment ago can be gone when it's looked at. That crashed
    this page's worker on a Windows CI run.
    """
    if not folder.is_dir():
        return []
    found: list[Path] = []
    try:
        for path in folder.rglob("*") if recursive else folder.iterdir():
            try:
                if path.is_file():
                    found.append(path)
            except OSError:
                continue
    except OSError:
        pass  # a whole folder went away mid-walk; what was found so far stands
    return found


def _folder_size(folder: Path) -> int:
    total = 0
    for path in _files_in(folder):
        try:
            total += path.stat().st_size
        except OSError:
            continue  # removed since the walk listed it
    return total
