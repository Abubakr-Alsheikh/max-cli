"""The Activity page's Queue tab: the work the dashboard runs, one task at a time.

- Tiles count what's running and waiting, and what finished or failed today.
- NOW RUNNING shows the running task with its progress, speed and time left.
- UP NEXT lists the waiting tasks in order, each with Pause or Resume and
  Cancel, plus Pause all, Resume all and Clear waiting.
- FINISHED shows the last few tasks with Retry, Run again or Open folder.

The app refreshes this page every 2 seconds while it shows. Rows update in
place; a list is rebuilt only when its tasks or their order change.
The Jobs window (`J`) shows the same queue from any page.
"""

from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.content import Content
from textual.message import Message
from textual.widgets import Button, Digits, Static

from max_cli.common.utils import format_size
from max_cli.core.engines.task_manager import get_task_manager
from max_cli.core.engines.task_queue import TaskItem, TaskStatus, TaskType
from max_cli.interface.tui.messages import OpenPage
from max_cli.interface.tui.text import relative_time
from max_cli.interface.tui.widgets.charts import Meter

FINISHED_SHOWN = 8
SEPARATOR = "  ·  "
WAITING_STATES = (TaskStatus.PENDING, TaskStatus.PAUSED)
# The buttons each state offers: (label, what it does).
ROW_ACTIONS: dict[TaskStatus, tuple[tuple[str, str], ...]] = {
    TaskStatus.RUNNING: (("Cancel", "cancel"),),
    TaskStatus.PENDING: (("Pause", "pause"), ("Cancel", "cancel")),
    TaskStatus.PAUSED: (("Resume", "resume"), ("Cancel", "cancel")),
    TaskStatus.FAILED: (("Retry", "retry"),),
    TaskStatus.CANCELLED: (("Retry", "retry"),),
}
STATE_CLASSES = {
    TaskStatus.RUNNING: "-running",
    TaskStatus.PENDING: "-waiting",
    TaskStatus.PAUSED: "-paused",
    TaskStatus.COMPLETED: "-done",
    TaskStatus.FAILED: "-failed",
    TaskStatus.CANCELLED: "-cancelled",
}
ACTION_STYLES = {
    "cancel": "-cancel",
    "retry": "-retry",
    "again": "-retry",
    "open": "-open",
}


def task_kind(task: TaskItem) -> str:
    """What a task does, in words: "grab download", "video compress"."""
    if task.type == TaskType.ACTION:
        return str(task.payload.get("action", "action")).replace(".", " ")
    return task.type.value.replace("_", " ")


def task_title(task: TaskItem) -> str:
    return task.title or task.description or task_kind(task)


def row_actions(task: TaskItem) -> tuple[tuple[str, str], ...]:
    """The buttons a task's row offers in its current state."""
    if task.status == TaskStatus.COMPLETED:
        if task.output_files:
            return (("Open folder", "open"), ("Run again", "again"))
        return (("Run again", "again"),)
    return ROW_ACTIONS.get(task.status, ())


def task_info(task: TaskItem, position: int = 0) -> Content:
    """The muted line under a task's title: progress, place in line, or result."""
    kind = task_kind(task)
    if task.status == TaskStatus.RUNNING:
        return Content.assemble(
            (f"{task.progress:.0f}%", "bold $primary"),
            (
                SEPARATOR
                + SEPARATOR.join(
                    part
                    for part in (
                        task.speed,
                        f"{task.eta} left" if task.eta else "",
                        kind,
                        f"started {relative_time(task.started_at)}"
                        if task.started_at
                        else "",
                    )
                    if part
                ),
                "$text-muted",
            ),
        )
    if task.status in WAITING_STATES:
        state = (
            ("Paused", "bold $warning")
            if task.status == TaskStatus.PAUSED
            else (f"#{position} in line", "bold $warning")
        )
        added = f"added {relative_time(task.created_at)}"
        return Content.assemble(
            state, (f"{SEPARATOR}{kind}{SEPARATOR}{added}", "$text-muted")
        )
    when = relative_time(task.completed_at)
    if task.status == TaskStatus.FAILED:
        return Content.assemble(
            ("Failed: ", "bold $error"),
            (task.error or "no reason given", "$error"),
            (f"{SEPARATOR}{kind}{SEPARATOR}{when}", "$text-muted"),
        )
    if task.status == TaskStatus.CANCELLED:
        return Content.assemble(
            ("Cancelled", "bold $warning"),
            (f"{SEPARATOR}{kind}{SEPARATOR}{when}", "$text-muted"),
        )
    size = int(
        task.result.get("file_size")
        or task.result.get("details", {}).get("size_bytes")
        or 0
    )
    files = len(task.output_files)
    return Content.assemble(
        ("Done", "bold $success"),
        (
            SEPARATOR
            + SEPARATOR.join(
                part
                for part in (
                    f"{files} file{'s' if files != 1 else ''}" if files else "",
                    format_size(size) if size else "",
                    kind,
                    when,
                )
                if part
            ),
            "$text-muted",
        ),
    )


class TaskRow(Vertical):
    """One task: title and one-line buttons, a progress bar while it runs, info.

    Rows have no widget id: a task moving from UP NEXT to NOW RUNNING gets a
    new row while the old one is still being removed.
    """

    DEFAULT_CSS = """
    TaskRow {
        height: auto;
        background: $boost 40%;
        border-left: outer $border;
        padding: 0 1 0 2;
        margin-bottom: 1;
    }
    TaskRow.-running {
        border-left: outer $primary;
    }
    TaskRow.-waiting, TaskRow.-paused {
        border-left: outer $warning;
    }
    TaskRow.-done {
        border-left: outer $success;
    }
    TaskRow.-failed {
        border-left: outer $error;
    }
    TaskRow .row-head {
        height: 1;
    }
    TaskRow .row-title {
        width: 1fr;
        height: 1;
        text-style: bold;
    }
    TaskRow .row-buttons {
        width: auto;
        height: 1;
    }
    TaskRow .row-info {
        height: auto;
    }
    TaskRow Button.row-action,
    TaskRow Button.row-action:hover,
    TaskRow Button.row-action:focus,
    TaskRow Button.row-action.-active {
        height: 1;
        min-width: 12;
        margin-left: 1;
        border: none;
        background: $boost;
        text-style: bold;
    }
    TaskRow Button.row-action:hover {
        background: $primary 30%;
    }
    TaskRow Button.-cancel {
        color: $error;
    }
    TaskRow Button.-retry {
        color: $warning;
    }
    TaskRow Button.-open {
        color: $success;
    }
    """

    class Action(Message):
        """A row's button was pressed: `action` on task `task_id`."""

        def __init__(self, task_id: str, action: str) -> None:
            super().__init__()
            self.task_id = task_id
            self.action = action

    def __init__(self, task: TaskItem, position: int = 0) -> None:
        super().__init__()
        self.task_id = task.id
        self._item = task  # not _task: MessagePump uses that name
        self._position = position
        self._shown: Optional[tuple[Any, ...]] = None
        self._actions: tuple[tuple[str, str], ...] = ()
        self._ready = False  # composed; show() before that only stores the task

    def compose(self) -> ComposeResult:
        with Horizontal(classes="row-head"):
            yield Static("", classes="row-title")
            yield Horizontal(classes="row-buttons")
        yield Meter(classes="row-meter")
        yield Static("", classes="row-info")

    def on_mount(self) -> None:
        self._ready = True
        self.show(self._item, self._position)

    def show(self, task: TaskItem, position: int = 0) -> None:
        """Draw `task`; nothing happens when nothing it shows changed."""
        self._item, self._position = task, position
        signature = (
            task.status,
            task.title,
            round(task.progress),
            task.speed,
            task.eta,
            task.error,
            position,
            relative_time(task.completed_at or task.started_at or task.created_at),
        )
        if signature == self._shown or not self._ready:
            return
        state_changed = self._shown is None or self._shown[0] != task.status
        self._shown = signature
        running = task.status == TaskStatus.RUNNING
        with self.app.batch_update():
            if state_changed:
                for status_class in STATE_CLASSES.values():
                    self.remove_class(status_class)
                self.add_class(STATE_CLASSES.get(task.status, ""))
                self.query_one(".row-title", Static).update(Content(task_title(task)))
                self.query_one(Meter).display = running
                self._set_buttons(row_actions(task))
            if running:
                self.query_one(Meter).set_value(task.progress)
            # Progress ticks change one line of the same length: no layout.
            self.query_one(".row-info", Static).update(
                task_info(task, position), layout=state_changed
            )

    def _set_buttons(self, actions: tuple[tuple[str, str], ...]) -> None:
        if actions == self._actions:
            return
        self._actions = actions
        holder = self.query_one(".row-buttons", Horizontal)
        holder.remove_children()
        holder.mount_all(
            Button(
                label,
                name=action,
                classes=f"row-action {ACTION_STYLES.get(action, '')}",
            )
            for label, action in actions
        )

    @on(Button.Pressed, ".row-action")
    def _on_button(self, event: Button.Pressed) -> None:
        event.stop()
        self.post_message(self.Action(self.task_id, event.button.name or ""))


class QueueTile(Vertical):
    """One count in big digits with a caption; redraws only on change."""

    def __init__(self, title: str, *, id: str) -> None:
        super().__init__(id=id, classes="queue-card queue-tile")
        self.border_title = title
        self._shown: Optional[tuple[str, str]] = None

    def compose(self) -> ComposeResult:
        yield Digits("0", classes="tile-value")
        yield Static("", classes="tile-note")

    def show(self, value: int, note: str, style: str = "$primary") -> None:
        if (str(value), note) == self._shown:
            return
        self._shown = (str(value), note)
        self.query_one(Digits).update(str(value))
        # Muted at zero, in the tile's colour otherwise (the CSS -lit- rules).
        self.set_class(value > 0, style.replace("$", "-lit-"))
        self.query_one(".tile-note", Static).update(Content.styled(note, "$text-muted"))


class QueuePanel(Vertical):
    """The Activity page's Queue tab (with brand=True, a page of its own)."""

    DEFAULT_CSS = """
    #queue-header {
        height: 3;
        margin-bottom: 1;
    }
    /* Inside the Activity page, whose header says what the page is. */
    #queue-header.-plain {
        height: 1;
    }
    #queue-header.-plain Static {
        height: 1;
    }
    #queue-brand {
        width: 1fr;
        height: 3;
    }
    #queue-worker {
        width: auto;
        height: 3;
        content-align: right middle;
    }
    QueuePanel .queue-card {
        height: auto;
        background: $surface;
        border: round $border;
        border-title-color: $primary;
        border-title-style: bold;
        padding: 0 1;
        margin-bottom: 1;
    }
    QueuePanel .queue-card:focus-within {
        border: round $primary;
    }
    #queue-tiles {
        height: auto;
        grid-size: 4;
        grid-columns: 1fr 1fr 1fr 1fr;
        grid-gutter: 0 2;
        margin-bottom: 1;
    }
    /* Digits take 3 rows and the caption 1: a card margin hid the caption. */
    QueuePanel .queue-tile {
        height: 6;
        margin-bottom: 0;
    }
    QueuePanel .tile-value {
        width: 100%;
        text-align: center;
        color: $text-muted;
        text-style: bold;
    }
    QueuePanel .-lit-primary .tile-value {
        color: $primary;
    }
    QueuePanel .-lit-warning .tile-value {
        color: $warning;
    }
    QueuePanel .-lit-success .tile-value {
        color: $success;
    }
    QueuePanel .-lit-error .tile-value {
        color: $error;
    }
    QueuePanel .tile-note {
        width: 100%;
        text-align: center;
    }
    QueuePanel .queue-list {
        height: auto;
        margin-top: 1;
    }
    QueuePanel .queue-empty {
        color: $text-muted;
        padding: 1 0;
    }
    QueuePanel .queue-bar {
        height: auto;
        margin-bottom: 1;
    }
    """

    def __init__(self, brand: bool = True, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._show_brand = brand
        self._lists: dict[str, list[str]] = {}
        self._worker_shown: Optional[bool] = None

    def compose(self) -> ComposeResult:
        with Horizontal(
            id="queue-header", classes="" if self._show_brand else "-plain"
        ):
            yield Static(self._brand() if self._show_brand else "", id="queue-brand")
            yield Static("", id="queue-worker")
        with Grid(id="queue-tiles"):
            yield QueueTile("RUNNING", id="tile-running")
            yield QueueTile("WAITING", id="tile-waiting")
            yield QueueTile("DONE TODAY", id="tile-done")
            yield QueueTile("FAILED TODAY", id="tile-failed")
        with Vertical(id="queue-now", classes="queue-card"):
            yield Vertical(id="queue-running", classes="queue-list")
            yield Static(
                "Nothing running. Queued work starts here, one task at a time.",
                id="queue-running-empty",
                classes="queue-empty",
            )
        with Vertical(id="queue-next", classes="queue-card"):
            yield Vertical(id="queue-waiting", classes="queue-list")
            yield Static(
                'Nothing waiting. "Queue for later" on the Download page and '
                '"Add to queue" on a Tools form put work here.',
                id="queue-waiting-empty",
                classes="queue-empty",
            )
            with Horizontal(id="queue-next-bar", classes="queue-bar"):
                yield Button("Pause all", id="btn-pause-all")
                yield Button("Resume all", id="btn-resume-all")
                yield Button("Clear waiting", id="btn-clear-waiting", variant="error")
        with Vertical(id="queue-done", classes="queue-card"):
            yield Vertical(id="queue-finished", classes="queue-list")
            yield Static(
                "Nothing finished yet.",
                id="queue-finished-empty",
                classes="queue-empty",
            )
            with Horizontal(id="queue-done-bar", classes="queue-bar"):
                yield Button("All activity (History)", id="btn-goto-history")

    @staticmethod
    def _brand() -> Content:
        return Content.assemble(
            ("◢◤ ", "bold $secondary"),
            ("QUEUE", "bold $primary"),
            (" // TASK CONTROL\n", "bold"),
            (
                # Short enough for 100 columns beside the queue light.
                "One task at a time while the dashboard is open"
                "  ·  J shows it anywhere",
                "$text-muted",
            ),
        )

    def on_mount(self) -> None:
        self.query_one("#queue-now").border_title = "NOW RUNNING"
        self.query_one("#queue-next").border_title = "UP NEXT"
        self.query_one("#queue-done").border_title = "FINISHED"
        self.refresh_data()

    def on_show(self) -> None:
        # The app refreshes every 2 seconds; opening the page shouldn't wait.
        self.refresh_data()

    # --- refresh ------------------------------------------------------------

    def refresh_data(self) -> None:
        manager = get_task_manager()
        manager.refresh()
        queued = list(manager.get_all())
        running = [task for task in queued if task.status == TaskStatus.RUNNING]
        waiting = [task for task in queued if task.status in WAITING_STATES]
        finished = list(manager.get_history(limit=FINISHED_SHOWN))
        today = self._finished_today(manager)
        with self.app.batch_update():
            self._show_worker(bool(manager.is_worker_running))
            self._show_tiles(running, waiting, today)
            self._sync("#queue-running", running)
            self._sync("#queue-waiting", waiting)
            self._sync("#queue-finished", finished)
            self.query_one("#queue-next").border_title = (
                f"UP NEXT ({len(waiting)})" if waiting else "UP NEXT"
            )
            self.query_one("#queue-next-bar").display = bool(waiting)
            self.query_one("#btn-pause-all", Button).disabled = not any(
                task.status == TaskStatus.PENDING for task in waiting
            )
            self.query_one("#btn-resume-all", Button).disabled = not any(
                task.status == TaskStatus.PAUSED for task in waiting
            )

    @staticmethod
    def _finished_today(manager: Any) -> dict[TaskStatus, int]:
        today = date.today()
        counts = {TaskStatus.COMPLETED: 0, TaskStatus.FAILED: 0}
        for task in manager.get_history(limit=0):
            try:
                finished = datetime.fromisoformat(task.completed_at or "").date()
            except (ValueError, TypeError):
                continue
            # Not a break: record() and the migration can add older entries
            # in front, so history isn't strictly newest first.
            if finished != today:
                continue
            if task.status in counts:
                counts[task.status] += 1
        return counts

    def _show_worker(self, on: bool) -> None:
        if on == self._worker_shown:
            return
        self._worker_shown = on
        text = (
            Content.styled("● RUNNING QUEUE", "bold $success")
            if on
            else Content.styled("● QUEUE STOPPED", "bold $text-muted")
        )
        self.query_one("#queue-worker", Static).update(text, layout=False)

    def _show_tiles(
        self,
        running: list[TaskItem],
        waiting: list[TaskItem],
        today: dict[TaskStatus, int],
    ) -> None:
        paused = sum(task.status == TaskStatus.PAUSED for task in waiting)
        self.query_one("#tile-running", QueueTile).show(
            len(running),
            f"{running[0].progress:.0f}% done" if running else "idle",
            "$primary",
        )
        self.query_one("#tile-waiting", QueueTile).show(
            len(waiting), f"{paused} paused" if paused else "in line", "$warning"
        )
        self.query_one("#tile-done", QueueTile).show(
            today[TaskStatus.COMPLETED], "finished today", "$success"
        )
        self.query_one("#tile-failed", QueueTile).show(
            today[TaskStatus.FAILED], "failed today", "$error"
        )

    def _sync(self, list_id: str, tasks: list[TaskItem]) -> None:
        """Show `tasks` in a list: update rows in place, rebuild on a new order."""
        holder = self.query_one(list_id, Vertical)
        ids = [task.id for task in tasks]
        if ids != self._lists.get(list_id):
            self._lists[list_id] = ids
            holder.remove_children()
            holder.mount_all(
                TaskRow(task, position) for position, task in enumerate(tasks, 1)
            )
        else:
            # By task id, last one wins: right after a rebuild the old rows
            # can still be in the list, ahead of their replacements.
            rows = {row.task_id: row for row in holder.query(TaskRow)}
            for position, task in enumerate(tasks, 1):
                rows[task.id].show(task, position)
        holder.display = bool(tasks)
        self.query_one(f"{list_id}-empty").display = not tasks

    # --- actions ------------------------------------------------------------

    def on_task_row_action(self, message: TaskRow.Action) -> None:
        manager = get_task_manager()
        task = manager.get(message.task_id)
        if message.action == "cancel":
            manager.cancel(message.task_id)
        elif message.action == "pause":
            manager.pause(message.task_id)
        elif message.action == "resume":
            manager.resume(message.task_id)
        elif message.action in ("retry", "again"):
            manager.retry(message.task_id)
        elif message.action == "open" and task is not None and task.output_files:
            from max_cli.common.utils import open_in_file_manager

            open_in_file_manager(Path(task.output_files[0]).parent)
        self.refresh_data()

    @on(Button.Pressed, "#btn-pause-all")
    def _on_pause_all(self) -> None:
        manager = get_task_manager()
        for task in manager.get_all(status=TaskStatus.PENDING):
            manager.pause(task.id)
        self.refresh_data()

    @on(Button.Pressed, "#btn-resume-all")
    def _on_resume_all(self) -> None:
        manager = get_task_manager()
        for task in manager.get_all(status=TaskStatus.PAUSED):
            manager.resume(task.id)
        self.refresh_data()

    @on(Button.Pressed, "#btn-clear-waiting")
    def _on_clear_waiting(self) -> None:
        from max_cli.interface.tui.widgets.dialogs import ConfirmDialog

        def _answered(confirmed: Optional[bool]) -> None:
            if not confirmed:
                return
            manager = get_task_manager()
            count = sum(manager.clear(status=status) for status in WAITING_STATES)
            self.refresh_data()
            self.notify(f"Removed {count} waiting task{'s' if count != 1 else ''}.")

        self.app.push_screen(
            ConfirmDialog(
                "Remove every waiting and paused task from the queue? "
                "The running task keeps going."
            ),
            _answered,
        )

    @on(Button.Pressed, "#btn-goto-history")
    def _on_goto_history(self) -> None:
        self.post_message(OpenPage("activity", tab="history"))
