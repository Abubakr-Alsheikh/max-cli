from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import typer
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from max_cli.common.atomic import atomic_write_json
from max_cli.common.exceptions import MaxError
from max_cli.common.logger import console, log_error, log_success

if TYPE_CHECKING:
    from max_cli.core.agent.agent import ActionCall, Agent, AgentReply, Step

app = typer.Typer()

# Earlier conversation turns a chat session starts from.
CHAT_MEMORY_TURNS = 20
EXIT_WORDS = ("exit", "quit")
DANGER_NOTES = {
    "moves": "moves or renames files",
    "overwrites": "overwrites files in place",
    "deletes": "deletes files",
}
STEP_STYLES = {
    "loaded": ("·", "dim"),
    "looked": ("·", "dim"),
    "started": ("⚙", "bold cyan"),
    "ran": ("✓", "green"),
    "failed": ("✗", "red"),
    "refused": ("!", "yellow"),
    "declined": ("-", "dim"),
    "planned": ("→", "cyan"),
}
# Quicker actions don't show how long they took.
MIN_SHOWN_SECONDS = 0.1
# A finished action's lines sit under its "⚙ name" line.
RESULT_INDENT = "      "
ARGUMENT_INDENT = "      "
EXAMPLES = (
    "shrink every video in this folder",
    "merge the PDFs in Downloads into one file",
    "sort my Music folder into Artist/Album folders",
    "find duplicate files here",
)


def _get_engine():
    from max_cli.core.engines.ai_engine import AIEngine

    return AIEngine()


def _confirm(call: "ActionCall") -> bool:
    """The agent asks before it moves, overwrites or deletes files."""
    note = DANGER_NOTES.get(call.action.danger.value, "changes files")
    return Confirm.ask(
        f"[yellow]Run [bold]{escape(call.describe())}[/bold]? It {note}.[/yellow]"
    )


def _show_arguments(step: "Step") -> None:
    width = max((len(name) for name in step.arguments), default=0)
    for name, value in step.arguments.items():
        console.print(
            f"{ARGUMENT_INDENT}[dim]{escape(name.ljust(width))}[/dim]  {escape(value)}"
        )


def _show_step(step: "Step") -> None:
    """One step as it happens: an action's name and arguments when it starts,
    its result (and the files it made) indented under it when it ends."""
    kind = step.kind.value
    mark, style = STEP_STYLES.get(kind, ("·", "dim"))
    if kind in ("started", "planned", "refused", "declined"):
        title = {
            "started": step.label,
            "planned": f"Would run {step.label}",
            "declined": f"Skipped {step.label}",
        }.get(kind, step.text)
        console.print(f"  [{style}]{mark} {escape(title)}[/{style}]")
        _show_arguments(step)
        return
    if kind in ("ran", "failed") and (step.result is not None or step.seconds):
        message = step.result.message if step.result is not None else step.text
        took = (
            f"  [dim]{step.seconds:.1f}s[/dim]"
            if step.seconds >= MIN_SHOWN_SECONDS
            else ""
        )
        console.print(
            f"{RESULT_INDENT}[{style}]{mark} {escape(message)}[/{style}]{took}"
        )
        for path in step.result.output_files if step.result is not None else []:
            console.print(f"{RESULT_INDENT}  [dim]→[/dim] {escape(str(path))}")
        return
    console.print(f"  [{style}]{mark} {escape(step.text)}[/{style}]")


def _make_agent(dry_run: bool = False) -> "Agent":
    from max_cli.core.agent.agent import Agent

    return Agent.from_settings(confirm=_confirm, on_step=_show_step, dry_run=dry_run)


def _show_reply(reply: "AgentReply") -> None:
    """The answer as Markdown in a panel; the footer counts actions and tokens."""
    from rich.markdown import Markdown

    actions = sum(1 for step in reply.steps if step.kind.value in ("ran", "failed"))
    facts = []
    if actions:
        facts.append(f"{actions} action{'s' if actions != 1 else ''}")
    if reply.tokens:
        facts.append(f"{reply.tokens:,} tokens")
    console.print()
    console.print(
        Panel(
            Markdown(reply.text),
            title="[bold cyan]Max[/bold cyan]",
            title_align="left",
            subtitle=f"[dim]{' · '.join(facts)}[/dim]" if facts else None,
            subtitle_align="right",
            border_style="cyan",
            padding=(1, 2),
        )
    )


@app.command("ask")
@app.command("a", hidden=True)
def ask_ai(
    prompt: str = typer.Argument(..., help="What do you want done?"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what the agent would run, and run nothing."
    ),
    explain: bool = typer.Option(
        False, "--explain", "-e", hidden=True, help="No longer used."
    ),
):
    """
    Ask the AI agent to do something; it runs Max's own commands.
    Example: max ai ask "Compress all PDFs in Documents folder"

    It asks before it moves, overwrites or deletes files, works only in this
    folder and folders you name, and never runs other programs.
    """
    try:
        agent = _make_agent(dry_run)
        with console.status("[bold cyan]Thinking...[/bold cyan]") as status:
            # The agent may ask a question; the spinner would draw over it.
            agent.confirm = _paused(status, _confirm)
            reply = agent.ask(prompt)
    except MaxError as e:
        log_error(escape(str(e)))
        raise typer.Exit(1) from None
    _show_reply(reply)


def _paused(status: Any, confirm: Any) -> Any:
    """`confirm` with the spinner stopped while it asks."""

    def ask(call: "ActionCall") -> bool:
        status.stop()
        try:
            return bool(confirm(call))
        finally:
            status.start()

    return ask


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
            from rich.markdown import Markdown

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
            raise typer.Exit(1) from None


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

    from max_cli.core.engines.ai_engine import download_image

    console.print("\n[green]Image Ready![/green]")
    console.print(f"🔗 [link={url}]View Online[/link]")

    # Auto-download
    final_path = output_path or Path.cwd() / default_name

    try:
        with console.status(f"[dim]Downloading to {final_path.name}...[/dim]"):
            download_image(url, final_path)
        log_success(f"Saved to: [bold]{final_path}[/bold]")
    except (requests.RequestException, OSError) as e:
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
    Talk with the AI agent: each request runs Max's commands, and it
    remembers the conversation.

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
            "[bold cyan]Max Interactive Session[/bold cyan]\n"
            "Ask for what you want done. Type 'help' for examples, 'exit' to quit.",
            border_style="cyan",
        )
    )

    eng = _get_engine()
    try:
        agent = _make_agent()
    except MaxError as e:
        log_error(escape(str(e)))
        raise typer.Exit(1) from None
    earlier = eng.history[-CHAT_MEMORY_TURNS:]
    agent.messages.extend(earlier)
    if earlier:
        console.print(f"[dim]Remembering {len(earlier)} earlier messages[/dim]")

    while True:
        user_input = Prompt.ask("[bold green]You[/bold green]").strip()
        if user_input.lower() in EXIT_WORDS:
            break
        if not user_input:
            continue
        if user_input.lower() == "help":
            console.print("[bold cyan]For example:[/bold cyan]")
            for example in EXAMPLES:
                console.print(f"  {example}")
            continue
        try:
            with console.status("[bold cyan]Thinking...[/bold cyan]") as status:
                agent.confirm = _paused(status, _confirm)
                reply = agent.ask(user_input)
        except MaxError as e:
            log_error(escape(str(e)))
            continue
        _show_reply(reply)
        eng.history += [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": reply.text},
        ]

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

    from max_cli.core.engines.ai_engine import (
        SEARCHABLE_SUFFIXES,
        find_searchable_files,
    )

    requested = [ext.strip().lower().lstrip(".") for ext in extensions.split(",")]
    unreadable = [
        ext for ext in requested if ext and f".{ext}" not in SEARCHABLE_SUFFIXES
    ]
    if unreadable:
        readable = ", ".join(sorted(s.lstrip(".") for s in SEARCHABLE_SUFFIXES))
        console.print(
            f"[yellow]Skipping {', '.join(unreadable)}: search reads only "
            f"{readable}.[/yellow]"
        )
    files = find_searchable_files(
        path, [ext for ext in requested if ext not in unreadable]
    )

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
    schema: list[str] = typer.Option(
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
            atomic_write_json(output, result)
            log_success(f"Saved to: {output}")
    except Exception as e:
        log_error(f"Extraction failed: {e}")
