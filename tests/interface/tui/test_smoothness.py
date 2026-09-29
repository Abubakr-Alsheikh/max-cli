"""Dashboard smoothness fixes (PLANS/active/dashboard-design-system.md, R0)."""

import pytest
from textual.app import App, ComposeResult
from textual.color import Color
from textual.widgets import DataTable

from max_cli.interface.tui.tables import Row, show_rows


class TableApp(App):
    def compose(self) -> ComposeResult:
        yield DataTable()


def _rows(count: int) -> list[Row]:
    return [Row((f"item {n}", str(n)), key=str(n)) for n in range(count)]


@pytest.mark.asyncio
async def test_unchanged_rows_are_not_redrawn():
    app = TableApp()
    async with app.run_test() as pilot:
        table = app.query_one(DataTable)
        table.add_columns("Name", "Number")

        assert show_rows(table, _rows(5)) is True
        await pilot.pause()
        assert show_rows(table, _rows(5)) is False


@pytest.mark.asyncio
async def test_a_refill_keeps_the_cursor_where_it_was():
    """Queue and History jumped back to the top every 2 seconds."""
    app = TableApp()
    async with app.run_test(size=(60, 10)) as pilot:
        table = app.query_one(DataTable)
        table.add_columns("Name", "Number")
        show_rows(table, _rows(30))
        table.move_cursor(row=20)
        await pilot.pause()

        show_rows(table, _rows(31))
        await pilot.pause()

        assert table.cursor_coordinate.row == 20
        assert table.row_count == 31


@pytest.mark.asyncio
async def test_screen_background_matches_the_pages():
    """The default near-black Screen showed through as black blocks on scroll."""
    from max_cli.interface.tui.app import MaxDashboardApp

    app = MaxDashboardApp()
    async with app.run_test(size=(100, 30)):
        panel = Color.parse(app.theme_variables["panel"])
        assert app.screen.styles.background == panel
