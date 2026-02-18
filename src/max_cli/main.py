import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich import box

from max_cli.common.exceptions import MaxError
from max_cli.interface import (
    cli_ai,
    cli_config,
    cli_files,
    cli_images,
    cli_media,
    cli_network,
    cli_pdf,
    cli_tools,
)
from max_cli.plugins.base import PluginContext
from max_cli.plugins.manager import PluginManager

console = Console()

plugin_manager: Optional[PluginManager] = None

app = typer.Typer(
    name="max",
    help="MAX: The High-Performance CLI Utility.",
    add_completion=True,
    no_args_is_help=True,
)

app.add_typer(
    cli_images.app, name="images", help="Compress, resize, and convert images."
)
app.add_typer(cli_images.app, name="img", hidden=True)

app.add_typer(cli_files.app, name="files", help="Organize and bulk-rename files.")
app.add_typer(cli_files.app, name="file", hidden=True)

app.add_typer(cli_pdf.app, name="pdf", help="Merge, split, and compress PDFs.")

app.add_typer(
    cli_media.app, name="video", help="Compress, convert, and process video/audio."
)
app.add_typer(cli_media.app, name="v", hidden=True)

app.add_typer(cli_network.app, name="net", help="Network tools (Download, Speedtest).")

app.add_typer(cli_ai.app, name="ai", help="Ask AI to run commands.")

app.add_typer(
    cli_network.app,
    name="grab",
    help="Download media from various platforms.",
)

app.add_typer(cli_tools.app, name="tools", help="System utilities (Clipboard, QR).")

app.add_typer(cli_config.app, name="config", help="Manage API keys and settings.")

app.command("share")(cli_tools.share_qr)
app.command("paste")(cli_tools.paste_image)
app.command("copy")(cli_tools.copy_file)


def _init_plugins() -> None:
    """Initialize and load plugins."""
    global plugin_manager
    plugin_manager = PluginManager()
    plugin_manager.load_all(PluginContext(app=app))
    plugin_manager.register_all(app)


def _get_plugin_manager() -> PluginManager:
    """Get or initialize the plugin manager."""
    global plugin_manager
    if plugin_manager is None:
        plugin_manager = PluginManager()
        plugin_manager.load_all(PluginContext(app=app))
    return plugin_manager


plugins_app = typer.Typer(name="plugins", help="Manage plugins.")


@plugins_app.command("list")
def list_plugins(
    all: bool = typer.Option(
        False, "--all", "-a", help="Show all plugins including disabled"
    ),
) -> None:
    """List all installed plugins."""
    manager = _get_plugin_manager()
    plugins = manager.get_all_plugins()

    if not plugins:
        console.print("[yellow]No plugins found.[/yellow]")
        console.print("[dim]Place plugins in ~/.max_cli/plugins/ or ./plugins/[/dim]")
        return

    table = Table(title="Installed Plugins", box=box.ROUNDED)
    table.add_column("Name", style="cyan")
    table.add_column("Version", justify="center")
    table.add_column("Description")
    table.add_column("Status", justify="center")

    for name, loaded in sorted(plugins.items()):
        if loaded.plugin:
            status = (
                "[green]✓ Enabled[/green]"
                if loaded.enabled
                else "[red]✗ Disabled[/red]"
            )
            if not all and not loaded.enabled:
                continue
            table.add_row(
                loaded.plugin.name,
                loaded.plugin.version,
                loaded.plugin.description[:50] + "..."
                if len(loaded.plugin.description) > 50
                else loaded.plugin.description,
                status,
            )
        else:
            status = "[red]✗ Error[/red]"
            if not all:
                continue
            table.add_row(name, "-", loaded.error or "Failed to load", status)

    console.print(table)


@plugins_app.command("info")
def plugin_info(name: str = typer.Argument(..., help="Plugin name")) -> None:
    """Show detailed information about a plugin."""
    manager = _get_plugin_manager()
    info = manager.get_plugin_info(name)

    if not info:
        console.print(f"[red]Plugin '{name}' not found.[/red]")
        return

    console.print(f"\n[bold cyan]{info['name']}[/bold cyan] v{info['version']}")
    console.print(f"[dim]{info['description']}[/dim]\n")

    table = Table(box=None, show_header=False)
    table.add_column("Key", style="bold")
    table.add_column("Value")

    if info["author"]:
        table.add_row("Author", info["author"])
    if info["author_email"]:
        table.add_row("Email", info["author_email"])
    if info["url"]:
        table.add_row("URL", info["url"])
    if info["license"]:
        table.add_row("License", info["license"])
    if info["tags"]:
        table.add_row("Tags", ", ".join(info["tags"]))
    if info["dependencies"]:
        table.add_row("Dependencies", ", ".join(info["dependencies"]))

    status = "[green]Enabled[/green]" if info["enabled"] else "[red]Disabled[/red]"
    table.add_row("Status", status)

    if info["error"]:
        table.add_row("Error", f"[red]{info['error']}[/red]")

    console.print(table)


@plugins_app.command("enable")
def enable_plugin(name: str = typer.Argument(..., help="Plugin name")) -> None:
    """Enable a plugin."""
    manager = _get_plugin_manager()
    if manager.enable_plugin(name):
        console.print(f"[green]Plugin '{name}' enabled.[/green]")
    else:
        console.print(f"[red]Plugin '{name}' not found.[/red]")


@plugins_app.command("disable")
def disable_plugin(name: str = typer.Argument(..., help="Plugin name")) -> None:
    """Disable a plugin."""
    manager = _get_plugin_manager()
    if manager.disable_plugin(name):
        console.print(f"[yellow]Plugin '{name}' disabled.[/yellow]")
    else:
        console.print(f"[red]Plugin '{name}' not found.[/red]")


app.add_typer(plugins_app, name="plugins")

cli_ai.MAIN_APP_REF = app


def main():
    """Main entry point with Global Error Handling."""
    try:
        _init_plugins()
        app()
    except MaxError as e:
        console.print(f"[bold red]X Error:[/bold red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print("[bold red]!! Critical Error (Unexpected)[/bold red]")
        console.print(f"An error occurred: {e}")
        console.print(
            "[dim]If this persists, please report this to the developer.[/dim]"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
