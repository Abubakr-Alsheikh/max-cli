"""One page per command group: pick a file, see what it is, pick an action.

The Video, Images, PDF, Files and Audio pages share this layout. Each is a
`ToolPageSpec`: its catalog group, a header, its actions in named sections,
and a function that describes a picked file (`interface/tui/tool_pages.py`).

- FILE: a path box with Browse. A picked file is described in a thread
  worker (ffprobe for video, page count for PDF ...) and fills the chosen
  action's file field. A file another page works on (a PDF picked on the
  Files page) gets a button that opens it there.
- ACTIONS: the group's actions as buttons, in sections.
- The chosen action's form, built from the catalog (`ActionForm`), with
  Run and, where the action allows it, Add to queue.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.content import Content
from textual.css.query import NoMatches
from textual.timer import Timer
from textual.widgets import Button, Input, Label, Static

from max_cli.common.file_kinds import kind_of
from max_cli.core.catalog import get_action
from max_cli.core.catalog.spec import Action, ParamKind
from max_cli.interface.tui.messages import OpenFile
from max_cli.interface.tui.widgets.action_form import ActionForm
from max_cli.interface.tui.widgets.sidebar import SECTION_KEYS, SECTIONS
from max_cli.interface.tui.workers import show_from_worker

DESCRIBE_DELAY_SECONDS = 0.4
MAX_CHIP_COLUMNS = 3
CHIP_GUTTER = 1
CHIP_BORDER = 2  # a chip's left and right border
# Folder params an action writes to; the picked path never goes there.
OUTPUT_FOLDER_NAMES = frozenset({"output", "output_dir"})
PAGE_LABELS = {section_id: label for section_id, _icon, label in SECTIONS}


@dataclass(frozen=True)
class ToolSection:
    title: str
    actions: tuple[str, ...]  # action names in the page's group


@dataclass(frozen=True)
class ToolPageSpec:
    page_id: str  # the sidebar id; the widget is #<page_id>-panel
    group: str  # catalog group
    title: str  # VIDEO
    tagline: str  # FFMPEG STUDIO
    hint: str  # the header's second line
    file_prompt: str  # the path box's placeholder
    sections: tuple[ToolSection, ...]
    # Runs in a thread: the facts line for a picked file. Raises MaxError for
    # a file it can't read.
    describe: Callable[[Path], Content]
    file_title: str = "FILE"  # the path card's title: "FILE OR FOLDER" ...
    # File kinds (common/file_kinds) this page is the place for. Another
    # page offers to open such a file here.
    kinds: tuple[str, ...] = ()
    # Actions whose path fields aren't for the picked file (files.backups
    # takes a backup to restore).
    no_fill: tuple[str, ...] = ()


def file_param(action: Action) -> Optional[str]:
    """The parameter that takes the picked path: the first input file, else
    the first folder the action reads (not one it writes to)."""
    for kind in (ParamKind.FILE, ParamKind.FOLDER):
        for param in action.params:
            if param.kind == kind and param.name not in OUTPUT_FOLDER_NAMES:
                return param.name
    return None


class ToolPage(Vertical):
    """A command group's page, set up by a ToolPageSpec."""

    DEFAULT_CSS = """
    ToolPage .tool-header {
        height: 3;
        margin-bottom: 1;
    }
    ToolPage .tool-card {
        height: auto;
        background: $surface;
        border: round $border;
        border-title-color: $primary;
        border-title-style: bold;
        padding: 0 1;
        margin-bottom: 1;
    }
    ToolPage .tool-card:focus-within {
        border: round $primary;
    }
    ToolPage .tool-file-row {
        height: auto;
    }
    ToolPage .tool-file-row Input {
        width: 1fr;
    }
    ToolPage .tool-facts {
        height: auto;
        margin-bottom: 1;
    }
    ToolPage #tool-open-page {
        display: none;
        height: 1;
        min-width: 10;
        border: none;
        padding: 0 1;
        margin-bottom: 1;
        background: $primary 20%;
        color: $primary;
        text-style: bold;
    }
    ToolPage #tool-open-page.-offered {
        display: block;
    }
    ToolPage #tool-open-page:hover {
        background: $primary 40%;
    }
    ToolPage .tool-main {
        height: auto;
        grid-size: 2;
        grid-columns: 2fr 3fr;
        grid-gutter: 0 2;
    }
    ToolPage .section-caption {
        color: $text-muted;
        text-style: bold;
        margin-top: 1;
    }
    ToolPage .section-chips {
        height: auto;
        grid-size: 3;
        grid-gutter: 0 1;
        grid-rows: 3;
    }
    ToolPage .chip {
        width: 100%;
        min-width: 8;
        margin: 0;
        padding: 0;
        border: tall $boost;
        background: $boost;
    }
    ToolPage .chip:hover {
        border: tall $primary 60%;
    }
    ToolPage .chip.-selected {
        background: $primary 25%;
        color: $primary;
        text-style: bold;
        border: tall $primary;
    }
    ToolPage .tool-actions-card {
        padding-bottom: 1;
    }
    ToolPage ActionForm {
        padding: 0;
        margin-bottom: 1;
    }
    """

    def __init__(self, spec: ToolPageSpec, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.spec = spec
        self._action: Optional[Action] = None
        # The form on show now. A replaced form stays in the DOM until Textual
        # finishes removing it, so querying for ActionForm can find the old one.
        self._form: Optional[ActionForm] = None
        self._describe_timer: Optional[Timer] = None
        self._described = ""  # the path the facts line belongs to
        self._offered_page = ""  # the page the open-on button goes to

    # --- layout -------------------------------------------------------------

    def compose(self) -> ComposeResult:
        spec = self.spec
        yield Static(self._brand(), classes="tool-header")
        with Vertical(classes="tool-card tool-file-card") as file_card:
            file_card.border_title = spec.file_title
            with Horizontal(classes="tool-file-row"):
                yield Input(placeholder=spec.file_prompt, id="tool-file")
                yield Button("Browse...", id="tool-browse")
            yield Static(
                Content.styled(
                    "Pick a file to see what it holds. Every action below can "
                    "also take a path of its own.",
                    "$text-muted",
                ),
                classes="tool-facts",
                id="tool-facts",
            )
            yield Button("", id="tool-open-page")
        with Grid(classes="tool-main"):
            with Vertical(classes="tool-card tool-actions-card") as actions_card:
                actions_card.border_title = "ACTIONS"
                for section in spec.sections:
                    yield Label(section.title, classes="section-caption")
                    with Grid(classes="section-chips"):
                        for name in section.actions:
                            yield Button(name, id=f"act-{name}", classes="chip")
            with Vertical(classes="tool-card tool-form-card", id="tool-form-card"):
                yield Static("")

    def _brand(self) -> Content:
        return Content.assemble(
            ("◢◤ ", "bold $secondary"),
            (self.spec.title, "bold $primary"),
            (f" // {self.spec.tagline}\n", "bold"),
            (self.spec.hint, "$text-muted"),
        )

    def on_mount(self) -> None:
        first = self.spec.sections[0].actions[0]
        self.show_action(first)

    def on_resize(self) -> None:
        self.call_after_refresh(self._fit_chips)

    def _fit_chips(self) -> None:
        """As many chip columns as fit the longest action name: in a narrow
        window three columns cut "backup-cleanup" to "backup-clea"."""
        grids = list(self.query(".section-chips").results(Grid))
        if not grids:
            return
        longest = max(
            len(name) for section in self.spec.sections for name in section.actions
        )
        chip_width = longest + CHIP_BORDER
        width = grids[0].content_region.width
        columns = max(
            1,
            min(MAX_CHIP_COLUMNS, (width + CHIP_GUTTER) // (chip_width + CHIP_GUTTER)),
        )
        for grid in grids:
            if grid.styles.grid_size_columns != columns:
                grid.styles.grid_size_columns = columns

    # --- actions ------------------------------------------------------------

    @property
    def action(self) -> Optional[Action]:
        return self._action

    @property
    def form(self) -> Optional[ActionForm]:
        return self._form

    def show_action(self, name: str, **values: Any) -> ActionForm:
        """Show `name`'s form, with the picked file and any `values` filled in."""
        action = get_action(f"{self.spec.group}.{name}")
        self._action = action
        for chip in self.query(".chip"):
            chip.set_class(chip.id == f"act-{name}", "-selected")
        card = self.query_one("#tool-form-card", Vertical)
        card.border_title = name.upper()  # the form's first line gives the summary
        form = ActionForm(action)
        self._form = form
        self.call_later(self._swap_form, card, form, values)
        return form

    async def _swap_form(
        self, card: Vertical, form: ActionForm, values: dict[str, Any]
    ) -> None:
        """Replace the form, then fill it: set_value needs its fields mounted."""
        await card.remove_children()
        await card.mount(form)
        if form is not self._form:
            return  # another action was picked meanwhile
        self._fill_file()
        for key, value in values.items():
            form.set_value(key, value)

    def open_file(self, path: Path) -> None:
        """Pick `path`, as if typed in the FILE box (from another page)."""
        self.query_one("#tool-file", Input).value = str(path)

    @on(Button.Pressed, ".chip")
    def _on_chip(self, event: Button.Pressed) -> None:
        event.stop()
        self.show_action((event.button.id or "").removeprefix("act-"))

    def _fill_file(self) -> None:
        """Put the picked path into the form's input field."""
        path = self.query_one("#tool-file", Input).value.strip()
        action = self._action
        field = (
            file_param(action)
            if action and action.name not in self.spec.no_fill
            else None
        )
        if not path or field is None or self._form is None or action is None:
            return
        picked = Path(path).expanduser()
        if action.param(field).kind == ParamKind.FOLDER and picked.is_file():
            path = str(picked.parent)  # a folder action works on the file's folder
        if self._form.is_mounted:
            try:
                self._form.set_value(field, path)
            except NoMatches:
                pass  # the form is between mount and compose; _swap_form fills it

    # --- file ---------------------------------------------------------------

    @on(Input.Changed, "#tool-file")
    def _on_file_changed(self) -> None:
        self._fill_file()
        if self._describe_timer is not None:
            self._describe_timer.stop()
        self._describe_timer = self.set_timer(DESCRIBE_DELAY_SECONDS, self._describe)

    @on(Input.Submitted, "#tool-file")
    def _describe(self) -> None:
        path = self.query_one("#tool-file", Input).value.strip()
        if not path or path == self._described:
            return
        self._described = path
        self._set_facts(Content.styled("Reading the file...", "$primary"))
        self._offer_page(None)
        self.run_worker(
            lambda: self._describe_in_thread(path),
            thread=True,
            exclusive=True,
            group="describe",
        )

    def _describe_in_thread(self, path: str) -> None:
        from max_cli.common.exceptions import MaxError

        picked = Path(path).expanduser()
        kind = ""
        try:
            facts = self.spec.describe(picked)
            kind = kind_of(picked) if picked.is_file() else ""
        except MaxError as e:
            facts = Content.styled(str(e), "$error")
        show_from_worker(self, self._show_facts, path, facts, kind)

    def _show_facts(self, path: str, facts: Content, kind: str = "") -> None:
        if path == self.query_one("#tool-file", Input).value.strip():
            self._set_facts(facts)
            self._offer_page(self._page_for(kind))

    def _page_for(self, kind: str) -> Optional["ToolPage"]:
        """Another page that is the place for this kind of file."""
        if not kind or kind in self.spec.kinds:
            return None
        return next(
            (page for page in self.app.query(ToolPage) if kind in page.spec.kinds),
            None,
        )

    def _offer_page(self, page: Optional["ToolPage"]) -> None:
        button = self.query_one("#tool-open-page", Button)
        button.set_class(page is not None, "-offered")
        if page is not None:
            page_id = page.spec.page_id
            button.label = (
                f"Open on the {PAGE_LABELS[page_id]} page ({SECTION_KEYS[page_id]})"
            )
        self._offered_page = page.spec.page_id if page is not None else ""

    @on(Button.Pressed, "#tool-open-page")
    def _on_open_page(self, event: Button.Pressed) -> None:
        event.stop()
        path = self.query_one("#tool-file", Input).value.strip()
        if path and self._offered_page:
            self.post_message(OpenFile(self._offered_page, Path(path).expanduser()))

    def _set_facts(self, facts: Content) -> None:
        self.query_one("#tool-facts", Static).update(facts)

    @on(Button.Pressed, "#tool-browse")
    def _on_browse(self) -> None:
        from max_cli.interface.tui.widgets.path_picker import PathPicker

        box = self.query_one("#tool-file", Input)
        start = Path(box.value.strip()) if box.value.strip() else None

        def _picked(path: Optional[Path]) -> None:
            if path is not None:
                box.value = str(path)

        self.app.push_screen(PathPicker(start, file_types=self.spec.group), _picked)
