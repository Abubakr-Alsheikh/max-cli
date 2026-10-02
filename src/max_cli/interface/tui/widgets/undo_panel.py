"""The Activity page's Undo tab: the file changes Max recorded, and Undo.

Organize, order, smart-sort and duplicates --delete record what they move,
rename or delete (`common/transaction_log.py`). Undo reverses the newest
change not undone yet; pressing it again steps further back, like an
editor's undo.
"""

from pathlib import Path
from typing import Any, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.widgets import Button, DataTable, Static

from max_cli.interface.tui.tables import Row, show_rows
from max_cli.interface.tui.text import relative_time
from max_cli.interface.tui.workers import show_from_worker

UNDO_ROWS = 12
WHAT_WIDTH = 28
CHANGES_WIDTH = 10
WHEN_WIDTH = 10
STATE_WIDTH = 12


def _changes(count: int) -> str:
    return f"{count} change{'s' if count != 1 else ''}"


def _what(group: dict[str, Any]) -> str:
    """ "files order  ·  Report": the command and the folder it changed."""
    folder = Path(group["folder"]).name if group.get("folder") else ""
    return f"{group['command']}  ·  {folder}" if folder else group["command"]


class UndoPanel(Vertical):
    """Recorded file changes, newest first, with Undo for the next one."""

    DEFAULT_CSS = """
    UndoPanel {
        height: auto;
    }
    #undo-next {
        height: auto;
        margin-bottom: 1;
    }
    #undo-table {
        height: auto;
        min-height: 0;
        border: none;
    }
    #undo-empty {
        color: $text-muted;
        padding: 1 0;
    }
    #undo-actions {
        height: auto;
        margin-top: 1;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._next: Optional[dict[str, Any]] = None

    def compose(self) -> ComposeResult:
        yield Static("", id="undo-next")
        yield DataTable(id="undo-table", cursor_type="row")
        yield Static(
            "Nothing to undo yet. Max records what organize, order, smart-sort "
            "and duplicates --delete move, rename or delete.",
            id="undo-empty",
        )
        with Horizontal(id="undo-actions"):
            yield Button("Undo", id="undo-run", variant="warning")

    def on_mount(self) -> None:
        table = self.query_one("#undo-table", DataTable)
        table.add_column("What", width=WHAT_WIDTH)
        table.add_column("Changes", width=CHANGES_WIDTH)
        table.add_column("When", width=WHEN_WIDTH)
        table.add_column("State", width=STATE_WIDTH)
        self.refresh_data()

    def on_show(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        from max_cli.common.transaction_log import TransactionLog

        groups = TransactionLog.list_groups()[:UNDO_ROWS]
        self._next = next(
            (group for group in groups if group["undo_status"] != "undone"), None
        )
        rows = [
            Row(
                (
                    Content(_what(group)),
                    _changes(group["operation_count"]),
                    relative_time(group["timestamp"]),
                    Content.styled("undone", "$text-muted")
                    if group["undo_status"] == "undone"
                    else Content.styled("next to undo", "bold $warning")
                    if group is self._next
                    else Content.styled("can undo", "$primary"),
                ),
                key=group["group_id"],
            )
            for group in groups
        ]
        table = self.query_one("#undo-table", DataTable)
        with self.app.batch_update():
            show_rows(table, rows)
            table.display = bool(rows)
            self.query_one("#undo-empty").display = not rows
            button = self.query_one("#undo-run", Button)
            button.disabled = self._next is None
            if self._next is not None:
                button.label = f"Undo {self._next['command']}"
                text = Content.assemble(
                    ("Undo puts back ", "$text-muted"),
                    (_what(self._next), "bold $primary"),
                    (
                        f"  ·  {_changes(self._next['operation_count'])}"
                        f"  ·  {relative_time(self._next['timestamp'])}",
                        "",
                    ),
                    ("\nPress it again to step further back.", "$text-muted"),
                )
            else:
                button.label = "Undo"
                text = Content.styled(
                    "Everything recorded is undone." if rows else "", "$text-muted"
                )
            self.query_one("#undo-next", Static).update(text)

    @on(Button.Pressed, "#undo-run")
    def _on_undo(self) -> None:
        from max_cli.interface.tui.widgets.dialogs import ConfirmDialog

        group = self._next
        if group is None:
            return

        def _answered(yes: Optional[bool]) -> None:
            if not yes:
                return
            self.query_one("#undo-run", Button).disabled = True
            self.run_worker(self._undo_in_thread, thread=True, group="undo")

        self.app.push_screen(
            ConfirmDialog(
                f"Put back the {_changes(group['operation_count'])} that "
                f"{_what(group)} made? Files go back to where they were."
            ),
            _answered,
        )

    def _undo_in_thread(self) -> None:
        from max_cli.common.exceptions import MaxError
        from max_cli.core.operations import files

        try:
            result = files.undo()
        except MaxError as e:
            show_from_worker(self, self._undone, False, str(e))
            return
        show_from_worker(self, self._undone, True, result.message)

    def _undone(self, ok: bool, message: str) -> None:
        self.notify(message, severity="information" if ok else "error")
        self.refresh_data()
