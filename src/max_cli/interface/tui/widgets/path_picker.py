"""Browse for a file or a folder, or where to save one: the dialog behind
every Browse button in the dashboard.

- PLACES: your usual folders (Home, Desktop, Downloads ...), the drives,
  folders you pinned and folders you picked from lately.
- A path bar with Back and Up. Type or paste a path and press Enter to go.
- The folder's contents: folders first, then files with size and date. A
  filter box narrows the list; a page can show only the files it works on
  (images, PDFs, videos) with "All files" to see the rest.
- Enter opens a folder or picks a file; Backspace goes up a folder.

The dialog remembers the last folder you picked from, your recent folders
and your pins (`ui_prefs`), so the next Browse starts where you were.
"""

import os
import stat
import string
import sys
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Input,
    Label,
    OptionList,
    Static,
)
from textual.widgets.data_table import RowDoesNotExist
from textual.widgets.option_list import Option

from max_cli.common.file_kinds import AUDIO, IMAGE, KIND_SUFFIXES, PDF, VIDEO, kind_of
from max_cli.common.utils import format_size
from max_cli.interface.tui.ui_prefs import load_prefs, save_pref
from max_cli.interface.tui.workers import show_from_worker

PREF_LAST_FOLDER = "picker_last_folder"
PREF_RECENT = "picker_recent_folders"
PREF_PINNED = "picker_pinned_folders"
RECENT_LIMIT = 8
# More rows than this make the table slow to fill; the filter finds the rest.
MAX_ROWS = 1000
RECENT_DAYS = 7
SECONDS_PER_DAY = 86400
UP_KEY = ".."

# A command group -> the files its pages work on, and what to call them.
FILE_TYPES: dict[str, tuple[str, frozenset[str]]] = {
    "video": ("videos and audio", KIND_SUFFIXES[VIDEO] | KIND_SUFFIXES[AUDIO]),
    "images": ("images", KIND_SUFFIXES[IMAGE]),
    "pdf": ("PDFs", KIND_SUFFIXES[PDF]),
}
ICONS = {
    VIDEO: "\U0001f3ac",
    AUDIO: "\U0001f3b5",
    IMAGE: "\U0001f4f7",
    PDF: "\U0001f4c4",
}
FOLDER_ICON = "\U0001f4c1"
FILE_ICON = "\U0001f4ce"
# Folders under your home that most people have, in the order PLACES lists them.
KNOWN_FOLDERS = ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music")


class PickMode(str, Enum):
    FILE = "file"  # an existing file (a folder too, with "Use this folder")
    FOLDER = "folder"
    SAVE = "save"  # a folder and a file name to write


@dataclass(frozen=True)
class Entry:
    path: Path
    is_dir: bool
    size: int = 0
    modified: float = 0.0

    @property
    def name(self) -> str:
        return self.path.name


def _is_hidden(entry: "os.DirEntry[str]") -> bool:
    if entry.name.startswith("."):
        return True
    attributes = getattr(entry.stat(), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 0))


def list_folder(
    folder: Path,
    *,
    show_hidden: bool = False,
    suffixes: Optional[frozenset[str]] = None,
    folders_only: bool = False,
) -> list[Entry]:
    """A folder's contents, folders first, each part sorted by name. Raises
    OSError (PermissionError, FileNotFoundError ...) when it can't be read."""
    entries: list[Entry] = []
    with os.scandir(folder) as found:
        for item in found:
            try:
                if not show_hidden and _is_hidden(item):
                    continue
                is_dir = item.is_dir()
                if not is_dir and (
                    folders_only
                    or (
                        suffixes is not None
                        and Path(item.name).suffix.lower() not in suffixes
                    )
                ):
                    continue
                info = item.stat()
            except OSError:
                continue  # vanished, or a broken link
            entries.append(
                Entry(
                    path=Path(item.path),
                    is_dir=is_dir,
                    size=0 if is_dir else info.st_size,
                    modified=info.st_mtime,
                )
            )
    entries.sort(key=lambda entry: (not entry.is_dir, entry.name.casefold()))
    return entries


def drives() -> list[Path]:
    """The drive roots: C:\\, D:\\ ... on Windows, / elsewhere."""
    if sys.platform != "win32":
        return [Path("/")]
    return [
        Path(f"{letter}:\\")
        for letter in string.ascii_uppercase
        if Path(f"{letter}:\\").exists()
    ]


def places() -> list[tuple[str, Path]]:
    """Home, the usual folders under it that exist, and Max's download folder."""
    home = Path.home()
    found = [("Home", home)]
    found += [(name, home / name) for name in KNOWN_FOLDERS if (home / name).is_dir()]
    from max_cli.config import settings

    downloads = Path(settings.GRAB_DEFAULT_PATH).expanduser()
    if downloads.is_dir() and downloads not in {path for _name, path in found}:
        found.append(("Max downloads", downloads))
    return found


def _saved_folders(key: str) -> list[Path]:
    saved = load_prefs().get(key)
    if not isinstance(saved, list):
        return []
    return [Path(text) for text in saved if isinstance(text, str)]


def pinned_folders() -> list[Path]:
    return _saved_folders(PREF_PINNED)


def recent_folders() -> list[Path]:
    return _saved_folders(PREF_RECENT)


def set_pinned(folder: Path, pinned: bool) -> None:
    folders = [path for path in pinned_folders() if path != folder]
    if pinned:
        folders.append(folder)
    save_pref(PREF_PINNED, [str(path) for path in folders])


def remember_choice(path: Path) -> None:
    """Start the next Browse in this path's folder and list it under RECENT."""
    folder = path if path.is_dir() else path.parent
    recent = [folder] + [known for known in recent_folders() if known != folder]
    save_pref(PREF_RECENT, [str(known) for known in recent[:RECENT_LIMIT]])
    save_pref(PREF_LAST_FOLDER, str(folder))


def start_folder(start: Optional[Path]) -> Path:
    """Where Browse opens: the given path's folder, else the last folder
    picked from, else your home folder."""
    candidates = []
    if start is not None:
        start = start.expanduser()
        candidates += [start, start.parent]
    last = load_prefs().get(PREF_LAST_FOLDER)
    if isinstance(last, str):
        candidates.append(Path(last))
    return next((path for path in candidates if path.is_dir()), Path.home())


def _icon(entry: Entry) -> str:
    if entry.is_dir:
        return FOLDER_ICON
    return ICONS.get(kind_of(entry.path), FILE_ICON)


def _when(modified: float, now: datetime) -> str:
    """Today's time, "3d ago" in the last week, else the date."""
    moment = datetime.fromtimestamp(modified)
    age_days = (now - moment).total_seconds() / SECONDS_PER_DAY
    if moment.date() == now.date():
        return moment.strftime("today %H:%M")
    if 0 <= age_days < RECENT_DAYS:
        return f"{max(1, int(age_days))}d ago"
    return moment.strftime("%Y-%m-%d")


class PathPicker(ModalScreen[Optional[Path]]):
    """Browse for a path. Returns the chosen path, or None on cancel.

    `start` is where to open (a file opens its folder and highlights it).
    `file_types` is a key of FILE_TYPES: the list then shows only those files
    until you tick "All files".
    """

    DEFAULT_CSS = """
    PathPicker {
        align: center middle;
    }
    #picker-box {
        width: 92%;
        height: 92%;
        padding: 0 1;
        border: thick $accent;
        background: $panel;
    }
    #picker-header {
        height: auto;
    }
    #picker-bar {
        height: 3;
    }
    #picker-bar Button {
        min-width: 5;
        width: 5;
    }
    #picker-path {
        width: 1fr;
    }
    #picker-main {
        height: 1fr;
    }
    .picker-card {
        background: $surface;
        border: round $border;
        border-title-color: $primary;
        border-title-style: bold;
        padding: 0 1;
    }
    .picker-card:focus-within {
        border: round $primary;
    }
    #picker-places {
        width: 30;
        margin-right: 1;
    }
    #picker-places-list {
        height: 1fr;
        background: $surface;
        border: none;
        padding: 0;
    }
    #picker-files {
        width: 1fr;
    }
    #picker-filter {
        margin-bottom: 0;
    }
    #picker-table {
        height: 1fr;
        min-height: 4;
    }
    #picker-status {
        height: 1;
        color: $text-muted;
    }
    /* One line: the list keeps the height in a short terminal. */
    #picker-options {
        height: 1;
        margin: 1 0 0 1;
    }
    #picker-options Checkbox {
        height: 1;
        border: none;
        padding: 0;
        margin-right: 3;
        background: $panel;
    }
    #picker-pin {
        height: 1;
        min-width: 10;
        border: none;
        padding: 0 1;
        background: $boost;
    }
    #picker-pin:hover {
        background: $primary 30%;
    }
    #picker-selected {
        height: 1;
        margin: 0 1;
    }
    #picker-name-row {
        height: auto;
    }
    #picker-name-row Label {
        padding: 1 1 0 1;
    }
    #picker-name {
        width: 1fr;
    }
    #picker-buttons {
        height: auto;
        align-horizontal: right;
    }
    #picker-buttons Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("backspace", "up", "Up a folder", show=False),
        Binding("alt+up", "up", "Up a folder", show=False),
        Binding("alt+left", "back", "Back", show=False),
        Binding("ctrl+f", "focus_filter", "Filter", show=False),
        Binding("ctrl+l", "focus_path", "Path", show=False),
    ]

    def __init__(
        self,
        start: Optional[Path] = None,
        mode: PickMode = PickMode.FILE,
        file_types: Optional[str] = None,
    ) -> None:
        super().__init__()
        self._mode = mode
        self._file_types = (
            FILE_TYPES.get(file_types or "") if mode != PickMode.FOLDER else None
        )
        self._folder = start_folder(start)
        self._focus_name = ""  # a row to put the cursor on once the list is in
        self._save_name = ""
        if start is not None:
            start = start.expanduser()
            if start.is_file():
                self._focus_name = start.name
            elif mode == PickMode.SAVE and not start.is_dir() and start.suffix:
                self._save_name = start.name
        self._back: list[Path] = []
        self._entries: list[Entry] = []
        self._place_paths: dict[str, Path] = {}

    # --- layout ---------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-box"):
            yield Static(self._header(), id="picker-header")
            with Horizontal(id="picker-bar"):
                yield Button("<", id="picker-back", tooltip="Back (Alt+Left)")
                yield Button("^", id="picker-up", tooltip="Up a folder (Backspace)")
                yield Input(
                    value=str(self._folder),
                    placeholder="Type or paste a path, then press Enter",
                    id="picker-path",
                )
            with Horizontal(id="picker-main"):
                with Vertical(classes="picker-card", id="picker-places") as places_card:
                    places_card.border_title = "PLACES"
                    yield OptionList(id="picker-places-list")
                with Vertical(classes="picker-card", id="picker-files"):
                    yield Input(
                        placeholder="Filter this folder (Ctrl+F)", id="picker-filter"
                    )
                    yield DataTable(
                        id="picker-table", cursor_type="row", zebra_stripes=True
                    )
                    yield Static("", id="picker-status")
            with Horizontal(id="picker-options"):
                if self._file_types is not None:
                    yield Checkbox(
                        f"All files, not only {self._file_types[0]}",
                        id="picker-all",
                    )
                yield Checkbox("Hidden files", id="picker-hidden")
                yield Button("Pin this folder", id="picker-pin")
            yield Static("", id="picker-selected")
            if self._mode == PickMode.SAVE:
                with Horizontal(id="picker-name-row"):
                    yield Label("File name")
                    yield Input(value=self._save_name, id="picker-name")
            with Horizontal(id="picker-buttons"):
                if self._mode == PickMode.FILE:
                    yield Button("Use this folder", id="picker-use-folder")
                yield Button(self._ok_label(), id="picker-ok", variant="success")
                yield Button("Cancel", id="picker-cancel")

    def _header(self) -> Content:
        what = {
            PickMode.FILE: "CHOOSE A FILE",
            PickMode.FOLDER: "CHOOSE A FOLDER",
            PickMode.SAVE: "SAVE AS",
        }[self._mode]
        return Content.assemble(
            ("◢◤ ", "bold $secondary"),
            (what, "bold $primary"),
            (" // ", "bold"),
            (
                "Enter opens a folder or picks a file  ·  Backspace goes up  ·  "
                "Esc cancels",
                "$text-muted",
            ),
        )

    def _ok_label(self) -> str:
        return {
            PickMode.FILE: "Use this file",
            PickMode.FOLDER: "Use this folder",
            PickMode.SAVE: "Save here",
        }[self._mode]

    def on_mount(self) -> None:
        table = self.query_one("#picker-table", DataTable)
        table.add_columns("Name", "Size", "Modified")
        self._fill_places()
        self._open(self._folder, remember=False)
        table.focus()

    # --- places ---------------------------------------------------------------

    def _fill_places(self) -> None:
        options: list[Option] = []
        self._place_paths = {}

        def heading(title: str) -> None:
            options.append(
                Option(Content.styled(title, "bold $text-muted"), disabled=True)
            )

        def place(label: str, path: Path, icon: str = FOLDER_ICON) -> None:
            option_id = f"place-{len(self._place_paths)}"
            self._place_paths[option_id] = path
            options.append(Option(f"{icon} {label}", id=option_id))

        for label, path in places():
            place(label, path)
        pinned = [path for path in pinned_folders() if path.is_dir()]
        if pinned:
            heading("PINNED")
            for path in pinned:
                place(path.name or str(path), path, "*")
        recent = [path for path in recent_folders() if path.is_dir()]
        if recent:
            heading("RECENT")
            for path in recent:
                place(path.name or str(path), path, " ")
        heading("DRIVES")
        for root in drives():
            place(str(root), root, " ")
        places_list = self.query_one("#picker-places-list", OptionList)
        places_list.clear_options()
        places_list.add_options(options)

    @on(OptionList.OptionSelected, "#picker-places-list")
    def _on_place(self, event: OptionList.OptionSelected) -> None:
        path = self._place_paths.get(event.option.id or "")
        if path is not None:
            self._open(path)
            self.query_one("#picker-table", DataTable).focus()

    # --- the folder -----------------------------------------------------------

    def _open(self, folder: Path, remember: bool = True) -> None:
        """Show `folder`'s contents. The list is read in a thread: a network
        folder or one with thousands of files can take a while."""
        if remember and folder != self._folder:
            self._back.append(self._folder)
        self._folder = folder
        self.query_one("#picker-path", Input).value = str(folder)
        self.query_one("#picker-filter", Input).value = ""
        self.query_one("#picker-files").border_title = (
            folder.name or str(folder)
        ).upper()
        self.query_one("#picker-back", Button).disabled = not self._back
        self.query_one("#picker-up", Button).disabled = folder.parent == folder
        pinned = folder in pinned_folders()
        self.query_one("#picker-pin", Button).label = (
            "Unpin this folder" if pinned else "Pin this folder"
        )
        self._set_status(Content.styled("Reading the folder...", "$primary"))
        show_hidden = self.query_one("#picker-hidden", Checkbox).value
        suffixes = (
            None
            if self._show_all()
            else self._file_types[1]
            if self._file_types
            else None
        )
        folders_only = self._mode == PickMode.FOLDER
        self.run_worker(
            lambda: self._read(folder, show_hidden, suffixes, folders_only),
            thread=True,
            exclusive=True,
            group="picker-list",
        )

    def _show_all(self) -> bool:
        boxes = self.query("#picker-all")
        return bool(boxes) and boxes.first(Checkbox).value

    def _read(
        self,
        folder: Path,
        show_hidden: bool,
        suffixes: Optional[frozenset[str]],
        folders_only: bool,
    ) -> None:
        try:
            entries = list_folder(
                folder,
                show_hidden=show_hidden,
                suffixes=suffixes,
                folders_only=folders_only,
            )
        except OSError as e:
            show_from_worker(self, self._show_error, folder, e)
            return
        show_from_worker(self, self._show_entries, folder, entries)

    def _show_error(self, folder: Path, error: OSError) -> None:
        if folder != self._folder:
            return
        self._entries = []
        self._fill_table()
        reason = (
            "You don't have permission to open this folder."
            if isinstance(error, PermissionError)
            else f"Can't open this folder: {error.strerror or error}"
        )
        self._set_status(Content.styled(reason, "$error"))

    def _show_entries(self, folder: Path, entries: list[Entry]) -> None:
        if folder != self._folder:
            return  # an older folder's list came in late
        self._entries = entries
        self._fill_table()

    def _fill_table(self) -> None:
        table = self.query_one("#picker-table", DataTable)
        text = self.query_one("#picker-filter", Input).value.strip().casefold()
        matching = [entry for entry in self._entries if text in entry.name.casefold()]
        now = datetime.now()
        with self.app.batch_update():
            table.clear()
            if self._folder.parent != self._folder:
                table.add_row(Text(f"{FOLDER_ICON} .."), "", "", key=UP_KEY)
            for entry in matching[:MAX_ROWS]:
                table.add_row(
                    # Text, not str: a str cell is read as markup, and
                    # Content cells measured two columns wide.
                    Text(f"{_icon(entry)} {entry.name}"),
                    "" if entry.is_dir else format_size(entry.size),
                    _when(entry.modified, now) if entry.modified else "",
                    key=str(entry.path),
                )
            focus_row = self._row_of(self._focus_name)
            if focus_row is not None:
                table.move_cursor(row=focus_row, animate=False)
                self._focus_name = ""
            elif matching and table.row_count > 1:
                table.move_cursor(row=1, animate=False)  # past ".."
        self._set_status(self._summary(matching, text))
        self._show_selected()

    def _row_of(self, name: str) -> Optional[int]:
        if not name:
            return None
        table = self.query_one("#picker-table", DataTable)
        try:
            return table.get_row_index(str(self._folder / name))
        except RowDoesNotExist:
            return None

    def _summary(self, shown: list[Entry], filter_text: str) -> Content:
        folders = sum(1 for entry in shown if entry.is_dir)
        files = len(shown) - folders
        parts = [f"{folders} folder{'s' if folders != 1 else ''}"]
        if self._mode != PickMode.FOLDER:
            kind = (
                self._file_types[0]
                if self._file_types and not self._show_all()
                else "files"
            )
            parts.append(f"{files} {kind if files != 1 else kind.rstrip('s')}")
        if filter_text:
            parts.append(f'matching "{filter_text}"')
        if len(shown) > MAX_ROWS:
            parts.append(f"showing the first {MAX_ROWS}; filter to find the rest")
        if not shown and not filter_text:
            return Content.styled("This folder is empty.", "$text-muted")
        return Content.styled("  ·  ".join(parts), "$text-muted")

    def _set_status(self, text: Content) -> None:
        self.query_one("#picker-status", Static).update(text)

    # --- what's highlighted -----------------------------------------------------

    def _highlighted(self) -> Optional[Path]:
        table = self.query_one("#picker-table", DataTable)
        if not table.row_count:
            return None
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        if key == UP_KEY:
            return self._folder.parent
        return Path(key) if key else None

    def _show_selected(self) -> None:
        path = self._highlighted()
        if path is None or path == self._folder.parent:
            text = Content.styled(f"In {self._folder}", "$text-muted")
        elif path.is_dir():
            text = Content.assemble(
                ("Folder  ", "$text-muted"),
                (path.name, "bold $primary"),
                ("  ·  Enter opens it", "$text-muted"),
            )
        else:
            entry = next((e for e in self._entries if e.path == path), None)
            size = format_size(entry.size) if entry else ""
            text = Content.assemble(
                ("Selected  ", "$text-muted"),
                (path.name, "bold $primary"),
                (f"  ·  {size}" if size else "", ""),
            )
        self.query_one("#picker-selected", Static).update(text)

    @on(DataTable.RowHighlighted, "#picker-table")
    def _on_highlight(self) -> None:
        self._show_selected()

    @on(DataTable.RowSelected, "#picker-table")
    def _on_row(self, event: DataTable.RowSelected) -> None:
        path = self._highlighted()
        if path is None:
            return
        if path.is_dir():
            self._open(path)
        elif self._mode == PickMode.SAVE:
            self.query_one("#picker-name", Input).value = path.name
        else:
            self._choose(path)

    # --- typing ----------------------------------------------------------------

    @on(Input.Changed, "#picker-filter")
    def _on_filter(self) -> None:
        self._fill_table()

    @on(Input.Submitted, "#picker-filter")
    def _on_filter_enter(self) -> None:
        self.query_one("#picker-table", DataTable).focus()

    @on(Input.Submitted, "#picker-path")
    def _on_path(self) -> None:
        text = self.query_one("#picker-path", Input).value.strip()
        if not text:
            return
        path = Path(text).expanduser()
        if path.is_dir():
            self._open(path)
            self.query_one("#picker-table", DataTable).focus()
        elif path.is_file() and self._mode == PickMode.FILE:
            self._choose(path)
        elif self._mode == PickMode.SAVE and path.parent.is_dir():
            self._choose(path)
        else:
            self._set_status(Content.styled(f"Not found: {path}", "$error"))

    @on(Input.Submitted, "#picker-name")
    def _on_name(self) -> None:
        self._on_ok()

    # --- options ----------------------------------------------------------------

    @on(Checkbox.Changed, "#picker-all, #picker-hidden")
    def _on_option(self) -> None:
        self._open(self._folder, remember=False)

    @on(Button.Pressed, "#picker-pin")
    def _on_pin(self) -> None:
        set_pinned(self._folder, self._folder not in pinned_folders())
        self._fill_places()
        self._open(self._folder, remember=False)

    # --- moving around -----------------------------------------------------------

    @on(Button.Pressed, "#picker-up")
    def action_up(self) -> None:
        if isinstance(self.focused, Input):
            return  # Backspace edits the text there
        if self._folder.parent != self._folder:
            self._focus_name = self._folder.name
            self._open(self._folder.parent)

    @on(Button.Pressed, "#picker-back")
    def action_back(self) -> None:
        if self._back:
            self._open(self._back.pop(), remember=False)

    def action_focus_filter(self) -> None:
        self.query_one("#picker-filter", Input).focus()

    def action_focus_path(self) -> None:
        self.query_one("#picker-path", Input).focus()

    # --- the answer --------------------------------------------------------------

    @on(Button.Pressed, "#picker-ok")
    def _on_ok(self) -> None:
        if self._mode == PickMode.FOLDER:
            self._choose(self._folder)
            return
        if self._mode == PickMode.SAVE:
            name = self.query_one("#picker-name", Input).value.strip()
            if not name:
                self._set_status(Content.styled("Type a file name first.", "$error"))
                self.query_one("#picker-name", Input).focus()
                return
            self._choose(self._folder / name)
            return
        typed = Path(self.query_one("#picker-path", Input).value.strip()).expanduser()
        highlighted = self._highlighted()
        if typed.is_file():
            self._choose(typed)
        elif highlighted is not None and highlighted.is_file():
            self._choose(highlighted)
        else:
            self._set_status(
                Content.styled(
                    "Highlight a file first, or press Use this folder.", "$warning"
                )
            )

    @on(Button.Pressed, "#picker-use-folder")
    def _on_use_folder(self) -> None:
        self._choose(self._folder)

    def _choose(self, path: Path) -> None:
        remember_choice(path)
        self.dismiss(path)

    @on(Button.Pressed, "#picker-cancel")
    def action_cancel(self) -> None:
        self.dismiss(None)
