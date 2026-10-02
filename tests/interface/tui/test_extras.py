"""The Extras page (`max tools` in the dashboard) and Ctrl+P action search."""

from pathlib import Path
from unittest.mock import patch

import pytest
from textual.command import CommandPalette
from textual.widgets import Button, Input, Static

from max_cli.core.catalog import actions_for, group_names
from max_cli.core.catalog.spec import Surface
from max_cli.interface.tui.app import MaxDashboardApp
from max_cli.interface.tui.commands import GROUP_PAGES, palette_entries
from max_cli.interface.tui.widgets.action_form import ActionForm
from max_cli.interface.tui.widgets.extras_panel import ExtrasPanel
from max_cli.interface.tui.widgets.sidebar import SECTION_KEYS, SECTIONS
from max_cli.interface.tui.widgets.tool_page import ToolPage

from .waiting import wait_until

SIZE = (140, 44)
SAVE_IMAGE = "max_cli.core.engines.system_engine.SystemEngine.save_clipboard_image"


def _shown(app: MaxDashboardApp) -> str:
    [panel] = [panel for panel in app.query("#content > *") if panel.display]
    return str(panel.id).removesuffix("-panel")


def _form(app: MaxDashboardApp, name: str) -> ActionForm:
    return app.query_one(f"#extras-{name}-card ActionForm", ActionForm)


# --- the Extras page ----------------------------------------------------------


@pytest.mark.asyncio
async def test_key_0_opens_extras_with_a_card_per_action():
    app = MaxDashboardApp()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press(SECTION_KEYS["extras"])
        await pilot.pause()

        assert _shown(app) == "extras"
        for name in ("share", "paste", "copy"):
            assert _form(app, name).action.id == f"tools.{name}"


@pytest.mark.asyncio
async def test_share_shows_the_qr_code_on_the_page():
    app = MaxDashboardApp()
    async with app.run_test(size=SIZE) as pilot:
        app.navigate("extras")
        form = _form(app, "share")
        form.query_one("#field-data", Input).value = "http://192.168.1.20:8000"
        form.query_one("#form-run", Button).press()
        qr = app.query_one("#extras-qr", Static)
        await wait_until(pilot, lambda: qr.has_class("-shown"))

        rows = str(qr.content).splitlines()
        assert len(rows) > 10
        assert set("".join(rows)) <= {" ", "█", "▀", "▄"}


@pytest.mark.asyncio
async def test_paste_starts_from_a_new_name_and_offers_the_images_page(isolated_home):
    (isolated_home / "Pictures").mkdir()

    def fake_save(_engine, path: Path) -> None:
        path.write_bytes(b"png")

    app = MaxDashboardApp()
    with patch(SAVE_IMAGE, fake_save):
        async with app.run_test(size=SIZE) as pilot:
            app.navigate("extras")
            form = _form(app, "paste")
            output = form.query_one("#field-output", Input)
            first_name = output.value
            assert Path(first_name).parent == isolated_home / "Pictures"
            assert Path(first_name).name.startswith("clipboard-")

            form.query_one("#form-run", Button).press()
            offer = app.query_one("#extras-open-image", Button)
            await wait_until(pilot, lambda: offer.has_class("-shown"))
            assert Path(first_name).exists()

            offer.press()
            await wait_until(pilot, lambda: _shown(app) == "images")
            box = app.query_one("#images-panel #tool-file", Input)
            assert box.value == first_name


@pytest.mark.asyncio
async def test_an_existing_paste_file_is_kept(tmp_path):
    existing = tmp_path / "shot.png"
    existing.write_bytes(b"keep")
    app = MaxDashboardApp()
    with patch(SAVE_IMAGE) as save:
        async with app.run_test(size=SIZE) as pilot:
            app.navigate("extras")
            form = _form(app, "paste")
            form.query_one("#field-output", Input).value = str(existing)
            form.query_one("#form-run", Button).press()
            status = form.query_one("#form-status", Static)
            await wait_until(pilot, lambda: "already exists" in str(status.content))

    save.assert_not_called()
    assert existing.read_bytes() == b"keep"


# --- Ctrl+P ---------------------------------------------------------------------


def test_every_group_has_a_page():
    pages = {section_id for section_id, _icon, _label in SECTIONS}
    for group in group_names():
        assert GROUP_PAGES[group] in pages, group


def test_the_palette_lists_every_page_and_dashboard_action():
    targets = {target for _text, _help, target in palette_entries()}

    for section_id, _icon, _label in SECTIONS:
        assert f"page:{section_id}" in targets
    for group in group_names():
        for action in actions_for(group, Surface.DASHBOARD):
            assert f"action:{action.id}" in targets


@pytest.mark.asyncio
async def test_open_action_shows_the_form_with_its_first_field_focused():
    app = MaxDashboardApp()
    async with app.run_test(size=SIZE) as pilot:
        app.open_action("pdf.merge")
        page = app.query_one("#pdf-panel", ToolPage)
        await wait_until(
            pilot,
            lambda: page.form is not None
            and page.form.is_mounted
            and app.focused is not None
            and page.form in app.focused.ancestors,
        )

        assert _shown(app) == "pdf"
        assert page.action is not None and page.action.id == "pdf.merge"


@pytest.mark.asyncio
async def test_open_action_on_extras_focuses_its_card():
    app = MaxDashboardApp()
    async with app.run_test(size=SIZE) as pilot:
        app.open_action("tools.copy")
        await pilot.pause()

        assert _shown(app) == "extras"
        assert app.focused is app.query_one(ExtrasPanel).query_one(
            "#extras-copy-card #field-target"
        )


@pytest.mark.asyncio
async def test_ctrl_p_finds_an_action_by_name():
    app = MaxDashboardApp()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("ctrl+p")
        await wait_until(pilot, lambda: isinstance(app.screen, CommandPalette))
        await pilot.press(*"pdf: merge")
        await pilot.pause(0.5)
        await pilot.press("enter")
        page = app.query_one("#pdf-panel", ToolPage)
        await wait_until(
            pilot, lambda: page.action is not None and page.action.name == "merge"
        )

        assert _shown(app) == "pdf"


# --- removed settings ---------------------------------------------------------


@pytest.mark.asyncio
async def test_a_removed_setting_in_the_file_is_pointed_out_at_start(isolated_home):
    (isolated_home / ".max_config.env").write_text("VERBOSE=true\n", encoding="utf-8")
    app = MaxDashboardApp()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        messages = [notice.message for notice in app._notifications]

    assert any("VERBOSE" in message for message in messages)
