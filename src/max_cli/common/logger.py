from rich.console import Console
from rich.theme import Theme

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
    console.print(f"[error]✖ Error:[/error] {message}")


def log_success(message: str):
    console.print(f"[success]✔ Success:[/success] {message}")
