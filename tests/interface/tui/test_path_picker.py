"""The Browse dialog (widgets/path_picker.py): places, moving between folders,
filters, pins and recent folders, and the three modes."""

from pathlib import Path
from typing import Optional

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Button, Checkbox, DataTable, Input, OptionList, Static

from max_cli.common.file_kinds import IMAGE, KIND_SUFFIXES
from max_cli.interface.tui.ui_prefs import DOWNLOAD_FOLDER_PREF, save_pref
from max_cli.interface.tui.widgets import path_picker
from max_cli.interface.tui.widgets.path_picker import PathPicker, PickMode

from .waiting import wait_until

SIZE = (120, 40)


@pytest.fixture
def tree(tmp_path):
    """photos/ (a.jpg, b.png, notes.txt, .secret.jpg, trips/), docs/, report.pdf"""
    photos = tmp_path / "photos"
    (photos / "trips").mkdir(parents=True)
    for name in ("a.jpg", "b.png", "notes.txt", ".secret.jpg"):
        (photos / name).write_bytes(b"x" * 10)
    (tmp_path / "docs").mkdir()
    (tmp_path / "report.pdf").write_bytes(b"%PDF")
    return tmp_path


class PickerApp(App):
    def __init__(self, picker: PathPicker) -> None:
        super().__init__()
        self.picker = picker
        self.picked: list[Optional[Path]] = []

    def compose(self) -> ComposeResult:
        yield Static("")

    def on_mount(self) -> None:
        self.push_screen(self.picker, self.picked.append)


def _names(app: App) -> list[str]:
    table = app.screen.query_one("#picker-table", DataTable)
    return [
        str(table.get_row_at(row)[0]).split(" ", 1)[1] for row in range(table.row_count)
    ]


async def _listed(pilot, app: App, expected: list[str]) -> bool:
    return await wait_until(pilot, lambda: _names(app) == expected)


# --- the helpers ---------------------------------------------------------------


def test_list_folder_sorts_folders_first_and_filters(tree):
    photos = tree / "photos"

    everything = path_picker.list_folder(photos)
    images = path_picker.list_folder(photos, suffixes=KIND_SUFFIXES[IMAGE])
    hidden = path_picker.list_folder(photos, show_hidden=True)

    assert [entry.name for entry in everything] == [
        "trips",
        "a.jpg",
        "b.png",
        "notes.txt",
    ]
    assert [entry.name for entry in images] == ["trips", "a.jpg", "b.png"]
    assert ".secret.jpg" in [entry.name for entry in hidden]
    assert everything[1].size == 10


def test_start_folder_falls_back_to_the_last_folder_then_home(tree):
    assert path_picker.start_folder(tree / "photos" / "a.jpg") == tree / "photos"
    assert path_picker.start_folder(None) == Path.home()

    path_picker.remember_choice(tree / "docs")

    assert path_picker.start_folder(None) == tree / "docs"
    assert path_picker.start_folder(tree / "gone" / "x.mp4") == tree / "docs"


def test_recent_folders_keep_the_newest_first_without_repeats(tree):
    for folder in ("photos", "docs", "photos"):
        path_picker.remember_choice(tree / folder)
    path_picker.remember_choice(tree / "report.pdf")

    assert path_picker.recent_folders() == [tree, tree / "photos", tree / "docs"]


def test_places_lists_the_usual_folders_that_exist():
    (Path.home() / "Downloads").mkdir()

    names = [name for name, _path in path_picker.places()]

    assert names[:2] == ["Home", "Downloads"]
    assert "Desktop" not in names


def test_max_downloads_is_the_folder_the_download_page_saves_into(tmp_path):
    # The Download page remembers its own folder; the setting's folder can
    # sit elsewhere, empty. The place has to open the one with the files.
    page_folder = tmp_path / "Videos" / "Max Downloads"
    page_folder.mkdir(parents=True)
    save_pref(DOWNLOAD_FOLDER_PREF, str(page_folder))

    assert ("Max downloads", page_folder) in path_picker.places()


# --- the dialog ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_file_opens_in_its_folder_with_the_file_highlighted(tree):
    app = PickerApp(PathPicker(tree / "photos" / "b.png"))
    async with app.run_test(size=SIZE) as pilot:
        assert await _listed(pilot, app, ["..", "trips", "a.jpg", "b.png", "notes.txt"])
        await pilot.press("enter")
        await pilot.pause()

    assert app.picked == [tree / "photos" / "b.png"]


@pytest.mark.asyncio
async def test_enter_opens_folders_and_backspace_goes_up(tree):
    app = PickerApp(PathPicker(tree))
    async with app.run_test(size=SIZE) as pilot:
        assert await _listed(pilot, app, ["..", "docs", "photos", "report.pdf"])
        await pilot.press("down", "enter")  # photos
        assert await _listed(pilot, app, ["..", "trips", "a.jpg", "b.png", "notes.txt"])
        path_box = app.screen.query_one("#picker-path", Input).value

        await pilot.press("backspace")
        assert await _listed(pilot, app, ["..", "docs", "photos", "report.pdf"])
        table = app.screen.query_one("#picker-table", DataTable)
        # Going up puts the cursor back on the folder you came from.
        on_photos = await wait_until(pilot, lambda: table.cursor_row == 2)

    assert path_box == str(tree / "photos")
    assert on_photos


@pytest.mark.asyncio
async def test_back_returns_to_the_previous_folder(tree):
    app = PickerApp(PathPicker(tree / "photos"))
    async with app.run_test(size=SIZE) as pilot:
        assert await _listed(pilot, app, ["..", "trips", "a.jpg", "b.png", "notes.txt"])
        await pilot.press("enter")  # the cursor starts on trips, past ".."
        assert await _listed(pilot, app, [".."])
        app.screen.query_one("#picker-back", Button).press()
        back_in_photos = await _listed(
            pilot, app, ["..", "trips", "a.jpg", "b.png", "notes.txt"]
        )

    assert back_in_photos


@pytest.mark.asyncio
async def test_typing_a_folder_path_goes_there(tree):
    app = PickerApp(PathPicker(tree))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        box = app.screen.query_one("#picker-path", Input)
        box.value = str(tree / "photos" / "trips")
        box.focus()
        await pilot.press("enter")
        arrived = await _listed(pilot, app, [".."])

    assert arrived


@pytest.mark.asyncio
async def test_the_filter_narrows_the_list(tree):
    app = PickerApp(PathPicker(tree / "photos"))
    async with app.run_test(size=SIZE) as pilot:
        await _listed(pilot, app, ["..", "trips", "a.jpg", "b.png", "notes.txt"])
        app.screen.query_one("#picker-filter", Input).value = "PNG"
        narrowed = await _listed(pilot, app, ["..", "b.png"])
        status = str(app.screen.query_one("#picker-status", Static).content)

    assert narrowed
    assert 'matching "png"' in status


@pytest.mark.asyncio
async def test_a_page_shows_its_own_files_until_all_files_is_ticked(tree):
    app = PickerApp(PathPicker(tree / "photos", file_types="images"))
    async with app.run_test(size=SIZE) as pilot:
        only_images = await _listed(pilot, app, ["..", "trips", "a.jpg", "b.png"])
        app.screen.query_one("#picker-all", Checkbox).value = True
        everything = await _listed(
            pilot, app, ["..", "trips", "a.jpg", "b.png", "notes.txt"]
        )
        app.screen.query_one("#picker-hidden", Checkbox).value = True
        with_hidden = await wait_until(pilot, lambda: ".secret.jpg" in _names(app))

    assert only_images and everything and with_hidden


@pytest.mark.asyncio
async def test_folder_mode_shows_files_too_and_returns_the_open_folder(tree):
    app = PickerApp(PathPicker(tree, PickMode.FOLDER))
    async with app.run_test(size=SIZE) as pilot:
        assert await _listed(pilot, app, ["..", "docs", "photos", "report.pdf"])
        await pilot.press("down", "enter")  # from docs to photos
        assert await _listed(pilot, app, ["..", "trips", "a.jpg", "b.png", "notes.txt"])
        await pilot.press("down", "enter")  # a file: nothing to open or pick
        await pilot.pause()
        still_open = isinstance(app.screen, PathPicker)
        table = app.screen.query_one("#picker-table", DataTable)
        file_style = table.get_row_at(2)[0].style
        app.screen.query_one("#picker-ok", Button).press()
        await pilot.pause()

    assert still_open
    assert file_style == "dim"
    assert app.picked == [tree / "photos"]


@pytest.mark.asyncio
async def test_a_folder_of_the_pages_files_does_not_look_empty(tree):
    app = PickerApp(PathPicker(tree / "photos", PickMode.FOLDER, file_types="images"))
    async with app.run_test(size=SIZE) as pilot:
        listed = await _listed(pilot, app, ["..", "trips", "a.jpg", "b.png"])
        status = str(app.screen.query_one("#picker-status", Static).render())

    assert listed
    assert "1 folder" in status and "2 images" in status


@pytest.mark.asyncio
async def test_save_mode_joins_the_folder_and_the_name(tree):
    app = PickerApp(PathPicker(tree / "photos" / "out.mp4", PickMode.SAVE))
    async with app.run_test(size=SIZE) as pilot:
        await _listed(pilot, app, ["..", "trips", "a.jpg", "b.png", "notes.txt"])
        name = app.screen.query_one("#picker-name", Input).value
        app.screen.query_one("#picker-ok", Button).press()
        await pilot.pause()

    assert name == "out.mp4"
    assert app.picked == [tree / "photos" / "out.mp4"]


@pytest.mark.asyncio
async def test_save_mode_asks_for_a_name(tree):
    app = PickerApp(PathPicker(tree, PickMode.SAVE))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        app.screen.query_one("#picker-ok", Button).press()
        await pilot.pause()
        status = str(app.screen.query_one("#picker-status", Static).content)

    assert app.picked == []
    assert "file name" in status


@pytest.mark.asyncio
async def test_file_mode_can_use_the_open_folder(tree):
    app = PickerApp(PathPicker(tree / "photos"))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        app.screen.query_one("#picker-use-folder", Button).press()
        await pilot.pause()

    assert app.picked == [tree / "photos"]


@pytest.mark.asyncio
async def test_pinning_adds_the_folder_to_places_and_choices_go_to_recent(tree):
    app = PickerApp(PathPicker(tree / "photos"))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        app.screen.query_one("#picker-pin", Button).press()
        await pilot.pause()
        label = str(app.screen.query_one("#picker-pin", Button).label)
        places = app.screen.query_one("#picker-places-list", OptionList)
        prompts = [
            str(places.get_option_at_index(i).prompt)
            for i in range(places.option_count)
        ]
        app.screen.query_one("#picker-use-folder", Button).press()
        await pilot.pause()

    assert path_picker.pinned_folders() == [tree / "photos"]
    assert "PINNED" in prompts and "* photos" in prompts
    assert label == "Unpin this folder"
    assert path_picker.recent_folders() == [tree / "photos"]


@pytest.mark.asyncio
async def test_a_place_opens_its_folder(tree):
    path_picker.set_pinned(tree / "docs", True)
    app = PickerApp(PathPicker(tree / "photos"))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        places = app.screen.query_one("#picker-places-list", OptionList)
        index = next(
            i
            for i in range(places.option_count)
            if str(places.get_option_at_index(i).prompt) == "* docs"
        )
        places.highlighted = index
        places.action_select()
        opened = await _listed(pilot, app, [".."])
        path_box = app.screen.query_one("#picker-path", Input).value

    assert opened and path_box == str(tree / "docs")


@pytest.mark.asyncio
async def test_escape_cancels(tree):
    app = PickerApp(PathPicker(tree))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

    assert app.picked == [None]
