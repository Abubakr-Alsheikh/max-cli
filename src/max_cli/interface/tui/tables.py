"""Refill a DataTable without flicker.

Pages that refresh on a timer used to clear and refill their tables every
2 seconds. Each refill repainted the whole table and snapped the cursor and
the scroll back to the top. `show_rows` skips the refill when the rows are
unchanged, and keeps the cursor and scroll position when they did change.
"""

from typing import Any, NamedTuple, Optional
from weakref import WeakKeyDictionary

from textual.widgets import DataTable


class Row(NamedTuple):
    cells: tuple[Any, ...]
    key: Optional[str] = None


# What each table shows now, compared by the cells' text.
_shown: "WeakKeyDictionary[DataTable[Any], list[tuple[str, ...]]]" = WeakKeyDictionary()


def show_rows(table: "DataTable[Any]", rows: list[Row]) -> bool:
    """Show `rows` in `table`. Returns False when nothing changed."""
    signature = [tuple(str(cell) for cell in row.cells) for row in rows]
    if _shown.get(table) == signature:
        return False
    cursor_row = table.cursor_coordinate.row
    cursor_column = table.cursor_coordinate.column
    scroll_x, scroll_y = table.scroll_x, table.scroll_y
    with table.app.batch_update():
        table.clear()
        for row in rows:
            table.add_row(*row.cells, key=row.key)
        if rows:
            table.move_cursor(
                row=min(cursor_row, len(rows) - 1),
                column=cursor_column,
                animate=False,
                scroll=False,
            )
        table.scroll_to(scroll_x, scroll_y, animate=False)
    _shown[table] = signature
    return True
