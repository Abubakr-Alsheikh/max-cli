"""The command-group pages (widgets/tool_page.py, tool_pages.py): Video first."""

from pathlib import Path
from unittest.mock import patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Button, Input, Static

from max_cli.common.exceptions import ResourceNotFoundError
from max_cli.core.catalog import actions_for
from max_cli.core.catalog.spec import Surface
from max_cli.core.operations.result import ActionResult
from max_cli.core.operations.video import MediaFacts
from max_cli.interface.tui.tool_pages import TOOL_PAGES, VIDEO, describe_video
from max_cli.interface.tui.widgets.action_form import ActionForm
from max_cli.interface.tui.widgets.tool_page import ToolPage
from tests.interface.tui.waiting import wait_until

DESCRIBE = "max_cli.core.operations.video.describe"
RUN_ACTION = "max_cli.core.catalog.runner.run_action"
SIZE = (140, 60)


class VideoApp(App):
    def compose(self) -> ComposeResult:
        yield ToolPage(VIDEO, id="video-panel")


async def _settle(app: App, pilot) -> None:
    await pilot.pause()
    await app.workers.wait_for_complete()
    for _ in range(3):
        await pilot.pause()


def _form(app: App) -> ActionForm:
    form = app.query_one(ToolPage).form
    assert form is not None
    return form


def _target(app: App) -> str:
    return _form(app).query_one("#field-target", Input).value


def _facts(app: App) -> str:
    return str(app.query_one("#tool-facts", Static).content)


# --- the specs ----------------------------------------------------------------


@pytest.mark.parametrize("spec", TOOL_PAGES, ids=lambda spec: spec.page_id)
def test_every_dashboard_action_sits_in_one_section(spec):
    listed = [name for section in spec.sections for name in section.actions]
    offered = [action.name for action in actions_for(spec.group, Surface.DASHBOARD)]

    assert sorted(listed) == sorted(offered)
    assert len(listed) == len(set(listed))


def test_each_page_has_a_sidebar_entry():
    from max_cli.interface.tui.widgets.sidebar import SECTIONS

    ids = [section_id for section_id, _icon, _label in SECTIONS]
    assert all(spec.page_id in ids for spec in TOOL_PAGES)


def test_video_facts_line(tmp_path):
    facts = MediaFacts(
        path=tmp_path / "clip.mp4",
        size_bytes=412 * 1024 * 1024,
        duration=3725,
        width=1920,
        height=1080,
        fps=29.97,
        video_codec="h264",
        audio_codec="aac",
        audio_channels=2,
        bitrate=8_200_000,
    )
    with patch(DESCRIBE, return_value=facts):
        line = describe_video(facts.path).plain

    assert line == (
        "clip.mp4  ·  1:02:05  ·  1920x1080  ·  29.97 fps  ·  h264 + aac stereo"
        "  ·  412.00 MB  ·  8.2 Mb/s"
    )


def test_audio_only_and_missing_ffmpeg_are_explained(tmp_path):
    facts = MediaFacts(
        path=tmp_path / "song.mp3",
        size_bytes=5000,
        audio_codec="mp3",
        audio_channels=1,
        note="FFmpeg isn't installed yet, so only the size is known.",
    )
    with patch(DESCRIBE, return_value=facts):
        text = describe_video(facts.path).plain

    assert "mp3 mono" in text
    assert "Audio only" in text
    assert "FFmpeg isn't installed" in text


# --- the page -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_first_action_shows_first():
    app = VideoApp()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        action = _form(app).action.id
        selected = [chip.id for chip in app.query(".chip.-selected")]

    assert action == "video.compress"
    assert selected == ["act-compress"]


@pytest.mark.asyncio
async def test_a_picked_file_is_described_and_fills_every_form(dummy_video, tmp_path):
    facts = MediaFacts(path=dummy_video, size_bytes=10, duration=5, video_codec="h264")
    app = VideoApp()
    with patch(DESCRIBE, return_value=facts) as describe:
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            app.query_one("#tool-file", Input).value = str(dummy_video)
            app.query_one("#tool-file", Input).focus()
            await pilot.press("enter")
            await _settle(app, pilot)
            facts_text = _facts(app)
            first_target = _target(app)
            app.query_one("#act-cut", Button).press()
            await wait_until(
                pilot,
                lambda: _form(app).action.id == "video.cut"
                and _target(app) == str(dummy_video),
            )
            second_action = _form(app).action.id
            second_target = _target(app)

    describe.assert_called_with(Path(str(dummy_video)))
    assert facts_text.startswith("test.mp4  ·  0:05")
    assert first_target == str(dummy_video)
    assert (second_action, second_target) == ("video.cut", str(dummy_video))


@pytest.mark.asyncio
async def test_run_uses_the_picked_file(dummy_video):
    result = ActionResult(True, "Video saved: out.mp4", [])
    app = VideoApp()
    with (
        patch(DESCRIBE, return_value=MediaFacts(path=dummy_video, size_bytes=1)),
        patch(RUN_ACTION, return_value=result) as run_action,
    ):
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            app.query_one("#tool-file", Input).value = str(dummy_video)
            await pilot.pause()
            app.query_one("#form-run", Button).press()
            await _settle(app, pilot)

    action, values = run_action.call_args.args[:2]
    assert action.id == "video.compress"
    assert values["target"] == str(dummy_video)


@pytest.mark.asyncio
async def test_an_unreadable_file_shows_the_reason(tmp_path):
    app = VideoApp()
    with patch(DESCRIBE, side_effect=ResourceNotFoundError("File not found: x.mp4")):
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            app.query_one("#tool-file", Input).value = str(tmp_path / "x.mp4")
            app.query_one("#tool-file", Input).focus()
            await pilot.press("enter")
            await _settle(app, pilot)
            text = _facts(app)

    assert text == "File not found: x.mp4"


@pytest.mark.asyncio
async def test_in_the_dashboard_key_3_opens_video():
    from max_cli.interface.tui.app import MaxDashboardApp
    from max_cli.interface.tui.widgets.sidebar import SECTION_KEYS

    app = MaxDashboardApp()
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.query_one("#sidebar").focus()
        await pilot.press(SECTION_KEYS["video"])
        await pilot.pause()
        shown = app.query_one("#video-panel").display

    assert SECTION_KEYS["video"] == "3"
    assert shown
