"""The Extras page: the `max tools` actions, each in its own card.

- SHARE AS QR CODE: type a link or text, Run shows the code on the page to
  scan with a phone.
- SAVE CLIPBOARD IMAGE: saves a screenshot from the clipboard. The file name
  starts as a new dated name in Pictures, so a second paste never asks
  about the first; a saved image can be opened on the Images page.
- COPY TEXT FILE: puts a text file's contents on the clipboard.

Each card holds the action's `ActionForm`, so the fields and defaults match
the CLI. The page reacts to `ActionForm.Finished` to show the results.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Grid, Vertical
from textual.content import Content
from textual.widgets import Button, Input, Static

from max_cli.core.catalog import get_action
from max_cli.interface.tui.messages import OpenFile
from max_cli.interface.tui.widgets.action_form import ActionForm
from max_cli.interface.tui.widgets.sidebar import SECTION_KEYS

GROUP = "tools"
# Below this width the cards stack in one column.
TWO_COLUMN_MIN_WIDTH = 100
PASTE_NAME_FORMAT = "clipboard-%Y%m%d-%H%M%S.png"
CARD_TITLES = {
    "share": "SHARE AS QR CODE",
    "paste": "SAVE CLIPBOARD IMAGE",
    "copy": "COPY TEXT FILE",
}


def paste_name(now: datetime) -> Path:
    """A new file name for a pasted image: Pictures when you have one."""
    pictures = Path.home() / "Pictures"
    folder = pictures if pictures.is_dir() else Path.home()
    return folder / now.strftime(PASTE_NAME_FORMAT)


class ExtrasPanel(Vertical):
    """QR codes and the clipboard."""

    DEFAULT_CSS = """
    #extras-header {
        height: 3;
        margin-bottom: 1;
    }
    #extras-grid {
        height: auto;
        grid-size: 2;
        grid-columns: 1fr 1fr;
        grid-gutter: 0 2;
        grid-rows: auto;
    }
    ExtrasPanel .extras-column {
        height: auto;
    }
    ExtrasPanel .extras-card {
        height: auto;
        background: $surface;
        border: round $border;
        border-title-color: $primary;
        border-title-style: bold;
        padding: 0 1;
        margin-bottom: 1;
    }
    ExtrasPanel .extras-card:focus-within {
        border: round $primary;
    }
    ExtrasPanel ActionForm {
        padding: 0;
        margin-bottom: 1;
    }
    #extras-qr {
        display: none;
        width: auto;
        height: auto;
        margin-bottom: 1;
        color: $foreground;
        background: $background;
    }
    #extras-qr.-shown {
        display: block;
    }
    #extras-qr-caption {
        display: none;
        color: $text-muted;
        margin-bottom: 1;
    }
    #extras-qr-caption.-shown {
        display: block;
    }
    #extras-open-image {
        display: none;
        margin-bottom: 1;
    }
    #extras-open-image.-shown {
        display: block;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._saved_image: Optional[Path] = None

    def compose(self) -> ComposeResult:
        yield Static(self._brand(), id="extras-header")
        with Grid(id="extras-grid"):
            with Vertical(classes="extras-column"):
                with self._card("share"):
                    yield ActionForm(get_action(f"{GROUP}.share"))
                    yield Static("", id="extras-qr")
                    yield Static(
                        "Point your phone's camera at the code.",
                        id="extras-qr-caption",
                    )
            with Vertical(classes="extras-column"):
                with self._card("paste"):
                    yield ActionForm(get_action(f"{GROUP}.paste"))
                    yield Button("", id="extras-open-image")
                with self._card("copy"):
                    yield ActionForm(get_action(f"{GROUP}.copy"))

    @staticmethod
    def _card(name: str) -> Vertical:
        card = Vertical(classes="extras-card", id=f"extras-{name}-card")
        card.border_title = CARD_TITLES[name]
        return card

    @staticmethod
    def _brand() -> Content:
        return Content.assemble(
            ("◢◤ ", "bold $secondary"),
            ("EXTRAS", "bold $primary"),
            (" // QR CODES AND THE CLIPBOARD\n", "bold"),
            (
                "Share a link with your phone  ·  save a screenshot  ·  "
                "copy a text file",
                "$text-muted",
            ),
        )

    def on_mount(self) -> None:
        self._new_paste_name()

    def _new_paste_name(self) -> None:
        """A fresh dated name, with the cursor at its end so the name shows
        rather than the start of a long folder path."""
        form = self._form("paste")
        form.set_value("output", paste_name(datetime.now()))
        field = form.query_one("#field-output", Input)
        field.cursor_position = len(field.value)

    def on_resize(self) -> None:
        columns = 2 if self.size.width >= TWO_COLUMN_MIN_WIDTH else 1
        grid = self.query_one("#extras-grid", Grid)
        if grid.styles.grid_size_columns != columns:
            grid.styles.grid_size_columns = columns

    def _form(self, name: str) -> ActionForm:
        return self.query_one(f"#extras-{name}-card ActionForm", ActionForm)

    def show_action(self, name: str) -> None:
        """Bring an action's card into view with its first field focused
        (Ctrl+P)."""
        card = self.query_one(f"#extras-{name}-card", Vertical)
        card.scroll_visible(animate=False)
        first = card.query(Input).first()
        first.focus()

    # --- results ------------------------------------------------------------

    @on(ActionForm.Finished)
    def _on_finished(self, event: ActionForm.Finished) -> None:
        event.stop()
        result = event.result
        if not result.ok:
            return
        if event.action.name == "share":
            self._show_qr(str(result.details.get("qr", "")))
        elif event.action.name == "paste" and result.output_files:
            self._offer_image(result.output_files[0])
            self._new_paste_name()

    def _show_qr(self, qr_text: str) -> None:
        qr = self.query_one("#extras-qr", Static)
        qr.update(Content(qr_text.rstrip("\n")))
        qr.add_class("-shown")
        caption = self.query_one("#extras-qr-caption")
        caption.add_class("-shown")
        # In a short window the code lands below the fold.
        self.call_after_refresh(caption.scroll_visible, animate=False)

    def _offer_image(self, path: Path) -> None:
        self._saved_image = path
        button = self.query_one("#extras-open-image", Button)
        button.label = f"Open {path.name} on the Images page ({SECTION_KEYS['images']})"
        button.add_class("-shown")

    @on(Button.Pressed, "#extras-open-image")
    def _on_open_image(self, event: Button.Pressed) -> None:
        event.stop()
        if self._saved_image is not None:
            self.post_message(OpenFile("images", self._saved_image))
