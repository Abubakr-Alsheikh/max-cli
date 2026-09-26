"""The Tools page and the catalog-built ActionForm (command-catalog.md, build step 2)."""

from pathlib import Path
from unittest.mock import patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import (
    Button,
    Collapsible,
    Input,
    OptionList,
    Select,
    Static,
    Switch,
)

from max_cli.config import settings
from max_cli.core.catalog import get_action
from max_cli.core.catalog.spec import Action, Danger, Param, ParamKind
from max_cli.core.engines.task_manager import get_task_manager
from max_cli.core.engines.task_queue import TaskType
from max_cli.core.operations.result import ActionResult
from max_cli.interface.tui.activity_log import ActivityLog
from max_cli.interface.tui.widgets.action_form import ActionForm
from max_cli.interface.tui.widgets.dialogs import ConfirmDialog, PathPicker

RUN_ACTION = "max_cli.core.catalog.runner.run_action"


class FormApp(App):
    def __init__(self, action: Action) -> None:
        super().__init__()
        self._action = action

    def compose(self) -> ComposeResult:
        yield ActionForm(self._action)


def _status(app: App) -> str:
    return str(app.query_one("#form-status", Static).content)


async def _settle(app: App, pilot) -> None:
    # press() only posts a message; process it so the worker exists before waiting.
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


@pytest.mark.asyncio
async def test_tools_page_lists_dashboard_actions_only():
    from max_cli.interface.tui.app import MaxDashboardApp

    app = MaxDashboardApp()
    async with app.run_test(size=(120, 40)) as pilot:
        app._show_panel("tools")
        await pilot.pause()

        assert app.query_one("#tools-group", Select).value == "video"
        options = app.query_one("#tools-actions", OptionList)
        ids = [options.get_option_at_index(i).id for i in range(options.option_count)]
        assert "video.compress" in ids
        assert "video.record" not in ids
        assert "video.stream" not in ids


@pytest.mark.asyncio
async def test_form_shows_every_option_with_cli_defaults():
    action = get_action("video.gif")
    app = FormApp(action)
    async with app.run_test(size=(100, 60)):
        for param in action.params:
            assert app.query(f"#field-{param.name}")
        assert app.query_one("#field-width", Input).value == "480"
        assert app.query_one("#field-output", Input).value == ""
        # width and fps are advanced, so they fold away.
        collapsible = app.query_one(Collapsible)
        assert collapsible.collapsed
        assert app.query_one("#field-fps", Input) in collapsible.query(Input)


@pytest.mark.asyncio
async def test_choice_and_bool_fields():
    app = FormApp(get_action("video.compress"))
    async with app.run_test(size=(100, 60)):
        level = app.query_one("#field-level", Select)
        assert level.value == "balanced"
        assert app.query_one("#form-queue", Button)

    app = FormApp(get_action("video.record"))
    async with app.run_test(size=(100, 60)):
        assert app.query_one("#field-audio", Switch).value is False


@pytest.mark.asyncio
async def test_run_calls_the_operation_in_a_worker_and_logs_activity(dummy_video):
    result = ActionResult(True, "Video saved: out.mp4", [Path("out.mp4")])
    app = FormApp(get_action("video.compress"))
    with patch(RUN_ACTION, return_value=result) as run_action:
        async with app.run_test(size=(100, 60)) as pilot:
            app.query_one("#field-target", Input).value = str(dummy_video)
            app.query_one("#form-run", Button).press()
            await _settle(app, pilot)
            status = _status(app)

    values = run_action.call_args.args[1]
    assert values["target"] == str(dummy_video)
    assert values["level"] == "balanced"
    assert "Done." in status and "Video saved" in status
    [entry] = ActivityLog().get_entries()
    assert (entry.category, entry.action, entry.status) == (
        "video",
        "compress",
        "success",
    )


@pytest.mark.asyncio
async def test_missing_required_value_is_shown_and_nothing_runs():
    app = FormApp(get_action("video.compress"))
    with patch(RUN_ACTION) as run_action:
        async with app.run_test(size=(100, 60)) as pilot:
            app.query_one("#form-run", Button).press()
            await _settle(app, pilot)
            status = _status(app)

    run_action.assert_not_called()
    assert "'target' is required" in status


@pytest.mark.asyncio
async def test_failed_operation_shows_the_error(dummy_video):
    app = FormApp(get_action("video.mute"))
    with patch(RUN_ACTION, side_effect=RuntimeError("FFmpeg Error: boom")):
        async with app.run_test(size=(100, 60)) as pilot:
            app.query_one("#field-target", Input).value = str(dummy_video)
            app.query_one("#form-run", Button).press()
            await _settle(app, pilot)
            status = _status(app)
            run_disabled = app.query_one("#form-run", Button).disabled

    assert "Failed:" in status and "boom" in status
    assert not run_disabled
    assert ActivityLog().get_entries()[0].status == "failed"


@pytest.mark.asyncio
async def test_add_to_queue_creates_an_action_task(dummy_video):
    app = FormApp(get_action("video.compress"))
    async with app.run_test(size=(100, 60)) as pilot:
        app.query_one("#field-target", Input).value = str(dummy_video)
        app.query_one("#form-queue", Button).press()
        await pilot.pause()
        status = _status(app)

    [task] = get_task_manager().get_all()
    assert task.type == TaskType.ACTION
    assert task.payload["action"] == "video.compress"
    assert "Queued" in status


def _delete_everything(target: Path) -> ActionResult:
    return ActionResult(True, f"Deleted {target}")


DANGEROUS = Action(
    group="test",
    name="wipe",
    summary="Delete a file.",
    operation=f"{__name__}:_delete_everything",
    params=(Param("target", ParamKind.FILE, "File to delete."),),
    danger=Danger.DELETES,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answer, runs", [("#confirm-yes", True), ("#confirm-no", False)]
)
async def test_dangerous_actions_ask_first(tmp_path, answer, runs):
    app = FormApp(DANGEROUS)
    with patch(RUN_ACTION, return_value=ActionResult(True, "Deleted")) as run_action:
        async with app.run_test(size=(100, 40)) as pilot:
            app.query_one("#field-target", Input).value = str(tmp_path / "x.txt")
            app.query_one("#form-run", Button).press()
            await pilot.pause()
            assert isinstance(app.screen, ConfirmDialog)

            app.screen.query_one(answer, Button).press()
            await _settle(app, pilot)
            status = _status(app)

    assert run_action.called is runs
    assert ("Done." in status) is runs


@pytest.mark.asyncio
async def test_browse_fills_the_path_field(tmp_path):
    app = FormApp(get_action("video.compress"))
    picked = tmp_path / "movie.mp4"
    async with app.run_test(size=(100, 60)) as pilot:
        app.query_one("#browse-target", Button).press()
        await pilot.pause()
        assert isinstance(app.screen, PathPicker)

        app.screen.query_one("#picker-path", Input).value = str(picked)
        app.screen.query_one("#picker-ok", Button).press()
        await pilot.pause()

        assert app.query_one("#field-target", Input).value == str(picked)


@pytest.mark.asyncio
async def test_files_page_video_compress_opens_the_prefilled_form(dummy_video):
    from max_cli.interface.tui.app import MaxDashboardApp
    from max_cli.interface.tui.widgets.files_panel import FilesPanel

    app = MaxDashboardApp()
    async with app.run_test(size=(120, 40)) as pilot:
        app.query_one(FilesPanel).post_message(
            FilesPanel.OpenAction("video.compress", {"target": str(dummy_video)})
        )
        await pilot.pause()
        await pilot.pause()

        tools = app.query_one("#tools-panel")
        assert tools.display
        form = tools.query_one(ActionForm)
        assert form.action.id == "video.compress"
        assert form.query_one("#field-target", Input).value == str(dummy_video)


@pytest.mark.asyncio
async def test_files_page_image_compress_opens_the_prefilled_form(dummy_image):
    from max_cli.interface.tui.app import MaxDashboardApp
    from max_cli.interface.tui.widgets.files_panel import FilesPanel

    app = MaxDashboardApp()
    async with app.run_test(size=(120, 40)) as pilot:
        app.query_one(FilesPanel).post_message(
            FilesPanel.OpenAction("images.compress", {"target": str(dummy_image)})
        )
        await pilot.pause()
        await pilot.pause()

        form = app.query_one("#tools-panel").query_one(ActionForm)
        assert form.action.id == "images.compress"
        assert form.query_one("#field-target", Input).value == str(dummy_image)
        # A Setting default shows the user's configured value.
        quality = form.query_one("#field-quality", Input).value
        assert quality == str(settings.DEFAULT_QUALITY)
