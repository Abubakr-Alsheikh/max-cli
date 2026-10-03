import typer
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from max_cli.common.logger import console
from max_cli.core.engines.task_queue import TaskStatus, TaskType

app = typer.Typer(help="Manage background task queue")


def _get_engine():
    from max_cli.core.engines.task_manager import get_task_manager

    return get_task_manager()


def _show_worker(manager) -> None:
    """Whether a process runs the queue now, and how to start one."""
    if manager.worker_alive():
        console.print(
            "[green]A worker is running the queue[/green] "
            "[dim](the dashboard or the background worker)[/dim]"
        )
    elif manager.get_pending():
        console.print(
            "[yellow]No worker is running.[/yellow] "
            "[dim]Run 'max queue start' to run the queue in the background.[/dim]"
        )


@app.command("status")
@app.command("s", hidden=True)
def queue_status() -> None:
    """List every task in the queue with its status and progress."""
    manager = _get_engine()
    stats = manager.get_stats()
    tasks = manager.get_all()

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
    _show_worker(manager)


@app.command("history")
@app.command("h", hidden=True)
def queue_history(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of history items"),
    task_type: str = typer.Option(None, "--type", "-t", help="Filter by task type"),
) -> None:
    """Show finished tasks, newest first."""
    try:
        tt = TaskType(task_type) if task_type else None
    except ValueError:
        valid_types = ", ".join(t.value for t in TaskType)
        console.print(f"[red]Unknown task type '{task_type}'.[/red]")
        console.print(f"[dim]Valid types: {valid_types}[/dim]")
        raise typer.Exit(1) from None
    history = _get_engine().get_history(limit=limit, task_type=tt)

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
    """Cancel a pending, paused or running task."""
    if _get_engine().cancel(task_id):
        console.print(f"[green]Cancelled task {task_id}[/green]")
    else:
        console.print(f"[red]Task {task_id} not found or already finished[/red]")
        raise typer.Exit(1)


@app.command("retry")
@app.command("r", hidden=True)
def queue_retry(
    task_id: str = typer.Argument(..., help="Task ID to retry"),
) -> None:
    """Put a failed or finished task back in the queue as pending."""
    task = _get_engine().retry(task_id)
    if task:
        console.print(f"[green]Retrying task {task_id}: {task.title}[/green]")
    else:
        console.print(f"[red]Task {task_id} not found or still running[/red]")
        raise typer.Exit(1)


@app.command("clear")
@app.command("cl", hidden=True)
def queue_clear(
    all_tasks: bool = typer.Option(False, "--all", "-a", help="Clear all tasks"),
    # No -f short flag: everywhere else -f means --force.
    failed_only: bool = typer.Option(False, "--failed", help="Clear failed tasks only"),
    force: bool = typer.Option(False, "--force", help="Skip confirmation"),
) -> None:
    """Remove pending tasks (or all, or only failed ones) from the queue."""
    if not force:
        from rich.prompt import Confirm

        if not Confirm.ask("Clear queue?"):
            console.print("[dim]Cancelled.[/dim]")
            return

    manager = _get_engine()
    if all_tasks:
        count = manager.clear()
        console.print(f"[green]Cleared {count} tasks[/green]")
    elif failed_only:
        count = manager.clear(status=TaskStatus.FAILED)
        console.print(f"[green]Cleared {count} failed tasks[/green]")
    else:
        count = manager.clear(status=TaskStatus.PENDING)
        console.print(f"[green]Cleared {count} pending tasks[/green]")


@app.command("process")
@app.command("p", hidden=True)
def queue_process(
    max_tasks: int = typer.Option(
        0, "--max", "-n", help="Max tasks to process (0=all)"
    ),
) -> None:
    """Run pending tasks now, in this terminal."""
    from max_cli.core.engines.task_manager import TaskManagerError

    console.print("[bold]Processing queue...[/bold]")
    try:
        count = _get_engine().process_now(max_tasks=max_tasks)
    except TaskManagerError as e:
        console.print(f"[yellow]{e}[/yellow]")
        return
    console.print(f"[green]Processed {count} tasks[/green]")


@app.command("start")
def queue_start() -> None:
    """Run the queue in the background; closing the terminal doesn't stop it."""
    from max_cli.core.engines.background_worker import (
        start_background_worker,
        worker_log_path,
    )

    if start_background_worker():
        console.print("[green]Started the background worker.[/green]")
        console.print(
            f"[dim]'max queue status' shows the tasks; its log: {worker_log_path()}[/dim]"
        )
    else:
        console.print("[dim]A worker is already running the queue.[/dim]")


@app.command("worker", hidden=True)
def queue_worker() -> None:
    """The background worker itself: runs the queue until it stays empty."""
    from max_cli.core.engines.task_manager import WORKER_IDLE_EXIT_SECONDS

    ran = _get_engine().run_until_idle(idle_seconds=WORKER_IDLE_EXIT_SECONDS)
    if ran is None:
        console.print("Another worker is running the queue.")
    else:
        console.print(f"Ran {ran} tasks.")


@app.command("stats")
def queue_stats() -> None:
    """Show task counts by status and by type."""
    stats = _get_engine().get_stats()

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
