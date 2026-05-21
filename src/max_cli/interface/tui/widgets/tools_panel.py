"""Command launcher panel with dynamic forms."""

from typing import Any

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, Checkbox, Input, Label, Select, Static, Tree


class ToolsPanel(Vertical):
    """Command launcher with category tree and dynamic form."""

    def compose(self) -> ComposeResult:
        yield Static("[bold cyan]Tools & Commands[/bold cyan]", id="tools-title")

        with Horizontal(id="tools-layout"):
            with Vertical(id="tools-tree-panel"):
                yield Static("[bold]Categories[/bold]", id="tree-title")
                tree: Tree[str] = Tree("Commands", id="tools-tree")
                yield tree

            with ScrollableContainer(id="tools-form-scroll"):
                with Vertical(id="tools-form-panel"):
                    yield Static(
                        "[dim]Select a command to begin[/dim]", id="tools-placeholder"
                    )

    def on_mount(self) -> None:
        self._build_tree()

    def _build_tree(self) -> None:
        from max_cli.interface.tui.command_registry import CommandRegistry

        tree = self.query_one("#tools-tree", Tree)
        registry = CommandRegistry.get_all_commands()

        for category, commands in registry.items():
            cat_node = tree.root.add(f"  {category.title()}", data=category)
            for cmd_name, cmd_schema in commands.items():
                icon = cmd_schema.get("icon", "\u2022")
                label = cmd_schema.get("label", cmd_name)
                cat_node.add(f"{icon} {label}", data=f"{category}:{cmd_name}")

        tree.root.expand_all()

    @on(Tree.NodeSelected, "#tools-tree")
    def _on_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if not data or ":" not in str(data):
            return

        category, command = str(data).split(":", 1)
        self._build_form(category, command)

    def _build_form(self, category: str, command: str) -> None:
        from max_cli.interface.tui.command_registry import CommandRegistry

        schema = CommandRegistry.get_command(category, command)
        if not schema:
            return

        form_panel = self.query_one("#tools-form-panel", Vertical)
        form_panel.remove_children()

        placeholder = self.query_one("#tools-placeholder", Static)
        placeholder.remove()

        form_panel.mount(
            Static(
                f"[bold cyan]{schema['icon']} {schema['label']}[/bold cyan]",
                id="form-title",
            ),
        )
        form_panel.mount(
            Static("[dim]" + schema.get("description", "") + "[/dim]", id="form-desc"),
        )
        form_panel.mount(Static("\u2500" * 50, id="form-divider"))

        for field in schema["fields"]:
            field_id = f"field-{field['name']}"
            required_marker = " *" if field.get("required") else ""
            label_text = f"{field['label']}{required_marker}:"
            form_panel.mount(Label(label_text, id=f"label-{field_id}"))

            field_type = field.get("type", "str")

            if field_type == "bool":
                widget: Any = Checkbox(
                    label=field["label"],
                    value=bool(field.get("default", False)),
                    id=field_id,
                )
            elif field_type == "select":
                options = [(opt, opt) for opt in field.get("options") or []]
                default_val = field.get("default")
                widget = Select(
                    options=options,
                    value=default_val if default_val else Select.BLANK,
                    id=field_id,
                    allow_blank=False,
                )
            elif field_type in ("int", "float"):
                input_type = "integer" if field_type == "int" else "number"
                widget = Input(
                    value=str(field.get("default", "")),
                    type=input_type,  # type: ignore[arg-type]
                    placeholder=field.get("help", ""),
                    id=field_id,
                )
            else:
                default = str(field.get("default", ""))
                widget = Input(
                    value=default,
                    placeholder=field.get("help", ""),
                    id=field_id,
                )

            form_panel.mount(widget)

        with Horizontal(id="form-actions"):
            exec_btn = Button("Execute", id="btn-execute", variant="success")
            form_panel.mount(exec_btn)

            if schema.get("has_queue_option"):
                queue_btn = Button("Add to Queue", id="btn-queue", variant="primary")
                form_panel.mount(queue_btn)

        form_panel.mount(Static("Status: Ready", id="form-status"))
        form_panel.mount(Static("", id="form-result"))

        self.query_one("#tools-form-scroll", ScrollableContainer).scroll_home()

    @on(Button.Pressed, "#btn-execute")
    def _on_execute(self) -> None:
        self._run_command(queue=False)

    @on(Button.Pressed, "#btn-queue")
    def _on_queue(self) -> None:
        self._run_command(queue=True)

    def _run_command(self, queue: bool) -> None:
        from max_cli.interface.tui.command_executor import CommandExecutor
        from max_cli.interface.tui.command_registry import CommandRegistry

        title_widget = self.query_one("#form-title", Static)
        category, command = self._parse_title(title_widget.renderable)  # type: ignore[attr-defined]

        values = self._collect_form_values()

        schema = CommandRegistry.get_command(category, command)
        if not schema:
            self._set_form_status("Error: Command not found", "error")
            return

        valid, errors = CommandRegistry.validate_fields(schema, values)
        if not valid:
            self._set_form_status(f"Error: {'; '.join(errors)}", "error")
            return

        self._set_form_status("Executing...", "info")

        executor = CommandExecutor()
        try:
            result = executor.execute(
                category=category,
                command=command,
                values=values,
                queue=queue,
            )

            if result.success:
                status_msg = "Queued" if queue else "Success"
                self._set_form_status(f"{status_msg}: {result.message}", "success")
                result_widget = self.query_one("#form-result", Static)
                if result.output_files:
                    output_text = "Output:\n" + "\n".join(
                        f"  {f}" for f in result.output_files
                    )
                    result_widget.update(output_text)
            else:
                self._set_form_status(f"Failed: {result.error}", "error")

        except Exception as e:
            self._set_form_status(f"Error: {e}", "error")

    def _collect_form_values(self) -> dict[str, Any]:
        from max_cli.interface.tui.command_registry import CommandRegistry

        title_widget = self.query_one("#form-title", Static)
        category, command = self._parse_title(title_widget.renderable)  # type: ignore[attr-defined]

        schema = CommandRegistry.get_command(category, command)
        if not schema:
            return {}

        values: dict[str, Any] = {}
        for field in schema["fields"]:
            field_id = f"field-{field['name']}"
            try:
                widget = self.query_one(f"#{field_id}")
                if isinstance(widget, Checkbox):
                    values[field["name"]] = widget.value
                elif isinstance(widget, Select):
                    val = widget.value
                    values[field["name"]] = (
                        val if val != Select.BLANK else field.get("default")
                    )
                elif isinstance(widget, Input):
                    raw = widget.value.strip()
                    if field["type"] == "int" and raw:
                        values[field["name"]] = int(raw)
                    elif field["type"] == "float" and raw:
                        values[field["name"]] = float(raw)
                    else:
                        values[field["name"]] = raw
            except Exception:
                values[field["name"]] = field.get("default")
        return values

    def _set_form_status(self, message: str, level: str) -> None:
        status = self.query_one("#form-status", Static)
        colors = {
            "success": "green",
            "error": "red",
            "info": "cyan",
            "warning": "yellow",
        }
        color = colors.get(level, "white")
        status.update(f"[{color}]Status: {message}[/{color}]")

    def _parse_title(self, title: Any) -> tuple[str, str]:
        from max_cli.interface.tui.command_registry import CommandRegistry

        title_str = (
            str(title).replace("[bold cyan]", "").replace("[/bold cyan]", "").strip()
        )
        registry = CommandRegistry.get_all_commands()
        for category, commands in registry.items():
            for cmd_name, cmd_schema in commands.items():
                if cmd_schema.get("label") == title_str:
                    return category, cmd_name
        return "", ""
