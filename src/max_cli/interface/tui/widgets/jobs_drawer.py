"""The Jobs window: queued work, live, above the footer.

`J` opens and closes it, and it opens by itself when something is queued.
It shows the running job with its progress, speed and time left, then the
waiting jobs, then the last few finished ones. While open it checks the
queue once a second and redraws only when something changed.
"""

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.content import Content
from textual.message import Message
from textual.timer import Timer
from textual.widgets import Static

from max_cli.core.engines.task_queue import TaskItem, TaskStatus
from max_cli.interface.tui.widgets.sidebar import SECTION_KEYS

REFRESH_SECONDS = 1.0
FINISHED_SHOWN = 3
BAR_WIDTH = 16
# Width before the title on every row: mark (2) + " 42% " (5) + bar + 2.
STATE_WIDTH = 2 + 5 + BAR_WIDTH + 2
TITLE_WIDTH = 48
FULL_BLOCK = "█"

FINISHED_LOOK = {
    TaskStatus.COMPLETED: ("✓ done     ", "$success"),
    TaskStatus.FAILED: ("✗ failed   ", "$error"),
    TaskStatus.CANCELLED: ("⊘ cancelled", "$text-muted"),
}


def _title(task: TaskItem) -> str:
    title = task.title or task.description or task.type.value
    if len(title) > TITLE_WIDTH:
        title = title[: TITLE_WIDTH - 1] + "…"
    return f"{title:<{TITLE_WIDTH}}"


def job_line(task: TaskItem) -> Content:
    """One row: state, progress bar for running work, title, speed and ETA."""
    if task.status == TaskStatus.RUNNING:
        filled = round(task.progress / 100 * BAR_WIDTH)
        details = "  ".join(
            part for part in (task.speed, task.eta and f"{task.eta} left") if part
        )
        return Content.assemble(
            # A single-width mark: some fonts draw a triangle two columns wide.
            ("» ", "bold $primary"),
            (f"{task.progress:>3.0f}% ", "bold $primary"),
            (FULL_BLOCK * filled, "$primary"),
            # $border, not $boost: as a text colour $boost came out near-white.
            (FULL_BLOCK * (BAR_WIDTH - filled), "$border"),
            ("  ", ""),
            (_title(task), "bold"),
            (details, "$text-muted"),
        )
    if task.status in (TaskStatus.PENDING, TaskStatus.PAUSED):
        state = "waiting" if task.status == TaskStatus.PENDING else "paused "
        return Content.assemble(
            ("◷ ", "$warning"),
            (f"{state:<{STATE_WIDTH - 2}}", "$warning"),
            (_title(task), ""),
        )
    label, style = FINISHED_LOOK.get(task.status, (task.status.value, ""))
    return Content.assemble(
        (f"{label:<{STATE_WIDTH}}", style),
        (_title(task), "$text-muted"),
        ((task.error or "")[:40], "$error"),
    )


class JobsDrawer(Vertical):
    """Docked at the bottom of the screen; hidden until opened."""

    DEFAULT_CSS = """
    /* Not docked: the Footer docks at the bottom and would cover it. As a
       normal child after the main area it takes its rows from the page. */
    JobsDrawer {
        height: auto;
        max-height: 14;
        background: $surface;
        border-top: heavy $accent;
        padding: 0 2;
        display: none;
    }
    JobsDrawer.-open {
        display: block;
    }
    #jobs-title {
        height: 1;
        margin-bottom: 1;
    }
    #jobs-list {
        height: auto;
    }
    #jobs-hint {
        height: 1;
        margin-top: 1;
        color: $text-muted;
    }
    """

    class Show(Message):
        """Ask the app to open the Jobs window (e.g. after queueing)."""

    def __init__(self, *, id: str) -> None:
        super().__init__(id=id)
        self._timer: Optional[Timer] = None
        self._shown: Optional[tuple[str, ...]] = None

    def compose(self) -> ComposeResult:
        yield Static("", id="jobs-title")
        yield Static("", id="jobs-list")
        yield Static(
            Content(
                f"J closes this  ·  {SECTION_KEYS['activity']} opens Activity "
                "to cancel or retry"
            ),
            id="jobs-hint",
        )

    @property
    def is_open(self) -> bool:
        return self.has_class("-open")

    def show_jobs(self) -> None:
        self.add_class("-open")
        self.refresh_jobs()
        if self._timer is None:
            self._timer = self.set_interval(REFRESH_SECONDS, self.refresh_jobs)
        else:
            self._timer.resume()

    def hide_jobs(self) -> None:
        self.remove_class("-open")
        if self._timer is not None:
            self._timer.pause()

    def toggle(self) -> None:
        if self.is_open:
            self.hide_jobs()
        else:
            self.show_jobs()

    def refresh_jobs(self) -> None:
        from max_cli.core.engines.task_manager import get_task_manager

        manager = get_task_manager()
        queued = manager.get_all()
        running = [task for task in queued if task.status == TaskStatus.RUNNING]
        waiting = [task for task in queued if task.status != TaskStatus.RUNNING]
        finished = manager.get_history(limit=FINISHED_SHOWN)
        lines = [job_line(task) for task in running + waiting + finished]
        signature = tuple(line.plain for line in lines)
        if signature == self._shown:
            return
        self._shown = signature
        title = Content.assemble(
            ("JOBS", "bold $accent"),
            (f"   {len(running)} running  ·  {len(waiting)} waiting", "$text-muted"),
        )
        empty = Content.styled(
            'Nothing queued. Use "Queue for later" on the Download or Tools page.',
            "$text-muted",
        )
        with self.app.batch_update():
            self.query_one("#jobs-title", Static).update(title)
            self.query_one("#jobs-list", Static).update(
                Content("\n").join(lines) if lines else empty
            )
