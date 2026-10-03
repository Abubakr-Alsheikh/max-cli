"""A searchable list of a provider's models, for the Settings page.

Type to filter (every word must match), move with up and down, Enter picks
the highlighted model. A name that isn't in the list can be typed and
picked with Enter too, for a model the list doesn't show. Esc cancels.
"""

from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

MAX_SHOWN = 300  # options in the list at once; search narrows the rest


def matches(name: str, query: str) -> bool:
    """Every word of `query` is in `name`, ignoring case."""
    folded = name.casefold()
    return all(word in folded for word in query.casefold().split())


class ModelPicker(ModalScreen[Optional[str]]):
    """Pick a model by name; returns it, or None when cancelled."""

    DEFAULT_CSS = """
    ModelPicker {
        align: center middle;
    }
    #mp-box {
        width: 72;
        max-width: 95%;
        height: auto;
        max-height: 85%;
        padding: 1 2;
        background: $surface;
        border: round $primary;
    }
    #mp-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    #mp-list {
        height: 16;
        margin-top: 1;
    }
    #mp-hint {
        color: $text-muted;
        margin-top: 1;
    }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, models: list[str], current: str = "") -> None:
        super().__init__()
        self._heading = title
        self._models = models
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="mp-box"):
            yield Static(self._heading, id="mp-title")
            yield Input(placeholder="Search, or type any model name", id="mp-search")
            yield OptionList(id="mp-list")
            yield Static("", id="mp-hint")

    def on_mount(self) -> None:
        self._show("")
        self.query_one("#mp-search", Input).focus()

    def _show(self, query: str) -> None:
        found = [name for name in self._models if matches(name, query)]
        options = self.query_one("#mp-list", OptionList)
        options.clear_options()
        options.add_options([Option(name, id=name) for name in found[:MAX_SHOWN]])
        if found:
            current = found.index(self._current) if self._current in found else 0
            options.highlighted = min(current, MAX_SHOWN - 1)
        typed = query.strip()
        if found:
            hint = f"{len(found)} of {len(self._models)} models  ·  Enter picks"
        elif typed:
            hint = f'No match: Enter uses "{typed}"'
        else:
            hint = "No models listed: type a model name"
        self.query_one("#mp-hint", Static).update(hint + "  ·  Esc cancels")

    @on(Input.Changed, "#mp-search")
    def _on_search(self, event: Input.Changed) -> None:
        self._show(event.value)

    def on_key(self, event: Key) -> None:
        """Up and down in the search box move through the list."""
        if self.focused is not self.query_one("#mp-search", Input):
            return
        options = self.query_one("#mp-list", OptionList)
        if event.key == "down":
            options.action_cursor_down()
            event.stop()
        elif event.key == "up":
            options.action_cursor_up()
            event.stop()

    @on(Input.Submitted, "#mp-search")
    def _on_submit(self, event: Input.Submitted) -> None:
        options = self.query_one("#mp-list", OptionList)
        if options.highlighted is not None and options.option_count:
            option = options.get_option_at_index(options.highlighted)
            self.dismiss(str(option.id))
        elif event.value.strip():
            self.dismiss(event.value.strip())

    @on(OptionList.OptionSelected, "#mp-list")
    def _on_pick(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(str(event.option.id))

    def action_cancel(self) -> None:
        self.dismiss(None)
