import typer
import subprocess
import shlex
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.markdown import Markdown
from pathlib import Path
import requests
from typing import Optional

from max_cli.core.ai_engine import AIEngine
from max_cli.common.logger import console, log_error, log_success

app = typer.Typer()
engine = AIEngine()

# We need a reference to the main Typer app to generate docs.
# We will set this in main.py
MAIN_APP_REF = None


@app.command("ask")
def ask_ai(
    prompt: str = typer.Argument(..., help="What do you want to do?"),
    explain: bool = typer.Option(
        False, "--explain", "-e", help="Explain the command logic."
    ),
):
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

    if explain and result.get("explanation"):
        console.print(
            Panel(
                result["explanation"],
                title="[dim]How it works[/dim]",
                border_style="blue",
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


@app.command("analyze")
def analyze_image(
    target: Path = typer.Argument(..., help="Path to the image."),
    prompt: str = typer.Option(
        "Describe this image in detail.",
        "--prompt",
        "-p",
        help="Specific question about the image.",
    ),
):
    """
    Use AI Vision to describe an image or extract data from it.
    Example: max ai analyze invoice.png -p "Extract the total amount and date"
    """
    if not target.exists():
        log_error(f"Image file not found: {target}")
        raise typer.Exit(1)

    console.print(f"[dim]Uploading '{target.name}' to AI...[/dim]")

    with console.status("[bold magenta]Analyzing Vision Data...[/bold magenta]"):
        try:
            # Call the new engine method
            result_text = engine.analyze_image_content(target, prompt)

            # Render result
            console.print("\n")
            console.print(
                Panel(
                    Markdown(result_text),
                    title=f"[cyan]Analysis: {target.name}[/cyan]",
                    border_style="magenta",
                )
            )

        except Exception as e:
            log_error(str(e))
            raise typer.Exit(1)


@app.command("create")
def create_image(
    prompt: str = typer.Argument(..., help="Description of the image to create."),
    output: Optional[Path] = typer.Option(None, "-o", "--output", help="Save path."),
    model: str = typer.Option("gemini-2.5-flash-image", help="Override image model."),
):
    """
    Generate an image from text (Nano Banana).
    """
    console.print(f"[cyan]Painting: [bold]{prompt}[/bold]...[/cyan]")

    with console.status("[bold green]Nano Banana is generating...[/bold green]"):
        try:
            url = engine.generate_image(prompt, model=model)
            _handle_image_result(url, output, "created_image.png")
        except Exception as e:
            log_error(str(e))


@app.command("edit")
def edit_image(
    target: Path = typer.Argument(..., help="Path to original image."),
    prompt: str = typer.Argument(
        ..., help="Instruction (e.g., 'Turn the sky purple')."
    ),
    output: Optional[Path] = typer.Option(None, "-o", help="Save path."),
    model: str = typer.Option("gemini-2.5-flash-image", help="Override image model."),
):
    """
    Edit an existing image using AI instructions.
    """
    if not target.exists():
        log_error(f"File not found: {target}")
        raise typer.Exit(1)

    console.print(f"[cyan]Editing [bold]{target.name}[/bold]...[/cyan]")

    with console.status("[bold green]Applying AI changes...[/bold green]"):
        try:
            url = engine.edit_image(target, prompt, model=model)
            _handle_image_result(url, output, f"edited_{target.name}")
        except Exception as e:
            log_error(str(e))


def _handle_image_result(url: str, output_path: Optional[Path], default_name: str):
    """Helper to display URL and download image."""
    console.print("\n[green]✨ Image Ready![/green]")
    console.print(f"🔗 [link={url}]View Online[/link]")

    # Auto-download
    final_path = output_path or Path.cwd() / default_name

    try:
        with console.status(f"[dim]Downloading to {final_path.name}...[/dim]"):
            r = requests.get(url, stream=True)
            r.raise_for_status()
            with open(final_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        log_success(f"Saved to: [bold]{final_path}[/bold]")
    except Exception as e:
        console.print(f"[yellow]Could not auto-download: {e}[/yellow]")


@app.command("chat")
def chat_session():
    """
    Start an interactive session with Max. He remembers what you said.
    """
    console.print(
        Panel(
            "[bold cyan]Max Interactive Session[/bold cyan]\nType 'exit' or 'quit' to end.",
            border_style="cyan",
        )
    )

    while True:
        user_input = Prompt.ask("[bold green]User[/bold green]")

        if user_input.lower() in ["exit", "quit"]:
            break

        with console.status("[dim]Thinking...[/dim]"):
            try:
                result = engine.interpret_intent(user_input, MAIN_APP_REF)

                if "error" in result:
                    console.print(f"[red]Max:[/red] {result['error']}")
                    continue

                cmd = result.get("command")
                thought = result.get("thought")

                console.print(
                    f"[cyan]Max Suggests:[/cyan] [bold white]{cmd}[/bold white]"
                )
                console.print(f"[dim]Reason: {thought}[/dim]")

                if Confirm.ask("Execute?"):
                    args = shlex.split(cmd)
                    subprocess.run(args)
            except Exception as e:
                log_error(str(e))

    console.print("[cyan]Goodbye![/cyan]")
