from rich.console import Console
from rich.theme import Theme

from max_cli.common.exit_status import mark_error

# Define a custom theme for consistent coloring
custom_theme = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "error": "bold red",
        "success": "bold green",
    }
)

console = Console(theme=custom_theme)


def log_error(message: str):
    """Print an error. `max` then exits 1 even if the command returns."""
    mark_error()
    console.print(f"[error]X Error:[/error] {message}")


def log_success(message: str):
    console.print(f"[success]V Success:[/success] {message}")
