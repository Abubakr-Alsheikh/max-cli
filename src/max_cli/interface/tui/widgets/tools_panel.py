"""Tools page: pick a command group and an action, then fill in its form.

The list and the forms come from the command catalog (`core/catalog`), so
every ported group appears here with the same options as its CLI command.
"""

from typing import Any, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import OptionList, Select, Static
from textual.widgets.option_list import Option

from max_cli.core.catalog import actions_for, get_action, group_names, load_group
from max_cli.core.catalog.spec import Action, Surface
from max_cli.interface.tui.widgets.action_form import ActionForm


def _dashboard_groups() -> list[str]:
    return [name for name in group_names() if actions_for(name, Surface.DASHBOARD)]


class ToolsPanel(Vertical):
    """Every catalog action the dashboard may run, one form at a time."""

    DEFAULT_CSS = """
    #tools-body {
        height: auto;
    }
    #tools-picker {
        width: 34;
        height: auto;
        margin-right: 2;
    }
    #tools-actions {
        height: auto;
        max-height: 24;
        margin-top: 1;
    }
    #tools-form-area {
        width: 1fr;
        height: auto;
    }
    #tools-group-help {
        color: $text-muted;
        margin-top: 1;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._group: Optional[str] = None

    def compose(self) -> ComposeResult:
        groups = _dashboard_groups()
        yield Static("[bold cyan]Tools[/bold cyan]", id="tools-title")
        yield Static(
            "[dim]Choose a group and an action. Every option matches the "
            "`max` command of the same name.[/dim]"
        )
        with Horizontal(id="tools-body"):
            with Vertical(id="tools-picker"):
                yield Select(
                    [(name, name) for name in groups],
                    value=groups[0] if groups else Select.BLANK,
                    allow_blank=not groups,
                    id="tools-group",
                )
                yield Static("", id="tools-group-help")
                yield OptionList(id="tools-actions")
            yield Vertical(
                Static("[dim]Pick an action on the left.[/dim]"),
                id="tools-form-area",
            )

    def on_mount(self) -> None:
        select = self.query_one("#tools-group", Select)
        if not select.is_blank():
            self._show_group(str(select.value))

    def _show_group(self, group_name: str) -> None:
        self._group = group_name
        self.query_one("#tools-group-help", Static).update(
            f"[dim]{load_group(group_name).summary}[/dim]"
        )
        option_list = self.query_one("#tools-actions", OptionList)
        option_list.clear_options()
        option_list.add_options(
            Option(f"{action.name}  [dim]{action.summary}[/dim]", id=action.id)
            for action in actions_for(group_name, Surface.DASHBOARD)
        )

    @on(Select.Changed, "#tools-group")
    def _on_group(self, event: Select.Changed) -> None:
        if event.value != Select.BLANK:
            self._show_group(str(event.value))

    @on(OptionList.OptionSelected, "#tools-actions")
    def _on_action(self, event: OptionList.OptionSelected) -> None:
        if event.option.id:
            self.show_action(get_action(event.option.id))

    def show_action(self, action: Action, **values: Any) -> ActionForm:
        """Show `action`'s form, filling any `values` given (e.g. a selected file)."""
        area = self.query_one("#tools-form-area", Vertical)
        area.remove_children()
        form = ActionForm(action)
        area.mount(form)

        def _fill() -> None:
            for name, value in values.items():
                form.set_value(name, value)

        self.call_after_refresh(_fill)
        return form

    def open_action(self, action_id: str, **values: Any) -> None:
        """Jump to an action from another page: select its group, show its form."""
        action = get_action(action_id)
        select = self.query_one("#tools-group", Select)
        if select.value != action.group:
            select.value = action.group
            self._show_group(action.group)
        self.show_action(action, **values)
