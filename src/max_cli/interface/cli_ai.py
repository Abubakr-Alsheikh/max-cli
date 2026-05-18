import typer
import subprocess
import shlex
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.markdown import Markdown
from pathlib import Path
from typing import Optional

from max_cli.common.logger import console, log_error, log_success

app = typer.Typer()

MAIN_APP_REF: Optional[typer.Typer] = None


def _get_engine():
    from max_cli.core.engines.ai_engine import AIEngine

    return AIEngine()


@app.command("ask")
@app.command("a", hidden=True)
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
            eng = _get_engine()
            result = eng.interpret_intent(prompt, MAIN_APP_REF)
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
@app.command("ana", hidden=True)
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
            eng = _get_engine()
            result_text = eng.analyze_image_content(target, prompt)

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
@app.command("c", hidden=True)
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
            eng = _get_engine()
            url = eng.generate_image(prompt, model=model)
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
            eng = _get_engine()
            url = eng.edit_image(target, prompt, model=model)
            _handle_image_result(url, output, f"edited_{target.name}")
        except Exception as e:
            log_error(str(e))


def _handle_image_result(url: str, output_path: Optional[Path], default_name: str):
    """Helper to display URL and download image."""
    import requests

    console.print("\n[green]Image Ready![/green]")
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
@app.command("ch", hidden=True)
def chat_session(
    clear: bool = typer.Option(False, "--clear", help="Clear conversation history."),
    export: Optional[Path] = typer.Option(
        None, "--export", "-e", help="Export conversation to JSON file."
    ),
    import_file: Optional[Path] = typer.Option(
        None, "--import", "-i", help="Import conversation from JSON file."
    ),
):
    """
    Start an interactive session with Max. He remembers what you said.

    Use --clear to reset history, --export to save, --import to load previous chats.
    """
    if clear:
        eng = _get_engine()
        eng.clear_history()
        console.print("[green]Conversation history cleared.[/green]")
        return

    if export:
        eng = _get_engine()
        eng.export_history(export)
        log_success(f"Conversation exported to: {export}")
        return

    if import_file:
        if not import_file.exists():
            log_error(f"File not found: {import_file}")
            raise typer.Exit(1)
        eng = _get_engine()
        eng.import_history(import_file)
        log_success(f"Conversation imported from: {import_file}")
        return

    console.print(
        Panel(
            "[bold cyan]Max Interactive Session[/bold cyan]\nType 'exit' to quit, 'help' for suggestions.",
            border_style="cyan",
        )
    )

    eng = _get_engine()
    if eng.history:
        console.print(
            f"[dim]Loaded {len(eng.history)} messages from previous session[/dim]"
        )

    while True:
        suggestions = eng.get_suggestions()
        user_input = Prompt.ask(
            "[bold green]User[/bold green]",
            choices=suggestions + ["help", "exit", "quit"],
            show_choices=False,
        )
        if user_input.lower() in ["exit", "quit"]:
            eng._save_history()
            break
        if user_input.lower() == "help":
            console.print("[bold cyan]Suggestions:[/bold cyan]")
            for i, s in enumerate(suggestions, 1):
                console.print(f"  {i}. {s}")
            console.print("  [dim]Or type your own command[/dim]")
            continue

        with console.status("[dim]Thinking...[/dim]"):
            try:
                result = eng.interpret_intent(user_input, MAIN_APP_REF)

                if "error" in result:
                    console.print(f"[red]Max:[/red] {result['error']}")
                    continue

                thought = result.get("thought")
                cmd = result.get("command")

                if thought and not cmd:
                    console.print(f"[cyan]Max:[/cyan] {thought}")

                elif cmd:
                    console.print(
                        f"[cyan]Max Suggests:[/cyan] [bold white]{cmd}[/bold white]"
                    )
                    if thought:
                        console.print(f"[dim]Reason: {thought}[/dim]")

                    if Confirm.ask("Execute?"):
                        args = shlex.split(cmd)
                        subprocess.run(args)

            except Exception as e:
                log_error(str(e))

    eng._save_history()
    console.print("[cyan]Goodbye![/cyan]")


@app.command("search")
@app.command("s", hidden=True)
def semantic_search_cmd(
    query: str = typer.Argument(..., help="Search query in natural language."),
    path: Path = typer.Argument(".", help="Folder to search in."),
    extensions: str = typer.Option(
        "txt,md,py,json,yaml",
        "--ext",
        help="File extensions to search (comma-separated).",
    ),
):
    """
    Search files by content using AI (semantic search).
    """

    if not path.is_dir():
        log_error(f"Folder not found: {path}")
        raise typer.Exit(1)

    exts = [f".{e.strip()}" for e in extensions.split(",")]
    files = [f for f in path.rglob("*") if f.is_file() and f.suffix.lower() in exts]

    if not files:
        console.print("[yellow]No matching files found.[/yellow]")
        return

    console.print(f"[cyan]Searching {len(files)} files for: '{query}'...[/cyan]")

    try:
        eng = _get_engine()
        results = eng.semantic_search(query, files)

        if not results:
            console.print("[yellow]No matches found.[/yellow]")
        else:
            console.print(f"[green]Found {len(results)} matching file(s):[/green]\n")
            for r in results:
                console.print(f"  [bold]{r['file']}[/bold]")
                console.print(f"  [dim]{r.get('reasoning', '')}[/dim]\n")
    except Exception as e:
        log_error(f"Search failed: {e}")


@app.command("extract")
def extract_data_cmd(
    target: Path = typer.Argument(..., help="Image file to extract data from."),
    schema: str = typer.Option(
        ...,
        "--schema",
        "-s",
        help="Schema as field:description (can specify multiple).",
    ),
    output: Optional[Path] = typer.Option(None, "-o", help="Output JSON file."),
):
    """
    Extract structured data from images (receipts, invoices, etc.).

    Example: max ai extract receipt.jpg -s "total:Total amount" -s "date:Date"
    """
    if not target.exists():
        log_error(f"File not found: {target}")
        raise typer.Exit(1)

    schema_dict = {}
    for s in schema:
        if ":" in s:
            field, desc = s.split(":", 1)
            schema_dict[field.strip()] = desc.strip()
        else:
            schema_dict[s.strip()] = ""

    console.print(f"[cyan]Extracting data from {target.name}...[/cyan]")

    try:
        eng = _get_engine()
        result = eng.extract_structured_data(target, schema_dict)

        console.print("\n[bold green]Extracted Data:[/bold green]")
        import json

        console.print(json.dumps(result, indent=2))

        if output:
            output.write_text(json.dumps(result, indent=2))
            log_success(f"Saved to: {output}")
    except Exception as e:
        log_error(f"Extraction failed: {e}")
