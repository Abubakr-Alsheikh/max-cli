"""The Activity page's History tab: every action the dashboard ran.

A page of rows (HISTORY_PAGE_ROWS) with a kind filter, "Failed only" and a
search box, never an inner scroll area (the max-tui-design rule). The line
under the table shows the highlighted entry in full.
"""

from typing import Any, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.widgets import Button, Checkbox, DataTable, Input, Select, Static

from max_cli.interface.tui.activity_log import ActivityEntry, ActivityLog
from max_cli.interface.tui.tables import Row, show_rows
from max_cli.interface.tui.text import relative_time

HISTORY_PAGE_ROWS = 10
HISTORY_LIMIT = 500
# (label, category) for the kind filter; categories are command groups.
KINDS = (
    ("Everything", "all"),
    ("Downloads", "download"),
    ("Video", "video"),
    ("Audio", "audio"),
    ("Images", "images"),
    ("PDF", "pdf"),
    ("Files", "files"),
    ("AI", "ai"),
    ("Extras", "tools"),
)
KIND_LABELS = {category: label for label, category in KINDS}
WHAT_WIDTH = 22
KIND_WIDTH = 10
WHEN_WIDTH = 10
TOOK_WIDTH = 7
DETAIL_MIN_WIDTH = 20
TABLE_CHROME = 16  # state column, cell padding, card border and padding
MS_PER_SECOND = 1000
DETAIL_KEYS = ("message", "error", "output_files", "url", "target", "prompt")


def _summary(entry: ActivityEntry) -> str:
    """One line about what an entry did: its message, error or input."""
    details = entry.details or {}
    for key in ("message", "error"):
        if details.get(key):
            return str(details[key])
    args = details.get("args") or {}
    for key in ("target", "url", "targets", "inputs", "folder", "path"):
        if args.get(key):
            return str(args[key])
    return str(details.get("prompt") or details.get("url") or "")


def _took(entry: ActivityEntry) -> str:
    if entry.duration_ms <= 0:
        return ""
    seconds = entry.duration_ms / MS_PER_SECOND
    return f"{seconds:.1f}s" if seconds < 60 else f"{seconds / 60:.0f}m"


def _clip(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


class HistoryPanel(Vertical):
    """Everything the dashboard ran, newest first, a page at a time."""

    DEFAULT_CSS = """
    HistoryPanel {
        height: auto;
    }
    #history-bar {
        height: auto;
    }
    #history-kind {
        width: 18;
    }
    #history-search {
        width: 1fr;
    }
    #history-failed {
        margin: 0 1;
        border: none;
        padding: 1 0 0 0;
        background: $surface;
    }
    #history-page {
        width: auto;
        min-width: 10;
        padding: 1 1 0 1;
        text-align: center;
    }
    #history-table {
        height: auto;
        min-height: 0;
        border: none;
        margin-top: 1;
    }
    #history-empty {
        color: $text-muted;
        padding: 1 0;
    }
    #history-detail {
        height: auto;
        margin-top: 1;
    }
    #history-actions {
        height: auto;
        margin-top: 1;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._page = 0
        self._shown: list[ActivityEntry] = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="history-bar"):
            yield Select(KINDS, value="all", allow_blank=False, id="history-kind")
            yield Input(placeholder="Search what, file or message", id="history-search")
            yield Checkbox("Failed only", id="history-failed")
            yield Button("< Prev", id="history-prev")
            yield Static("", id="history-page")
            yield Button("Next >", id="history-next")
        yield DataTable(id="history-table", cursor_type="row")
        yield Static("", id="history-empty")
        yield Static("", id="history-detail")
        with Horizontal(id="history-actions"):
            yield Button("Clear history", id="history-clear", variant="error")

    def on_mount(self) -> None:
        table = self.query_one("#history-table", DataTable)
        table.add_column("", key="state", width=1)
        table.add_column("What", key="what", width=WHAT_WIDTH)
        table.add_column("Kind", key="kind", width=KIND_WIDTH)
        table.add_column("Details", key="details", width=DETAIL_MIN_WIDTH)
        table.add_column("When", key="when", width=WHEN_WIDTH)
        table.add_column("Took", key="took", width=TOOK_WIDTH)
        self.refresh_data()

    def on_show(self) -> None:
        self.refresh_data()

    # --- data -----------------------------------------------------------------

    def _entries(self) -> list[ActivityEntry]:
        kind_select = self.query_one("#history-kind", Select)
        kind = "all" if kind_select.is_blank() else str(kind_select.value)
        failed_only = self.query_one("#history-failed", Checkbox).value
        entries = ActivityLog().get_entries(
            limit=HISTORY_LIMIT,
            category_filter=None if kind == "all" else kind,
            status_filter="failed" if failed_only else None,
        )
        needle = self.query_one("#history-search", Input).value.strip().casefold()
        if needle:
            entries = [
                entry
                for entry in entries
                if needle in entry.action.casefold()
                or needle in _summary(entry).casefold()
                or needle in str(entry.details).casefold()
            ]
        return entries

    def _details_width(self) -> int:
        fixed = WHAT_WIDTH + KIND_WIDTH + WHEN_WIDTH + TOOK_WIDTH + TABLE_CHROME
        return max(DETAIL_MIN_WIDTH, self.size.width - fixed)

    def refresh_data(self) -> None:
        """Show the current page. The app calls this every 2 seconds; the
        table refills only when its rows changed (tables.show_rows)."""
        entries = self._entries()
        pages = max(1, -(-len(entries) // HISTORY_PAGE_ROWS))
        self._page = min(self._page, pages - 1)
        start = self._page * HISTORY_PAGE_ROWS
        self._shown = entries[start : start + HISTORY_PAGE_ROWS]
        width = self._details_width()
        table = self.query_one("#history-table", DataTable)
        rows = [
            Row(
                (
                    Content.styled("✓", "$success")
                    if entry.status == "success"
                    else Content.styled("✗", "$error")
                    if entry.status == "failed"
                    else Content.styled("·", "$warning"),
                    Content(_clip(entry.action.replace("_", " "), WHAT_WIDTH)),
                    KIND_LABELS.get(entry.category, entry.category),
                    Content(_clip(_summary(entry), width)),
                    relative_time(entry.timestamp),
                    _took(entry),
                ),
                key=entry.id,
            )
            for entry in self._shown
        ]
        with self.app.batch_update():
            table.columns["details"].width = width
            show_rows(table, rows)
            table.display = bool(rows)
            empty = self.query_one("#history-empty", Static)
            empty.display = not rows
            if not rows:
                empty.update(
                    "Nothing matches. Clear the search or pick Everything."
                    if self._filtered()
                    else "Nothing yet. Actions you run on any page show up here."
                )
            self.query_one("#history-page", Static).update(
                f"{self._page + 1} of {pages}"
            )
            self.query_one("#history-prev", Button).disabled = self._page == 0
            self.query_one("#history-next", Button).disabled = self._page >= pages - 1
            self.query_one("#history-clear", Button).disabled = (
                not entries and not self._filtered()
            )
            self._show_detail()

    def _filtered(self) -> bool:
        kind = self.query_one("#history-kind", Select)
        return (
            bool(self.query_one("#history-search", Input).value.strip())
            or self.query_one("#history-failed", Checkbox).value
            or (not kind.is_blank() and kind.value != "all")
        )

    # --- the highlighted entry ------------------------------------------------

    def _selected(self) -> Optional[ActivityEntry]:
        table = self.query_one("#history-table", DataTable)
        if not self._shown or table.cursor_row < 0:
            return None
        return self._shown[min(table.cursor_row, len(self._shown) - 1)]

    def _show_detail(self) -> None:
        entry = self._selected()
        detail = self.query_one("#history-detail", Static)
        if entry is None:
            detail.update("")
            return
        details = entry.details or {}
        lines = [
            Content.assemble(
                (entry.action.replace("_", " "), "bold $primary"),
                (f"  ·  {KIND_LABELS.get(entry.category, entry.category)}", ""),
                (f"  ·  {entry.timestamp[:19].replace('T', ' ')}", "$text-muted"),
            )
        ]
        for key in DETAIL_KEYS:
            value = details.get(key)
            if not value:
                continue
            if isinstance(value, list):
                value = ", ".join(str(item) for item in value)
            style = "$error" if key == "error" else ""
            lines.append(
                Content.assemble(
                    (f"{key.replace('_', ' ')}: ", "$text-muted"), (str(value), style)
                )
            )
        args = details.get("args") or {}
        if args:
            shown = ", ".join(
                f"{name}={value}" for name, value in args.items() if value
            )
            lines.append(Content.assemble(("options: ", "$text-muted"), (shown, "")))
        detail.update(Content("\n").join(lines))

    @on(DataTable.RowHighlighted, "#history-table")
    def _on_highlight(self) -> None:
        self._show_detail()

    # --- controls ---------------------------------------------------------------

    @on(Select.Changed, "#history-kind")
    @on(Input.Changed, "#history-search")
    @on(Checkbox.Changed, "#history-failed")
    def _on_filter(self) -> None:
        self._page = 0
        self.refresh_data()

    @on(Button.Pressed, "#history-prev, #history-next")
    def _on_page(self, event: Button.Pressed) -> None:
        step = 1 if event.button.id == "history-next" else -1
        self._page = max(0, self._page + step)
        self.refresh_data()

    @on(Button.Pressed, "#history-clear")
    def _on_clear(self) -> None:
        from max_cli.interface.tui.widgets.dialogs import ConfirmDialog

        def _answered(yes: Optional[bool]) -> None:
            if not yes:
                return
            count = ActivityLog().clear()
            self._page = 0
            self.refresh_data()
            self.notify(f"Cleared {count} entries.")

        self.app.push_screen(
            ConfirmDialog(
                "Clear the whole activity history? Your files stay as they are."
            ),
            _answered,
        )
