import typer
import subprocess
import shlex
from rich.panel import Panel
from rich.prompt import Confirm

from max_cli.core.ai_engine import AIEngine
from max_cli.common.logger import console, log_error

app = typer.Typer()
engine = AIEngine()

# We need a reference to the main Typer app to generate docs.
# We will set this in main.py
MAIN_APP_REF = None


@app.command("ask")
def ask_ai(prompt: str = typer.Argument(..., help="What do you want to do?")):
    """
    Natural Language Interface.
    Example: max ai ask "Compress all PDFs in Documents folder"
    """
    if MAIN_APP_REF is None:
        log_error("Internal Error: Main App reference not linked.")
        raise typer.Exit(1)

    console.print(f"[dim]Analyzing request: '{prompt}'...[/dim]")

    with console.status("[bold cyan]Consulting AI...[/bold cyan]"):
        try:
            result = engine.interpret_intent(prompt, MAIN_APP_REF)
        except Exception as e:
            log_error(str(e))
            raise typer.Exit(1)

    # Handle AI Rejection
    if "error" in result:
        console.print(
            Panel(result["error"], title="[red]AI Error[/red]", border_style="red")
        )
        return

    # Handle Success
    cmd_str = result.get("command", "")
    reason = result.get("thought", "")
    is_dangerous = result.get("dangerous", False)

    # Display Proposal
    console.print(
        Panel(
            f"[dim]{reason}[/dim]\n\n[bold green]> {cmd_str}[/bold green]",
            title="[cyan]Max Suggests[/cyan]",
            border_style="green" if not is_dangerous else "yellow",
        )
    )

    # Confirmation
    msg = "Run this command?"
    if is_dangerous:
        msg = "[bold red]⚠ This command modifies files. Proceed?[/bold red]"

    if Confirm.ask(msg):
        console.print("\n[dim]Executing...[/dim]")
        # Execute safely using subprocess
        # We split the string safely to handle quotes properly
        try:
            args = shlex.split(cmd_str)
            subprocess.run(args, check=True)
        except Exception as e:
            log_error(f"Execution failed: {e}")
    else:
        console.print("[yellow]Aborted.[/yellow]")
