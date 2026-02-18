from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typer import Typer

from max_cli.core.cli import plugins


def register(app: "Typer") -> None:
    """Register plugin management commands."""
    from rich.console import Console
    from rich.table import Table
    from rich import box
    import typer

    console = Console()
    plugins_app = typer.Typer(name="plugins", help="Manage plugins.")

    @plugins_app.command("list")
    def list_plugins(
        all: bool = typer.Option(
            False, "--all", "-a", help="Show all plugins including disabled"
        ),
    ) -> None:
        """List all installed plugins."""
        manager = plugins.get_plugin_manager()
        loaded_plugins = manager.get_all_plugins()

        if not loaded_plugins:
            console.print("[yellow]No plugins found.[/yellow]")
            console.print(
                "[dim]Place plugins in ~/.max_cli/plugins/ or ./plugins/[/dim]"
            )
            return

        table = Table(title="Installed Plugins", box=box.ROUNDED)
        table.add_column("Name", style="cyan")
        table.add_column("Version", justify="center")
        table.add_column("Description")
        table.add_column("Status", justify="center")

        for name, loaded in sorted(loaded_plugins.items()):
            if loaded.plugin:
                status = (
                    "[green]Enabled[/green]"
                    if loaded.enabled
                    else "[red]Disabled[/red]"
                )
                if not all and not loaded.enabled:
                    continue
                desc = loaded.plugin.description
                if len(desc) > 50:
                    desc = desc[:50] + "..."
                table.add_row(loaded.plugin.name, loaded.plugin.version, desc, status)
            else:
                status = "[red]Error[/red]"
                if not all:
                    continue
                table.add_row(name, "-", loaded.error or "Failed to load", status)

        console.print(table)

    @plugins_app.command("info")
    def plugin_info(name: str = typer.Argument(..., help="Plugin name")) -> None:
        """Show detailed information about a plugin."""
        manager = plugins.get_plugin_manager()
        info = manager.get_plugin_info(name)

        if not info:
            console.print(f"[red]Plugin '{name}' not found.[/red]")
            return

        console.print(f"\n[bold cyan]{info['name']}[/bold cyan] v{info['version']}")
        console.print(f"[dim]{info['description']}[/dim]\n")

        table = Table(box=None, show_header=False)
        table.add_column("Key", style="bold")
        table.add_column("Value")

        for key in ["author", "author_email", "url", "license", "tags", "dependencies"]:
            if info.get(key):
                value = (
                    ", ".join(info[key]) if isinstance(info[key], list) else info[key]
                )
                table.add_row(key.capitalize(), value)

        status = "[green]Enabled[/green]" if info["enabled"] else "[red]Disabled[/red]"
        table.add_row("Status", status)

        if info.get("error"):
            table.add_row("Error", f"[red]{info['error']}[/red]")

        console.print(table)

    @plugins_app.command("enable")
    def enable_plugin(name: str = typer.Argument(..., help="Plugin name")) -> None:
        """Enable a plugin."""
        manager = plugins.get_plugin_manager()
        if manager.enable_plugin(name):
            console.print(f"[green]Plugin '{name}' enabled.[/green]")
        else:
            console.print(f"[red]Plugin '{name}' not found.[/red]")

    @plugins_app.command("disable")
    def disable_plugin(name: str = typer.Argument(..., help="Plugin name")) -> None:
        """Disable a plugin."""
        manager = plugins.get_plugin_manager()
        if manager.disable_plugin(name):
            console.print(f"[yellow]Plugin '{name}' disabled.[/yellow]")
        else:
            console.print(f"[red]Plugin '{name}' not found.[/red]")

    app.add_typer(plugins_app, name="plugins")
