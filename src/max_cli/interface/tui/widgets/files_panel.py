"""File browser panel with directory navigation and quick actions."""

from datetime import datetime
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Label, Select, Static


class FilesPanel(Vertical):
    """File browser with navigation and quick actions."""

    FILE_ICONS: dict[str, str] = {
        "video": "\U0001f3ac",
        "image": "\U0001f5bc",
        "pdf": "\U0001f4c4",
        "audio": "\U0001f3b5",
        "text": "\U0001f4dd",
        "archive": "\U0001f4e6",
        "dir": "\U0001f4c1",
        "other": "\U0001f4ce",
    }

    VIDEO_EXTS: set[str] = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"}
    IMAGE_EXTS: set[str] = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}
    PDF_EXTS: set[str] = {".pdf"}
    AUDIO_EXTS: set[str] = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"}
    TEXT_EXTS: set[str] = {
        ".txt",
        ".md",
        ".csv",
        ".json",
        ".yaml",
        ".yml",
        ".xml",
        ".log",
    }
    ARCHIVE_EXTS: set[str] = {".zip", ".tar", ".gz", ".rar", ".7z"}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._current_path: Path = Path.home()

    def compose(self) -> ComposeResult:
        yield Static("[bold cyan]File Browser[/bold cyan]", id="files-title")
        yield Static("", id="files-breadcrumb")
        with Horizontal(id="files-nav"):
            yield Button("\u2b06 Up", id="btn-up", variant="default")
            yield Button("\U0001f3e0 Home", id="btn-home", variant="default")
            yield Button("\U0001f4c2 Browse", id="btn-browse", variant="default")
        yield DataTable(id="files-table")
        yield Static("[bold]Quick Actions[/bold]", id="actions-title")
        with Horizontal(id="files-actions"):
            yield Button("Compress", id="btn-compress", variant="default")
            yield Button("Organize", id="btn-organize", variant="default")
            yield Button("Duplicates", id="btn-duplicates", variant="default")
            yield Button("Backup", id="btn-backup", variant="default")
            yield Button("Preview", id="btn-preview", variant="default")
        with Horizontal(id="files-footer"):
            yield Label("Filter:", id="filter-label")
            yield Input(placeholder="Filter files...", id="files-filter")
            yield Label("Sort:", id="sort-label")
            yield Select(
                [
                    ("Name", "name"),
                    ("Size", "size"),
                    ("Type", "type"),
                    ("Date", "date"),
                ],
                value="name",
                id="files-sort",
                allow_blank=False,
            )
            yield Label("", id="files-count")

    def on_mount(self) -> None:
        self._navigate(self._current_path)

    def _navigate(self, path: Path) -> None:
        self._current_path = path
        self._update_breadcrumb()
        self._load_directory()

    def _update_breadcrumb(self) -> None:
        breadcrumb = self.query_one("#files-breadcrumb", Static)
        parts = self._current_path.parts
        display = " > ".join(parts[-3:]) if len(parts) > 3 else str(self._current_path)
        breadcrumb.update(f"[bold]{display}[/bold]")

    def _load_directory(self, sort_by: str = "name") -> None:
        table = self.query_one("#files-table", DataTable)
        table.clear()
        if not table.columns:
            table.add_column("Name", width=35)
            table.add_column("Size", width=10)
            table.add_column("Type", width=8)
            table.add_column("Modified", width=20)
        try:
            entries = sorted(
                self._current_path.iterdir(),
                key=lambda p: (
                    not p.is_dir(),
                    p.name.lower()
                    if sort_by == "name"
                    else p.stat().st_size
                    if sort_by == "size"
                    else self._get_file_type(p)
                    if sort_by == "type"
                    else p.stat().st_mtime,
                ),
            )
        except PermissionError:
            table.add_row("[red]Permission denied[/red]", "", "", "")
            return
        for entry in entries:
            if entry.name.startswith("."):
                continue
            icon = self._get_file_icon(entry)
            name = f"{icon} {entry.name}" + ("/" if entry.is_dir() else "")
            size = self._format_size(entry) if entry.is_file() else "-"
            file_type = self._get_file_type(entry)
            modified = self._format_mtime(entry)
            table.add_row(name, size, file_type, modified, key=str(entry))
        self._update_count(len(entries))

    def _get_file_icon(self, path: Path) -> str:
        if path.is_dir():
            return self.FILE_ICONS["dir"]
        ext = path.suffix.lower()
        if ext in self.VIDEO_EXTS:
            return self.FILE_ICONS["video"]
        if ext in self.IMAGE_EXTS:
            return self.FILE_ICONS["image"]
        if ext in self.PDF_EXTS:
            return self.FILE_ICONS["pdf"]
        if ext in self.AUDIO_EXTS:
            return self.FILE_ICONS["audio"]
        if ext in self.TEXT_EXTS:
            return self.FILE_ICONS["text"]
        if ext in self.ARCHIVE_EXTS:
            return self.FILE_ICONS["archive"]
        return self.FILE_ICONS["other"]

    def _get_file_type(self, path: Path) -> str:
        if path.is_dir():
            return "dir"
        ext = path.suffix.lower()
        if ext in self.VIDEO_EXTS:
            return "video"
        if ext in self.IMAGE_EXTS:
            return "image"
        if ext in self.PDF_EXTS:
            return "pdf"
        if ext in self.AUDIO_EXTS:
            return "audio"
        if ext in self.TEXT_EXTS:
            return "text"
        return "other"

    def _format_size(self, path: Path) -> str:
        try:
            size = path.stat().st_size
            for unit in ["B", "KB", "MB", "GB"]:
                if size < 1024:
                    return f"{size:.1f}{unit}"
                size /= 1024
            return f"{size:.1f}TB"
        except OSError:
            return "-"

    def _format_mtime(self, path: Path) -> str:
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            return mtime.strftime("%Y-%m-%d %H:%M")
        except OSError:
            return "-"

    def _update_count(self, count: int) -> None:
        count_label = self.query_one("#files-count", Label)
        count_label.update(f"{count} items")

    @on(Button.Pressed, "#btn-up")
    def _on_up(self) -> None:
        if self._current_path.parent != self._current_path:
            self._navigate(self._current_path.parent)

    @on(Button.Pressed, "#btn-home")
    def _on_home(self) -> None:
        self._navigate(Path.home())

    @on(Button.Pressed, "#btn-browse")
    def _on_browse(self) -> None:
        self._navigate(Path.home())

    @on(DataTable.RowSelected, "#files-table")
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        path = Path(event.row_key.value)
        if path.is_dir():
            self._navigate(path)

    @on(Input.Changed, "#files-filter")
    def _on_filter(self, event: Input.Changed) -> None:
        filter_text = event.value.strip().lower()
        table = self.query_one("#files-table", DataTable)
        for row_key in table.rows:
            row_data = table.get_row(row_key)
            if row_data:
                name = row_data[0].lower()
                table.rows[row_key].visible = not filter_text or filter_text in name

    @on(Select.Changed, "#files-sort")
    def _on_sort(self, event: Select.Changed) -> None:
        sort_by = event.value
        if sort_by == Select.BLANK:
            return
        self._load_directory(sort_by=sort_by)

    @on(Button.Pressed, "#btn-compress")
    def _on_compress(self) -> None:
        table = self.query_one("#files-table", DataTable)
        if table.cursor_coordinate is not None:
            row_data = table.get_row_at(table.cursor_coordinate.row)
            file_path = Path(
                row_data[0]
                .replace("\U0001f4ce ", "")
                .replace("\U0001f5bc ", "")
                .replace("\U0001f3ac ", "")
                .replace("\U0001f4c4 ", "")
                .replace("\U0001f3b5 ", "")
                .replace("\U0001f4dd ", "")
                .replace("\U0001f4e6 ", "")
                .replace("\U0001f4c1 ", "")
                .rstrip("/")
            )
            full_path = self._current_path / file_path
            if full_path.is_file():
                ext = full_path.suffix.lower()
                if ext in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
                    self._execute_quick_action(
                        "images", "compress", {"target": str(full_path)}
                    )
                elif ext in {".mp4", ".mkv", ".avi", ".mov"}:
                    self._execute_quick_action(
                        "video", "compress", {"target": str(full_path)}
                    )
                else:
                    self.notify(
                        "Unsupported file type for compression", severity="warning"
                    )
            else:
                self.notify("Select a file to compress", severity="warning")
        else:
            self.notify("Select a file to compress", severity="warning")

    @on(Button.Pressed, "#btn-organize")
    def _on_organize(self) -> None:
        self._execute_quick_action(
            "files", "smart-sort", {"path": str(self._current_path)}
        )

    @on(Button.Pressed, "#btn-duplicates")
    def _on_duplicates(self) -> None:
        self._execute_quick_action(
            "files", "duplicates", {"folder": str(self._current_path)}
        )

    @on(Button.Pressed, "#btn-backup")
    def _on_backup(self) -> None:
        pass

    @on(Button.Pressed, "#btn-preview")
    def _on_preview(self) -> None:
        pass

    def _execute_quick_action(
        self, category: str, command: str, values: dict[str, str]
    ) -> None:
        from max_cli.interface.tui.command_executor import CommandExecutor

        executor = CommandExecutor()
        try:
            result = executor.execute(category=category, command=command, values=values)
            self.notify(
                f"{'Success' if result.success else 'Failed'}: {result.message}",
                severity="information" if result.success else "error",
            )
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")
