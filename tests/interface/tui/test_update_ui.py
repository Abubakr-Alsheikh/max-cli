"""The dashboard and updates: the start notice, Settings > Maintenance, and
Update closing the dashboard so `max dashboard` can install the new Max."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from textual.widgets import Button, Static

from max_cli.config import settings
from max_cli.core.engines import updates
from max_cli.interface.tui.app import UPDATE_RESULT, MaxDashboardApp
from max_cli.interface.tui.widgets.dialogs import ConfirmDialog

from .waiting import wait_until


@pytest.fixture(autouse=True)
def newer_max_out(monkeypatch):
    """A saved check says 1.2.0 is out; this Max is 1.1.0."""
    monkeypatch.setattr(settings, "UPDATE_CHECK", True)
    monkeypatch.setattr(updates, "current_version", lambda: "1.1.0")
    monkeypatch.setattr(updates, "fetch_latest", lambda: "1.2.0")
    state = Path.home() / ".max_cli" / updates.STATE_NAME
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(
        json.dumps({"latest": "1.2.0", "checked_at": datetime.now().isoformat()}),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_the_dashboard_says_a_new_max_is_out():
    app = MaxDashboardApp()
    async with app.run_test(size=(140, 50)) as pilot:
        await wait_until(pilot, lambda: app._notifications)
        messages = [notice.message for notice in app._notifications]

    assert any("Max 1.2.0 is out (you have 1.1.0)" in text for text in messages)


@pytest.mark.asyncio
async def test_no_notice_when_checks_are_off(monkeypatch):
    monkeypatch.setattr(settings, "UPDATE_CHECK", False)
    app = MaxDashboardApp()
    async with app.run_test(size=(140, 50)) as pilot:
        for _ in range(10):
            await pilot.pause(0.05)
        messages = [notice.message for notice in app._notifications]

    assert not any("is out" in text for text in messages)


@pytest.mark.asyncio
async def test_maintenance_offers_the_update_and_closes_for_it():
    app = MaxDashboardApp()
    async with app.run_test(size=(140, 50)) as pilot:
        app.navigate("settings")
        button = app.query_one("#btn-update", Button)
        await wait_until(pilot, lambda: "1.2.0" in str(button.label))
        row = str(app.query_one("#upkeep-update", Static).render())
        button.press()
        await wait_until(pilot, lambda: isinstance(app.screen, ConfirmDialog))
        app.screen.dismiss(True)
        await pilot.pause()

    assert "1.2.0 is out" in row
    assert str(button.label) == "Update to 1.2.0"
    assert app.return_value == UPDATE_RESULT


def test_max_dashboard_updates_after_the_dashboard_closes():
    from typer.testing import CliRunner

    from max_cli.interface.tui.dashboard import app as dashboard_app

    with (
        patch.object(MaxDashboardApp, "run", return_value=UPDATE_RESULT),
        patch("max_cli.interface.cli_update.update_max") as update_max,
    ):
        result = CliRunner().invoke(dashboard_app, [])

    assert result.exit_code == 0, result.output
    update_max.assert_called_once_with(assume_yes=True)
