import typer
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from max_cli.common.logger import console
from max_cli.core.engines.daemon_manager import DaemonManager
from max_cli.core.engines.task_queue import TaskStatus, TaskType

app = typer.Typer(help="Manage background task queue")
daemon = DaemonManager()


@app.command("status")
@app.command("s", hidden=True)
def queue_status() -> None:
    stats = daemon.get_stats()
    tasks = daemon.get_all()

    if not tasks:
        console.print("[dim]Queue is empty.[/dim]")
        return

    table = Table(
        title=f"Task Queue ({stats['total']} total)",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("ID")
    table.add_column("Type")
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Progress")
    table.add_column("Created")

    for task in tasks:
        status_color = {
            TaskStatus.PENDING: "yellow",
            TaskStatus.RUNNING: "blue",
            TaskStatus.COMPLETED: "green",
            TaskStatus.FAILED: "red",
            TaskStatus.CANCELLED: "dim",
            TaskStatus.PAUSED: "cyan",
        }.get(task.status, "white")

        table.add_row(
            task.id,
            task.type.value,
            task.title or task.description[:40],
            f"[{status_color}]{task.status.value}[/{status_color}]",
            f"{task.progress:.0f}%",
            task.created_at[:19],
        )

    console.print(table)

    summary = Text()
    summary.append(f"Pending: {stats['pending']}  ", style="yellow")
    summary.append(f"Running: {stats['running']}  ", style="blue")
    summary.append(f"Failed: {stats['failed']}  ", style="red")
    console.print(summary)


@app.command("history")
@app.command("h", hidden=True)
def queue_history(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of history items"),
    task_type: str = typer.Option(None, "--type", "-t", help="Filter by task type"),
) -> None:
    tt = TaskType(task_type) if task_type else None
    history = daemon.get_history(limit=limit, task_type=tt)

    if not history:
        console.print("[dim]No history.[/dim]")
        return

    table = Table(
        title=f"Task History ({len(history)} items)",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("ID")
    table.add_column("Type")
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Completed")

    for task in history:
        status_color = "green" if task.status == TaskStatus.COMPLETED else "red"
        table.add_row(
            task.id,
            task.type.value,
            task.title or task.description[:40],
            f"[{status_color}]{task.status.value}[/{status_color}]",
            task.completed_at[:19] if task.completed_at else "N/A",
        )

    console.print(table)


@app.command("cancel")
@app.command("c", hidden=True)
def queue_cancel(
    task_id: str = typer.Argument(..., help="Task ID to cancel"),
) -> None:
    if daemon.cancel(task_id):
        console.print(f"[green]Cancelled task {task_id}[/green]")
    else:
        console.print(f"[red]Task {task_id} not found or is running[/red]")
        raise typer.Exit(1)


@app.command("retry")
@app.command("r", hidden=True)
def queue_retry(
    task_id: str = typer.Argument(..., help="Task ID to retry"),
) -> None:
    task = daemon.retry(task_id)
    if task:
        console.print(f"[green]Retrying task {task_id}: {task.title}[/green]")
    else:
        console.print(f"[red]Task {task_id} not found[/red]")
        raise typer.Exit(1)


@app.command("clear")
@app.command("cl", hidden=True)
def queue_clear(
    all_tasks: bool = typer.Option(False, "--all", "-a", help="Clear all tasks"),
    failed_only: bool = typer.Option(
        False, "--failed", "-f", help="Clear failed tasks only"
    ),
    force: bool = typer.Option(False, "--force", help="Skip confirmation"),
) -> None:
    if not force:
        from rich.prompt import Confirm

        if not Confirm.ask("Clear queue?"):
            console.print("[dim]Cancelled.[/dim]")
            return

    if all_tasks:
        count = daemon.clear()
        console.print(f"[green]Cleared {count} tasks[/green]")
    elif failed_only:
        count = daemon.clear(status=TaskStatus.FAILED)
        console.print(f"[green]Cleared {count} failed tasks[/green]")
    else:
        count = daemon.clear(status=TaskStatus.PENDING)
        console.print(f"[green]Cleared {count} pending tasks[/green]")


@app.command("process")
@app.command("p", hidden=True)
def queue_process(
    max_tasks: int = typer.Option(
        0, "--max", "-n", help="Max tasks to process (0=all)"
    ),
) -> None:
    console.print("[bold]Processing queue...[/bold]")
    count = daemon.process_now(max_tasks=max_tasks)
    console.print(f"[green]Processed {count} tasks[/green]")


@app.command("stats")
def queue_stats() -> None:
    stats = daemon.get_stats()

    panel_lines = [
        f"Total in queue:  [bold]{stats['total']}[/bold]",
        f"  Pending:       [yellow]{stats['pending']}[/yellow]",
        f"  Running:       [blue]{stats['running']}[/blue]",
        f"  Paused:        [cyan]{stats['paused']}[/cyan]",
        f"  Failed:        [red]{stats['failed']}[/red]",
        "",
        "By type:",
    ]
    for type_name, count in stats.get("by_type", {}).items():
        panel_lines.append(f"  {type_name}: {count}")

    console.print(Panel("\n".join(panel_lines), title="Queue Statistics"))
