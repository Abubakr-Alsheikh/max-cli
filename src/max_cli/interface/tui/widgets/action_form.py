"""A form built from a catalog action (PLANS/active/command-catalog.md, build step 2).

Every option the CLI command has appears here with the same default. Advanced
options fold away, help sits under each field, and path fields get a Browse
button. The action runs in a thread worker, so the dashboard never freezes.
"""

from collections.abc import Collection
from pathlib import Path
from typing import Any, Literal, Optional

from rich.markup import escape
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Collapsible, Input, Label, Select, Static, Switch

from max_cli.common.exceptions import MaxError
from max_cli.core.catalog.spec import (
    PATH_KINDS,
    Action,
    Danger,
    Param,
    ParamKind,
)
from max_cli.interface.tui.activity_log import ActivityLog

CONFIRM_DANGERS = frozenset({Danger.MOVES, Danger.OVERWRITES, Danger.DELETES})
DANGER_NOTES = {
    Danger.MOVES: "moves or renames files",
    Danger.OVERWRITES: "overwrites files in place",
    Danger.DELETES: "deletes files",
}


def _field_label(param: Param) -> str:
    label = param.name.replace("_", " ").capitalize()
    return f"{label} [red]*[/red]" if param.required else label


def _initial_text(param: Param) -> str:
    if param.required:
        return ""
    default = param.resolved_default()
    return "" if default is None else str(default)


class ActionForm(Vertical):
    """One catalog action as a form with Run (and Add to queue) buttons."""

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
        margin-top: 1;
    }
    ActionForm .form-help {
        color: $text-muted;
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
    """

    def __init__(
        self,
        action: Action,
        include: Optional[Collection[str]] = None,
        embedded: bool = False,
        **kwargs: Any,
    ) -> None:
        """`include` limits the form to those parameters, in the catalog's order.

        An `embedded` form has no title and no buttons: a page places it
        inside its own layout and reads `values()` itself.
        """
        super().__init__(**kwargs)
        self.action = action
        self.embedded = embedded
        self.params = tuple(
            param for param in action.params if include is None or param.name in include
        )

    def compose(self) -> ComposeResult:
        action = self.action
        if self.embedded:
            for param in self.params:
                yield self._field(param)
            return
        yield Static(
            f"max {action.group} {action.name}: {action.summary}", classes="form-title"
        )
        if action.danger in CONFIRM_DANGERS:
            yield Static(
                f"Careful: this {DANGER_NOTES[action.danger]}. You'll be asked first.",
                classes="form-danger",
            )
        basic = [param for param in self.params if not param.advanced]
        advanced = [param for param in self.params if param.advanced]
        for param in basic:
            yield self._field(param)
        if advanced:
            with Collapsible(title="More options", collapsed=True):
                for param in advanced:
                    yield self._field(param)
        with Horizontal(classes="form-buttons"):
            yield Button("Run", id="form-run", variant="success")
            if action.queueable:
                yield Button("Add to queue", id="form-queue", variant="primary")
        yield Static("", id="form-status", classes="form-status")

    def _field(self, param: Param) -> Vertical:
        return Vertical(
            Label(_field_label(param)),
            self._input(param),
            Static(escape(param.help), classes="form-help"),
            classes="form-field",
        )

    def _input(self, param: Param) -> Widget:
        widget_id = f"field-{param.name}"
        default = None if param.required else param.resolved_default()
        if param.kind == ParamKind.BOOL:
            return Switch(value=default is True, id=widget_id)
        if param.kind == ParamKind.CHOICE:
            has_default = default in param.choices
            return Select(
                [(choice, choice) for choice in param.choices],
                value=default if has_default else Select.BLANK,
                allow_blank=not has_default,
                id=widget_id,
            )
        input_type: Literal["integer", "number", "text"] = "text"
        if param.kind == ParamKind.INT:
            input_type = "integer"
        elif param.kind == ParamKind.FLOAT:
            input_type = "number"
        text_input = Input(
            value=_initial_text(param),
            placeholder="Required" if param.required else "Optional",
            type=input_type,
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
            if isinstance(widget, Switch):
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
        elif isinstance(widget, Switch):
            widget.value = bool(value)
        elif isinstance(widget, Select):
            widget.value = value

    def _set_status(self, text: str) -> None:
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
        current = Path(field.value).expanduser() if field.value else Path.cwd()
        start = current if current.is_dir() else current.parent

        def _picked(path: Optional[Path]) -> None:
            if path is not None:
                field.value = str(path)

        from max_cli.interface.tui.widgets.dialogs import PathPicker

        self.app.push_screen(
            PathPicker(start, pick_folder=param.kind == ParamKind.FOLDER), _picked
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

    def _submit(self, queue: bool) -> None:
        from max_cli.core.catalog.runner import coerce_args

        values = self.values()
        try:
            coerce_args(self.action, values)
        except MaxError as e:
            self._set_status(f"[red]{escape(str(e))}[/red]")
            return

        if self.action.danger not in CONFIRM_DANGERS:
            self._start(values, queue)
            return

        def _answered(confirmed: Optional[bool]) -> None:
            if confirmed:
                self._start(values, queue)
            else:
                self._set_status("[dim]Cancelled.[/dim]")

        from max_cli.interface.tui.widgets.dialogs import ConfirmDialog

        note = DANGER_NOTES[self.action.danger]
        self.app.push_screen(
            ConfirmDialog(
                f"max {self.action.group} {self.action.name} {note}. Continue?"
            ),
            _answered,
        )

    def _start(self, values: dict[str, Any], queue: bool) -> None:
        if queue:
            self._enqueue(values)
            return
        self._set_busy(True)
        self._set_status("[cyan]Running...[/cyan]")
        self.run_worker(lambda: self._run(values), thread=True, group="action-form")

    def _enqueue(self, values: dict[str, Any]) -> None:
        from max_cli.core.catalog.runner import enqueue_action

        try:
            task = enqueue_action(self.action, values)
        except MaxError as e:
            self._set_status(f"[red]{escape(str(e))}[/red]")
            return
        self._set_status(
            f"[green]Queued[/green] (ID: {task.id}). See the Queue page for progress."
        )
        self.notify(f"Queued {self.action.group} {self.action.name}")

    def _run(self, values: dict[str, Any]) -> None:
        """Runs in a thread worker; the UI updates go through call_from_thread."""
        from max_cli.core.catalog.runner import run_action

        activity = ActivityLog()
        entry = activity.start_entry(
            category=self.action.group,
            action=self.action.name,
            details={"args": {k: str(v) for k, v in values.items()}},
        )
        try:
            result = run_action(self.action, values)
        except Exception as e:
            activity.complete_entry(entry, "failed", {"error": str(e)})
            self.app.call_from_thread(self._finish, False, str(e))
            return
        activity.complete_entry(
            entry, "success" if result.ok else "failed", result.to_dict()
        )
        self.app.call_from_thread(self._finish, result.ok, result.message)

    def _finish(self, ok: bool, message: str) -> None:
        self._set_busy(False)
        if ok:
            self._set_status(f"[green]Done.[/green] {escape(message)}")
            self.notify(message)
        else:
            self._set_status(f"[red]Failed:[/red] {escape(message)}")
            self.notify(message, severity="error")
