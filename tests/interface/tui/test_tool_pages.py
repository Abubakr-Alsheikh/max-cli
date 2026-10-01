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

from .waiting import wait_until

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


# --- the PDF page -----------------------------------------------------------------

PDF_DESCRIBE = "max_cli.core.operations.pdf.describe"


def test_pdf_facts_line(tmp_path):
    from max_cli.core.operations.pdf import PdfFacts
    from max_cli.interface.tui.tool_pages import describe_pdf

    facts = PdfFacts(
        path=tmp_path / "report.pdf",
        size_bytes=2048,
        pages=12,
        page_size="A4 portrait",
        title="Q3 report",
        author="Ana",
        form_fields=8,
    )
    with patch(PDF_DESCRIBE, return_value=facts):
        line = describe_pdf(facts.path).plain

    assert line == (
        'report.pdf  ·  12 pages  ·  A4 portrait  ·  2.00 KB  ·  "Q3 report" by Ana'
        "  ·  8 form fields"
    )


def test_a_locked_or_scanned_pdf_gets_its_note(tmp_path):
    from max_cli.core.operations import pdf
    from max_cli.interface.tui.tool_pages import describe_pdf

    locked = pdf.PdfFacts(
        path=tmp_path / "x.pdf", size_bytes=10, encrypted=True, note=pdf.LOCKED_NOTE
    )
    scanned = pdf.PdfFacts(
        path=tmp_path / "s.pdf",
        size_bytes=10,
        pages=1,
        scanned=True,
        note=pdf.SCANNED_NOTE,
    )
    with patch(PDF_DESCRIBE, return_value=locked):
        assert "password" in describe_pdf(locked.path).plain
    with patch(PDF_DESCRIBE, return_value=scanned):
        text = describe_pdf(scanned.path).plain
    assert "1 page  ·" in text and "OCR" in text


@pytest.mark.asyncio
@pytest.mark.parametrize("action, field", [("merge", "inputs"), ("compare", "file1")])
async def test_the_picked_pdf_goes_in_the_first_file_field(dummy_pdf, action, field):
    from max_cli.core.operations.pdf import PdfFacts
    from max_cli.interface.tui.tool_pages import PDF

    class PdfApp(App):
        def compose(self) -> ComposeResult:
            yield ToolPage(PDF, id="pdf-panel")

    app = PdfApp()
    with patch(PDF_DESCRIBE, return_value=PdfFacts(path=dummy_pdf, size_bytes=1)):
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            app.query_one("#tool-file", Input).value = str(dummy_pdf)
            app.query_one(f"#act-{action}", Button).press()
            page = app.query_one(ToolPage)
            filled = await wait_until(
                pilot,
                lambda: page.form.action.id == f"pdf.{action}"
                and page.form.query_one(f"#field-{field}", Input).value
                == str(dummy_pdf),
            )

    assert filled


def test_images_and_pdf_keys():
    from max_cli.interface.tui.widgets.sidebar import SECTION_KEYS

    assert (SECTION_KEYS["images"], SECTION_KEYS["pdf"]) == ("4", "5")


# --- the Images page --------------------------------------------------------------

IMAGES_DESCRIBE = "max_cli.core.operations.images.describe"


def test_image_facts_line(tmp_path):
    from max_cli.core.operations import images
    from max_cli.interface.tui.tool_pages import describe_images

    facts = images.ImageFacts(
        path=tmp_path / "photo.jpg",
        size_bytes=3 * 1024 * 1024,
        width=4032,
        height=3024,
        format="JPEG",
        mode="RGB",
        has_gps=True,
        taken="2024-05-01",
        camera="Pixel 7",
        note=images.GPS_NOTE,
    )
    with patch(IMAGES_DESCRIBE, return_value=facts):
        lines = describe_images(facts.path).plain.splitlines()

    assert lines == [
        "photo.jpg  ·  4032x3024 (12.2 MP)  ·  JPEG  ·  colour  ·  3.00 MB"
        "  ·  taken 2024-05-01 on Pixel 7",
        images.GPS_NOTE,
    ]


def test_a_small_animated_image_skips_megapixels(tmp_path):
    from max_cli.core.operations import images
    from max_cli.interface.tui.tool_pages import describe_images

    facts = images.ImageFacts(
        path=tmp_path / "spin.gif",
        size_bytes=2048,
        width=20,
        height=20,
        format="GIF",
        mode="P",
        frames=3,
    )
    with patch(IMAGES_DESCRIBE, return_value=facts):
        line = describe_images(facts.path).plain

    assert (
        line
        == "spin.gif  ·  20x20  ·  GIF  ·  palette colours  ·  3 frames  ·  2.00 KB"
    )


def test_folder_facts_say_where_results_go(tmp_path):
    from max_cli.core.operations import images
    from max_cli.interface.tui.tool_pages import describe_images

    facts = images.ImageFacts(
        path=tmp_path / "photos",
        size_bytes=4096,
        is_folder=True,
        image_count=3,
        formats={"JPG": 2, "PNG": 1},
        output_dir=tmp_path / "photos_optimized",
    )
    with patch(IMAGES_DESCRIBE, return_value=facts):
        lines = describe_images(facts.path).plain.splitlines()

    assert lines == [
        "photos  ·  3 images  ·  4.00 KB  ·  2 JPG, 1 PNG",
        "Actions run on each image here; results go to photos_optimized.",
    ]


@pytest.mark.asyncio
async def test_the_images_page_takes_a_folder(tmp_path):
    from max_cli.core.operations import images
    from max_cli.interface.tui.tool_pages import IMAGES

    class ImagesApp(App):
        def compose(self) -> ComposeResult:
            yield ToolPage(IMAGES, id="images-panel")

    facts = images.ImageFacts(path=tmp_path, size_bytes=0, is_folder=True)
    app = ImagesApp()
    with patch(IMAGES_DESCRIBE, return_value=facts):
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            title = app.query_one(".tool-file-card").border_title
            app.query_one("#tool-file", Input).value = str(tmp_path)
            app.query_one("#act-strip", Button).press()
            page = app.query_one(ToolPage)
            filled = await wait_until(
                pilot,
                lambda: page.form.action.id == "images.strip"
                and page.form.query_one("#field-target", Input).value == str(tmp_path),
            )

    assert title == "FILE OR FOLDER"
    assert filled


# --- which field gets the picked path -------------------------------------------


@pytest.mark.parametrize(
    "action_id, field",
    [
        ("pdf.rip", "target"),  # its output folder stays as it is
        ("files.order", "folder"),
        ("files.smart-sort", "path"),
        ("files.undo", None),
    ],
)
def test_the_picked_path_goes_to_the_input(action_id, field):
    from max_cli.core.catalog import get_action
    from max_cli.interface.tui.widgets.tool_page import file_param

    assert file_param(get_action(action_id)) == field


# --- the Files page ---------------------------------------------------------------

FILES_DESCRIBE = "max_cli.core.operations.files.describe"


def test_files_facts_for_a_folder(tmp_path):
    from max_cli.core.operations import files
    from max_cli.interface.tui.tool_pages import describe_files

    facts = files.PathFacts(
        path=tmp_path / "Downloads",
        size_bytes=3 * 1024 * 1024,
        is_folder=True,
        file_count=4,
        folder_count=1,
        kinds={"image": 2, "pdf": 1, "other": 1},
        biggest=tmp_path / "Downloads" / "scan.pdf",
        biggest_bytes=2 * 1024 * 1024,
        note=files.ORGANIZE_NOTE,
    )
    with patch(FILES_DESCRIBE, return_value=facts):
        lines = describe_files(facts.path).plain.splitlines()

    assert lines == [
        "Downloads  ·  4 files  ·  1 folder  ·  3.00 MB  ·  2 images, 1 PDF, 1 other file",
        "Biggest: scan.pdf (2.00 MB)",
        files.ORGANIZE_NOTE,
    ]


def test_files_facts_for_a_file(tmp_path):
    from datetime import datetime

    from max_cli.core.operations import files
    from max_cli.interface.tui.tool_pages import describe_files

    facts = files.PathFacts(
        path=tmp_path / "report.pdf",
        size_bytes=2048,
        kind="pdf",
        modified=datetime(2024, 5, 1, 9, 30),
    )
    with patch(FILES_DESCRIBE, return_value=facts):
        line = describe_files(facts.path).plain

    assert line == "report.pdf  ·  PDF  ·  2.00 KB  ·  modified 2024-05-01 09:30"


@pytest.mark.asyncio
async def test_a_pdf_picked_on_files_opens_on_the_pdf_page(dummy_pdf):
    from max_cli.interface.tui.app import MaxDashboardApp

    app = MaxDashboardApp()
    async with app.run_test(size=(140, 44)) as pilot:
        app.navigate("files")
        files_page = app.query_one("#files-panel", ToolPage)
        files_page.query_one("#tool-file", Input).value = str(dummy_pdf)
        button = files_page.query_one("#tool-open-page", Button)
        offered = await wait_until(pilot, lambda: button.has_class("-offered"))
        label = str(button.label)

        button.press()
        pdf_page = app.query_one("#pdf-panel", ToolPage)
        filled = await wait_until(
            pilot,
            lambda: pdf_page.display
            and pdf_page.form.query_one("#field-target", Input).value == str(dummy_pdf),
        )

    assert offered and label == "Open on the PDF page (5)"
    assert filled


@pytest.mark.asyncio
async def test_a_page_offers_no_link_for_its_own_kind(dummy_pdf):
    from max_cli.interface.tui.app import MaxDashboardApp

    app = MaxDashboardApp()
    async with app.run_test(size=(140, 44)) as pilot:
        app.navigate("pdf")
        page = app.query_one("#pdf-panel", ToolPage)
        page.query_one("#tool-file", Input).value = str(dummy_pdf)
        await wait_until(pilot, lambda: "page" in _facts_of(page))
        offered = page.query_one("#tool-open-page", Button).has_class("-offered")

    assert not offered


def _facts_of(page: ToolPage) -> str:
    return str(page.query_one("#tool-facts", Static).content)


@pytest.mark.asyncio
async def test_smart_sort_on_the_files_page_asks_before_moving(tmp_path):
    """Organize used to run smart-sort at once, with no question asked."""
    from max_cli.interface.tui.tool_pages import FILES
    from max_cli.interface.tui.widgets.dialogs import ConfirmDialog

    class FilesApp(App):
        def compose(self) -> ComposeResult:
            yield ToolPage(FILES, id="files-panel")

    (tmp_path / "invoice.pdf").write_bytes(b"%PDF")
    app = FilesApp()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        app.query_one("#tool-file", Input).value = str(tmp_path)
        app.query_one("#act-smart-sort", Button).press()
        page = app.query_one(ToolPage)
        filled = await wait_until(
            pilot,
            lambda: page.form.action.id == "files.smart-sort"
            and page.form.query_one("#field-path", Input).value == str(tmp_path),
        )
        page.form.query_one("#form-run", Button).press()
        asked = await wait_until(pilot, lambda: isinstance(app.screen, ConfirmDialog))

    assert filled and asked
    assert (tmp_path / "invoice.pdf").exists()


@pytest.mark.asyncio
async def test_backups_keeps_its_restore_field_empty(tmp_path):
    from max_cli.interface.tui.tool_pages import FILES

    class FilesApp(App):
        def compose(self) -> ComposeResult:
            yield ToolPage(FILES, id="files-panel")

    app = FilesApp()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        app.query_one("#tool-file", Input).value = str(tmp_path)
        app.query_one("#act-backups", Button).press()
        page = app.query_one(ToolPage)
        shown = await wait_until(pilot, lambda: page.form.action.id == "files.backups")
        restore = page.form.query_one("#field-restore", Input).value

    assert shown and restore == ""


@pytest.mark.asyncio
async def test_a_folder_action_gets_the_picked_files_folder(dummy_pdf):
    from max_cli.interface.tui.tool_pages import FILES

    class FilesApp(App):
        def compose(self) -> ComposeResult:
            yield ToolPage(FILES, id="files-panel")

    app = FilesApp()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        app.query_one("#tool-file", Input).value = str(dummy_pdf)
        app.query_one("#act-order", Button).press()
        page = app.query_one(ToolPage)
        filled = await wait_until(
            pilot,
            lambda: page.form.action.id == "files.order"
            and page.form.query_one("#field-folder", Input).value
            == str(dummy_pdf.parent),
        )

    assert filled


@pytest.mark.asyncio
@pytest.mark.parametrize("width, columns", [(160, 3), (110, 2)])
async def test_chips_drop_a_column_when_names_would_be_cut(width, columns):
    """At 120 columns three chips a row cut "backup-cleanup" to "backup-clea"."""
    from textual.containers import Grid

    from max_cli.interface.tui.tool_pages import FILES

    class FilesApp(App):
        def compose(self) -> ComposeResult:
            yield ToolPage(FILES, id="files-panel")

    app = FilesApp()
    async with app.run_test(size=(width, 50)) as pilot:
        grid = app.query(".section-chips").first(Grid)
        fitted = await wait_until(
            pilot, lambda: grid.styles.grid_size_columns == columns
        )
        chip = app.query_one("#act-backup-cleanup", Button)
        label_fits = chip.content_region.width >= len("backup-cleanup")

    assert fitted and label_fits
