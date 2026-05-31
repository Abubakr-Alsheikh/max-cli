"""Command launcher panel with dynamic forms."""

from typing import Any, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widget import Widget
from textual.widgets import Button, Checkbox, Input, Select, Static, Tree


class ToolsPanel(Vertical):
    """Command launcher with category tree and dynamic form."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._form_panel: Optional[Vertical] = None

    def compose(self) -> ComposeResult:
        yield Static("[bold cyan]Tools & Commands[/bold cyan]", id="tools-title")

        with Horizontal(id="tools-layout"):
            with Vertical(id="tools-tree-panel"):
                yield Static("[bold]Categories[/bold]", id="tree-title")
                tree: Tree[str] = Tree("Commands", id="tools-tree")
                yield tree

            with ScrollableContainer(id="tools-form-scroll"):
                self._form_panel = Vertical(id="tools-form-panel")
                yield self._form_panel

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

        self._form_panel.remove_children(*list(self._form_panel.children))

        title = Static(
            f"[bold cyan]{schema['icon']} {schema['label']}[/bold cyan]",
            id="form-title",
        )
        desc = Static(
            "[dim]" + schema.get("description", "") + "[/dim]", id="form-desc"
        )
        divider = Static("\u2500" * 50, id="form-divider")
        self._form_panel.mount(title, desc, divider)

        for field in schema["fields"]:
            field_name = field["name"]
            field_id = f"field-{field_name}"
            required_marker = " [bold red]*[/bold red]" if field.get("required") else ""
            label_text = f"{field['label']}:{required_marker}"
            self._form_panel.mount(
                Static(label_text, id=f"label-{field_name}")
            )

            field_type = field.get("type", "str")

            if field_type == "bool":
                self._form_panel.mount(
                    Checkbox(
                        label=field["label"],
                        value=bool(field.get("default", False)),
                        id=field_id,
                    )
                )
            elif field_type == "select":
                options = [(opt, opt) for opt in field.get("options") or []]
                default_val = field.get("default")
                self._form_panel.mount(
                    Select(
                        options=options,
                        value=default_val if default_val else Select.BLANK,
                        id=field_id,
                        allow_blank=False,
                    )
                )
            elif field_type in ("int", "float"):
                input_type = "integer" if field_type == "int" else "number"
                self._form_panel.mount(
                    Input(
                        value=str(field.get("default", "")),
                        type=input_type,  # type: ignore[arg-type]
                        placeholder=field.get("help", ""),
                        id=field_id,
                    )
                )
            else:
                default = str(field.get("default", ""))
                self._form_panel.mount(
                    Input(
                        value=default,
                        placeholder=field.get("help", ""),
                        id=field_id,
                    )
                )

        action_children: list[Widget] = [
            Button("Execute", id="btn-execute", variant="success")
        ]
        if schema.get("has_queue_option"):
            action_children.append(
                Button("Add to Queue", id="btn-queue", variant="primary")
            )

        self._form_panel.mount(Horizontal(*action_children, id="form-actions"))
        self._form_panel.mount(Static("Status: Ready", id="form-status"))
        self._form_panel.mount(Static("", id="form-result"))

        scroll = self.query_one("#tools-form-scroll", ScrollableContainer)
        scroll.scroll_home()

    @on(Button.Pressed, "#btn-execute")
    def _on_execute(self) -> None:
        self._run_command(queue=False)

    @on(Button.Pressed, "#btn-queue")
    def _on_queue(self) -> None:
        self._run_command(queue=True)

    def _run_command(self, queue: bool) -> None:
        from max_cli.interface.tui.command_executor import CommandExecutor
        from max_cli.interface.tui.command_registry import CommandRegistry

        form_panel = self._form_panel
        if form_panel is None:
            return
        title_widget = form_panel.query_one("#form-title", Static)
        category, command = self._parse_title(title_widget.renderable)  # type: ignore[attr-defined]

        values = self._collect_form_values()

        schema = CommandRegistry.get_command(category, command)
        if not schema:
            self._set_form_status("Error: Command not found", "error")
            return

        valid, errors = CommandRegistry.validate_fields(schema, values)
        if not valid:
            self._set_form_status(f"[red]\u2717 {'; '.join(errors)}[/red]", "error")
            return

        self._set_form_status("Executing...", "info")
        exec_btn = form_panel.query_one("#btn-execute", Button)
        exec_btn.disabled = True
        exec_btn.label = "Working..."
        queue_btn = form_panel.query_one("#btn-queue", Button, default=None)
        if queue_btn:
            queue_btn.disabled = True

        executor = CommandExecutor()
        try:
            result = executor.execute(
                category=category,
                command=command,
                values=values,
                queue=queue,
            )

            if result.success:
                if queue:
                    self._set_form_status(
                        "[yellow]\u23f3 Queued for background execution[/yellow]",
                        "info",
                    )
                else:
                    self._set_form_status(
                        f"[green]\u2713 {result.message}[/green]", "success"
                    )
                result_widget = form_panel.query_one("#form-result", Static)
                if result.output_files:
                    output_text = "Output:\n" + "\n".join(
                        f"  {f}" for f in result.output_files
                    )
                    result_widget.update(output_text)
            else:
                self._set_form_status(f"[red]\u2717 {result.error}[/red]", "error")

        except Exception as e:
            self._set_form_status(f"[red]\u2717 Error: {e}[/red]", "error")
        finally:
            exec_btn.disabled = False
            exec_btn.label = "Execute"
            if queue_btn:
                queue_btn.disabled = False

    def _collect_form_values(self) -> dict[str, Any]:
        from max_cli.interface.tui.command_registry import CommandRegistry

        form_panel = self.query_one("#tools-form-panel", Vertical)
        title_widget = form_panel.query_one("#form-title", Static)
        category, command = self._parse_title(title_widget.renderable)  # type: ignore[attr-defined]

        schema = CommandRegistry.get_command(category, command)
        if not schema:
            return {}

        values: dict[str, Any] = {}
        for field in schema["fields"]:
            field_id = f"field-{field['name']}"
            try:
                widget = form_panel.query_one(f"#{field_id}")
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
        form_panel = self.query_one("#tools-form-panel", Vertical)
        status = form_panel.query_one("#form-status", Static)
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

    def select_command(self, category: str, command: str) -> None:
        self._build_form(category, command)
        tree = self.query_one("#tools-tree", Tree)
        for node in tree.root.walk():
            if node.data == f"{category}:{command}":
                tree.select_node(node)
                break
