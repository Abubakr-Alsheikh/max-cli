"""A form built from a catalog action (PLANS/active/command-catalog.md, build step 2).

Every option the CLI command has appears here with the same default. Advanced
options fold away, help sits under each field, and path fields get a Browse
button. The action runs in a thread worker, so the dashboard never freezes.
"""

from collections.abc import Collection
from pathlib import Path
from typing import Any, Literal, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.content import Content
from textual.message import Message
from textual.widget import Widget
from textual.widgets import (
    Button,
    Checkbox,
    Collapsible,
    Input,
    Label,
    Select,
    Static,
    Switch,
)

from max_cli.common.activity_log import ActivityLog
from max_cli.common.exceptions import MaxError
from max_cli.core.catalog.spec import (
    LIST_SEPARATOR,
    PATH_KINDS,
    Action,
    Danger,
    Param,
    ParamKind,
)
from max_cli.core.operations.result import ActionResult
from max_cli.interface.tui.text import markup

CONFIRM_DANGERS = frozenset({Danger.MOVES, Danger.OVERWRITES, Danger.DELETES})
DANGER_NOTES = {
    Danger.MOVES: "moves or renames files",
    Danger.OVERWRITES: "overwrites files in place",
    Danger.DELETES: "deletes files",
}
# Asked even with CONFIRM_DESTRUCTIVE off: nothing can bring the file back.
ALWAYS_CONFIRM = frozenset({"files.shred"})


def _field_label(param: Param) -> str:
    label = param.name.replace("_", " ").capitalize()
    return f"{label} [red]*[/red]" if param.required else label


def asks_first(action: Action) -> bool:
    """Whether Run asks before it starts: the action changes files, and
    CONFIRM_DESTRUCTIVE is on (or the action can't be undone)."""
    from max_cli.config import settings

    if action.danger not in CONFIRM_DANGERS:
        return False
    return settings.CONFIRM_DESTRUCTIVE or action.id in ALWAYS_CONFIRM


def _initial_text(param: Param) -> str:
    if param.required:
        return ""
    default = param.resolved_default()
    if default is None:
        return ""
    if param.multiple and isinstance(default, (list, tuple)):
        return f"{LIST_SEPARATOR} ".join(str(item) for item in default)
    return str(default)


class ActionForm(Vertical):
    """One catalog action as a form with Run (and Add to queue) buttons."""

    class Finished(Message):
        """Run finished: the page can show what it made (a QR code, a file)."""

        def __init__(self, action: Action, result: ActionResult) -> None:
            super().__init__()
            self.action = action
            self.result = result

    DEFAULT_CSS = """
    ActionForm {
        height: auto;
        padding: 0 1;
    }
    ActionForm .form-title {
        text-style: bold;
        color: $accent;
    }
    ActionForm .form-danger {
        color: $warning;
    }
    ActionForm .form-field {
        height: auto;
        width: 1fr;
        margin-top: 1;
    }
    ActionForm .form-help {
        color: $text-muted;
        width: 1fr;
        height: auto;
    }
    ActionForm .path-row {
        height: auto;
    }
    ActionForm .path-row Input {
        width: 1fr;
    }
    ActionForm .path-row Button {
        min-width: 10;
    }
    ActionForm .form-buttons {
        height: auto;
        margin-top: 1;
    }
    ActionForm .form-status {
        margin-top: 1;
    }
    ActionForm .form-grid, ActionForm .form-toggles {
        grid-size: 2;
        grid-gutter: 0 2;
        grid-rows: auto;
        height: auto;
    }
    ActionForm .form-grid .form-field {
        margin-top: 0;
    }
    ActionForm .form-toggles {
        margin-top: 1;
    }
    ActionForm .form-toggles Checkbox {
        width: 1fr;
        border: none;
        padding: 0;
        background: transparent;
    }
    ActionForm .form-toggles Checkbox:focus {
        text-style: bold;
        color: $accent;
    }
    ActionForm .form-toggles Checkbox > .toggle--button {
        color: $border;
        background: $boost;
    }
    ActionForm .form-toggles Checkbox.-on > .toggle--button {
        color: $success;
        background: $boost;
    }
    """

    def __init__(
        self,
        action: Action,
        include: Optional[Collection[str]] = None,
        embedded: bool = False,
        compact: bool = False,
        **kwargs: Any,
    ) -> None:
        """`include` limits the form to those parameters, in the catalog's order.

        An `embedded` form has no title and no buttons: a page places it
        inside its own layout and reads `values()` itself. A `compact` form is
        embedded and fits in a few rows: fields two to a row, on/off options
        as checkboxes beside their names, and each help text in a tooltip.
        """
        super().__init__(**kwargs)
        self.action = action
        self.embedded = embedded or compact
        self.compact = compact
        self.params = tuple(
            param for param in action.params if include is None or param.name in include
        )

    def compose(self) -> ComposeResult:
        action = self.action
        if self.compact:
            yield from self._compact_fields()
            return
        if self.embedded:
            for param in self.params:
                yield self._field(param)
            return
        yield Static(
            f"max {action.group} {action.name}: {action.summary}", classes="form-title"
        )
        if action.danger in CONFIRM_DANGERS:
            ask = " You'll be asked first." if asks_first(action) else ""
            yield Static(
                f"Careful: this {DANGER_NOTES[action.danger]}.{ask}",
                classes="form-danger",
            )
        basic = [param for param in self.params if not param.advanced]
        advanced = [param for param in self.params if param.advanced]
        for param in basic:
            yield self._field(param)
        if action.each_param() is not None:
            # Several files, a folder or a pattern: how far to look, and
            # whether to run files whose result exists already.
            boxes = [Checkbox("Subfolders too", id="batch-recursive")]
            if action.output_name:
                boxes.append(Checkbox("Redo finished files", id="batch-redo"))
            yield Grid(*boxes, classes="form-toggles")
        if advanced:
            with Collapsible(title="More options", collapsed=True):
                for param in advanced:
                    yield self._field(param)
        with Horizontal(classes="form-buttons"):
            yield Button("Run", id="form-run", variant="success")
            if action.queueable:
                yield Button("Add to queue", id="form-queue", variant="primary")
        yield Static("", id="form-status", classes="form-status")

    def _compact_fields(self) -> ComposeResult:
        toggles = [param for param in self.params if param.kind == ParamKind.BOOL]
        others = [param for param in self.params if param.kind != ParamKind.BOOL]
        if others:
            fields = []
            for param in others:
                field = Vertical(
                    Label(_field_label(param)), self._input(param), classes="form-field"
                )
                field.tooltip = param.help
                fields.append(field)
            yield Grid(*fields, classes="form-grid")
        if toggles:
            boxes = []
            for param in toggles:
                box = Checkbox(
                    _field_label(param),
                    value=param.resolved_default() is True,
                    id=f"field-{param.name}",
                )
                box.tooltip = param.help
                boxes.append(box)
            yield Grid(*boxes, classes="form-toggles")

    def _field(self, param: Param) -> Vertical:
        return Vertical(
            Label(_field_label(param)),
            self._input(param),
            Static(Content(param.help), classes="form-help"),
            classes="form-field",
        )

    def _input(self, param: Param) -> Widget:
        widget_id = f"field-{param.name}"
        default = None if param.required else param.resolved_default()
        if param.kind == ParamKind.BOOL:
            return Switch(value=default is True, id=widget_id)
        if param.kind == ParamKind.CHOICE:
            options = [(choice, choice) for choice in param.choices]
            if default in param.choices:
                return Select(options, value=default, allow_blank=False, id=widget_id)
            # No value: Select starts empty. Passing Select.BLANK crashed on
            # Textual 8, where it is False and Select.NULL marks "empty".
            return Select(options, allow_blank=True, id=widget_id)
        input_type: Literal["integer", "number", "text"] = "text"
        if param.kind == ParamKind.INT:
            input_type = "integer"
        elif param.kind == ParamKind.FLOAT:
            input_type = "number"
        placeholder = "Required" if param.required else "Optional"
        if param.multiple:
            placeholder += f"; separate several with {LIST_SEPARATOR}"
        elif param.each:
            placeholder += (
                f": a file, several split by {LIST_SEPARATOR}, a folder or *.mp4"
            )
        text_input = Input(
            value=_initial_text(param),
            placeholder=placeholder,
            type=input_type,
            password=param.kind == ParamKind.SECRET,
            id=widget_id,
        )
        if param.kind in PATH_KINDS:
            return Horizontal(
                text_input,
                Button("Browse", id=f"browse-{param.name}"),
                classes="path-row",
            )
        return text_input

    def values(self) -> dict[str, Any]:
        """What the user entered, keyed by parameter name. Blank means default."""
        values: dict[str, Any] = {}
        for param in self.params:
            widget = self.query_one(f"#field-{param.name}")
            if isinstance(widget, (Switch, Checkbox)):
                values[param.name] = widget.value
            elif isinstance(widget, Select):
                values[param.name] = None if widget.is_blank() else widget.value
            elif isinstance(widget, Input):
                values[param.name] = widget.value
        return values

    def set_value(self, name: str, value: Any) -> None:
        """Fill a field from outside, e.g. the Files page passing the selected file."""
        widget = self.query_one(f"#field-{name}")
        if isinstance(widget, Input):
            widget.value = str(value)
        elif isinstance(widget, (Switch, Checkbox)):
            widget.value = bool(value)
        elif isinstance(widget, Select):
            widget.value = value

    def _set_status(self, text: "str | Content") -> None:
        self.query_one("#form-status", Static).update(text)

    def _set_busy(self, busy: bool) -> None:
        for button in self.query(".form-buttons Button"):
            button.disabled = busy

    # --- browse -------------------------------------------------------------

    @on(Button.Pressed)
    def _on_browse(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if not button_id.startswith("browse-"):
            return
        event.stop()
        param = self.action.param(button_id[len("browse-") :])
        field = self.query_one(f"#field-{param.name}", Input)
        # A list field opens at its last path.
        typed = field.value.split(LIST_SEPARATOR)[-1].strip()
        start = Path(typed) if typed else None

        def _picked(path: Optional[Path]) -> None:
            if path is None:
                return
            if param.multiple and field.value.strip():
                # Browse adds to a list instead of replacing it.
                field.value = f"{field.value.rstrip().rstrip(LIST_SEPARATOR)}{LIST_SEPARATOR} {path}"
            else:
                field.value = str(path)

        from max_cli.interface.tui.widgets.path_picker import PathPicker, PickMode

        mode = {
            ParamKind.FOLDER: PickMode.FOLDER,
            ParamKind.OUTPUT: PickMode.SAVE,
        }.get(param.kind, PickMode.FILE)
        self.app.push_screen(
            PathPicker(start, mode, file_types=self.action.group), _picked
        )

    # --- run and queue ------------------------------------------------------

    @on(Button.Pressed, "#form-run")
    def _on_run(self, event: Button.Pressed) -> None:
        event.stop()
        self._submit(queue=False)

    @on(Button.Pressed, "#form-queue")
    def _on_queue(self, event: Button.Pressed) -> None:
        event.stop()
        self._submit(queue=True)

    def batch_options(self) -> tuple[bool, bool]:
        """(subfolders too, redo finished files), off where the form has none."""
        recursive = self._optional_box("batch-recursive")
        redo = self._optional_box("batch-redo")
        return (
            bool(recursive is not None and recursive.value),
            bool(redo is not None and redo.value),
        )

    def _optional_box(self, box_id: str) -> Optional[Checkbox]:
        found = self.query(f"#{box_id}")
        return found.first(Checkbox) if found else None

    def _submit(self, queue: bool) -> None:
        from max_cli.core.catalog.batch import expand_each, is_batch, one_file
        from max_cli.core.catalog.runner import coerce_args

        values = self.values()
        many = is_batch(self.action, values)
        try:
            if many:
                found = expand_each(self.action, values, *self.batch_options())
            coerce_args(
                self.action,
                one_file(self.action, values) if self.action.each_param() else values,
            )
        except MaxError as e:
            self._set_status(markup("[red]$error[/red]", error=e))
            return
        if many and not found.files:
            self._set_status(
                f"[green]Nothing to do:[/green] all {found.total} files have their "
                "result already. Tick Redo finished files to run them again."
            )
            return

        if not asks_first(self.action):
            self._start(values, queue)
            return

        def _answered(confirmed: Optional[bool]) -> None:
            if confirmed:
                self._start(values, queue)
            else:
                self._set_status("[dim]Cancelled.[/dim]")

        from max_cli.interface.tui.widgets.dialogs import ConfirmDialog

        note = DANGER_NOTES[self.action.danger]
        files = f" on {len(found.files)} files" if many else ""
        self.app.push_screen(
            ConfirmDialog(
                f"max {self.action.group} {self.action.name}{files} {note}. Continue?"
            ),
            _answered,
        )

    def _start(self, values: dict[str, Any], queue: bool) -> None:
        if queue:
            self._enqueue(values)
            return
        self._set_busy(True)
        self._set_status("[cyan]Running...[/cyan]")
        options = self.batch_options()
        self.run_worker(
            lambda: self._run(values, *options), thread=True, group="action-form"
        )

    def _enqueue(self, values: dict[str, Any]) -> None:
        from max_cli.core.catalog.batch import enqueue_each

        try:
            tasks, _found = enqueue_each(self.action, values, *self.batch_options())
        except MaxError as e:
            self._set_status(markup("[red]$error[/red]", error=e))
            return
        if len(tasks) == 1:
            self._set_status(
                f"[green]Queued[/green] (ID: {tasks[0].id}). J shows its progress."
            )
        else:
            self._set_status(
                f"[green]Queued {len(tasks)} jobs[/green], one per file. J shows them."
            )
        self.notify(f"Queued {self.action.group} {self.action.name}")
        from max_cli.interface.tui.widgets.jobs_drawer import JobsDrawer

        self.post_message(JobsDrawer.Show())

    def _run(
        self, values: dict[str, Any], recursive: bool = False, redo: bool = False
    ) -> None:
        """Runs in a thread worker; the UI updates go through call_from_thread.
        Several files run side by side (catalog.batch); one runs as before."""
        from max_cli.core.catalog.batch import run_each

        activity = ActivityLog()
        entry = activity.start_entry(
            category=self.action.group,
            action=self.action.name,
            details={"args": {k: str(v) for k, v in values.items()}},
        )
        finished = 0

        def on_file(path: Path, result: Any, error: str) -> None:
            nonlocal finished
            finished += 1
            self.app.call_from_thread(
                self._set_status, f"[cyan]Running...[/cyan] {finished} files done"
            )

        try:
            if self.action.each_param() is not None:
                result = run_each(self.action, values, recursive, redo, on_file=on_file)
            else:
                from max_cli.core.catalog.runner import run_action

                result = run_action(self.action, values)
        except Exception as e:
            activity.complete_entry(entry, "failed", {"error": str(e)})
            self.app.call_from_thread(self._finish, False, str(e))
            return
        activity.complete_entry(
            entry, "success" if result.ok else "failed", result.to_dict()
        )
        self.app.call_from_thread(self._finish, result.ok, result.message, result)

    def _finish(
        self, ok: bool, message: str, result: Optional[ActionResult] = None
    ) -> None:
        self._set_busy(False)
        if result is not None:
            self.post_message(self.Finished(self.action, result))
        if ok:
            self._set_status(markup("[green]Done.[/green] $message", message=message))
            self.notify(message)
        else:
            self._set_status(markup("[red]Failed:[/red] $message", message=message))
            self.notify(message, severity="error")
