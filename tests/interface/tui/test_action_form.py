"""The catalog-built ActionForm (command-catalog.md, build step 2): fields, run, queue, Browse."""

from pathlib import Path
from unittest.mock import patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import (
    Button,
    Collapsible,
    DataTable,
    Input,
    Select,
    Static,
    Switch,
)

from max_cli.common.activity_log import ActivityLog
from max_cli.core.catalog import actions_for, get_action, group_names
from max_cli.core.catalog.spec import Action, Danger, Param, ParamKind, Surface
from max_cli.core.engines.task_manager import get_task_manager
from max_cli.core.engines.task_queue import TaskType
from max_cli.core.operations.result import ActionResult
from max_cli.interface.tui.widgets.action_form import ActionForm
from max_cli.interface.tui.widgets.dialogs import ConfirmDialog
from max_cli.interface.tui.widgets.path_picker import PathPicker

from .waiting import wait_until

RUN_ACTION = "max_cli.core.catalog.runner.run_action"


class FormApp(App):
    def __init__(self, action: Action) -> None:
        super().__init__()
        self._action = action

    def compose(self) -> ComposeResult:
        yield ActionForm(self._action)


async def _picker_ready(pilot, app: App) -> bool:
    """The picker has listed its first folder, so typing into its path box
    isn't overwritten by that first listing. An empty status isn't enough:
    it is empty before the picker's on_mount too."""

    def listed() -> bool:
        if not isinstance(app.screen, PathPicker):
            return False
        status = str(app.screen.query_one("#picker-status", Static).content)
        table = app.screen.query_one("#picker-table", DataTable)
        return bool(status) and "Reading" not in status and table.row_count > 0

    return await wait_until(pilot, listed)


def _status(app: App) -> str:
    return str(app.query_one("#form-status", Static).content)


async def _settle(app: App, pilot) -> None:
    # press() only posts a message; process it so the worker exists before waiting.
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


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
async def test_confirmations_off_runs_without_asking(tmp_path, monkeypatch):
    from max_cli.config import settings

    monkeypatch.setattr(settings, "CONFIRM_DESTRUCTIVE", False)
    app = FormApp(DANGEROUS)
    with patch(RUN_ACTION, return_value=ActionResult(True, "Deleted")) as run_action:
        async with app.run_test(size=(100, 40)) as pilot:
            app.query_one("#field-target", Input).value = str(tmp_path / "x.txt")
            app.query_one("#form-run", Button).press()
            await _settle(app, pilot)
            assert not isinstance(app.screen, ConfirmDialog)

    assert run_action.called


@pytest.mark.asyncio
async def test_shred_asks_even_with_confirmations_off(tmp_path, monkeypatch):
    from max_cli.config import settings

    monkeypatch.setattr(settings, "CONFIRM_DESTRUCTIVE", False)
    app = FormApp(get_action("files.shred"))
    with patch(RUN_ACTION, return_value=ActionResult(True, "Shredded")) as run_action:
        async with app.run_test(size=(100, 40)) as pilot:
            app.query_one("#field-target", Input).value = str(tmp_path / "x.txt")
            app.query_one("#form-run", Button).press()
            await pilot.pause()
            assert isinstance(app.screen, ConfirmDialog)

    assert not run_action.called


@pytest.mark.asyncio
async def test_browse_fills_the_path_field(tmp_path):
    app = FormApp(get_action("video.compress"))
    picked = tmp_path / "movie.mp4"
    picked.write_bytes(b"")
    async with app.run_test(size=(100, 60)) as pilot:
        app.query_one("#browse-target", Button).press()
        assert await _picker_ready(pilot, app)

        app.screen.query_one("#picker-path", Input).value = str(picked)
        app.screen.query_one("#picker-ok", Button).press()
        filled = await wait_until(
            pilot,
            lambda: app.query_one("#field-target", Input).value == str(picked),
        )

        assert filled


@pytest.mark.asyncio
async def test_password_fields_are_masked():
    app = FormApp(get_action("pdf.lock"))
    async with app.run_test(size=(100, 40)):
        assert app.query_one("#field-password", Input).password


@pytest.mark.asyncio
async def test_browse_adds_to_a_list_field(tmp_path):
    first, second = tmp_path / "a.pdf", tmp_path / "b.pdf"
    first.write_bytes(b"")
    second.write_bytes(b"")
    app = FormApp(get_action("pdf.merge"))
    async with app.run_test(size=(100, 60)) as pilot:
        field = app.query_one("#field-inputs", Input)
        field.value = str(first)

        app.query_one("#browse-inputs", Button).press()
        assert await _picker_ready(pilot, app)
        app.screen.query_one("#picker-path", Input).value = str(second)
        app.screen.query_one("#picker-ok", Button).press()
        added = await wait_until(pilot, lambda: field.value == f"{first}; {second}")

        assert added


def _dashboard_actions() -> list[Action]:
    return [
        action
        for group in group_names()
        for action in actions_for(group, Surface.DASHBOARD)
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("action", _dashboard_actions(), ids=lambda action: action.id)
async def test_every_dashboard_form_opens(action):
    """A choice with no default (images.convert's format) crashed the
    dashboard: Textual 8 marks an empty Select with Select.NULL, and the form
    passed Select.BLANK, which is now False."""
    app = FormApp(action)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        form = app.query_one(ActionForm)
        names = {param.name for param in form.params}
        values = form.values()

    assert set(values) == names


def _music_folder(folder: Path) -> Path:
    for name in ("done.m4a", "done.mp3", "new.m4a"):
        (folder / name).write_bytes(b"\0")
    return folder


@pytest.mark.asyncio
async def test_a_folder_runs_the_files_left(tmp_path):
    folder = _music_folder(tmp_path)
    app = FormApp(get_action("video.audio-convert"))
    ran = []

    def fake(action, args, **kwargs):
        ran.append(Path(args["target"]).name)
        return ActionResult(True, "ok", [Path(args["target"]).with_suffix(".mp3")])

    with patch(RUN_ACTION, side_effect=fake):
        async with app.run_test(size=(120, 60)) as pilot:
            app.query_one("#field-target", Input).value = str(folder)
            assert app.query("#batch-recursive") and app.query("#batch-redo")
            app.query_one("#form-run", Button).press()
            await _settle(app, pilot)
            status = _status(app)

    assert ran == ["new.m4a"]
    assert "1 of 2 files done, 1 had their result already" in status


@pytest.mark.asyncio
async def test_queueing_a_folder_adds_a_job_per_file(tmp_path):
    folder = _music_folder(tmp_path)
    (folder / "other.m4a").write_bytes(b"\0")
    app = FormApp(get_action("video.audio-convert"))
    async with app.run_test(size=(120, 60)) as pilot:
        app.query_one("#field-target", Input).value = str(folder)
        app.query_one("#form-queue", Button).press()
        await _settle(app, pilot)
        status = _status(app)

    names = sorted(
        Path(task.payload["args"]["target"]).name
        for task in get_task_manager().get_all()
    )
    assert names == ["new.m4a", "other.m4a"]
    assert "Queued 2 jobs" in status


@pytest.mark.asyncio
async def test_a_folder_with_nothing_left_says_so(tmp_path):
    (tmp_path / "a.m4a").write_bytes(b"\0")
    (tmp_path / "a.mp3").write_bytes(b"\0")
    app = FormApp(get_action("video.audio-convert"))
    with patch(RUN_ACTION) as run_action:
        async with app.run_test(size=(120, 60)) as pilot:
            app.query_one("#field-target", Input).value = str(tmp_path)
            app.query_one("#form-run", Button).press()
            await _settle(app, pilot)
            status = _status(app)

    run_action.assert_not_called()
    assert "Nothing to do" in status
