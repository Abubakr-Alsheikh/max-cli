# Workers and Pilot testing (verified on Textual 8.2.7)

Every snippet below ran on Textual 8.2.7. Max CLI's dashboard (`src/max_cli/interface/tui/`) must never block the event loop. Run engine calls in thread workers.

## Thread worker for blocking engine calls

```python
from __future__ import annotations  # Python 3.9: keeps `X | None` annotations lazy

import time
from textual import on, work
from textual.app import App, ComposeResult
from textual.widgets import Button, Label
from textual.worker import Worker, WorkerState, get_current_worker


class Panel(App):
    def compose(self) -> ComposeResult:
        yield Label("idle", id="status")
        yield Button("Go", id="go")

    @on(Button.Pressed, "#go")
    def start(self) -> None:
        self.set_status("running")
        self.run_job(3)  # decorated method returns a Worker immediately

    @work(thread=True, exclusive=True, group="jobs")
    def run_job(self, steps: int) -> int:
        worker = get_current_worker()
        for step in range(steps):
            if worker.is_cancelled:  # exclusive=True cancels the previous run
                return -1
            time.sleep(0.01)  # stands in for a blocking engine call
            self.call_from_thread(self.set_status, f"step {step}")  # UI from thread
        return steps

    def set_status(self, text: str) -> None:
        self.query_one("#status", Label).update(text)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state == WorkerState.SUCCESS:
            self.set_status(f"result {event.worker.result}")
        elif event.state == WorkerState.ERROR:
            self.notify(str(event.worker.error), severity="error")
```

Rules:
- `@work(thread=True)` goes on a **sync** method. From that thread, touch widgets only through `self.call_from_thread(fn, *args)`.
- `@work` on an **async** method runs on the event loop. Update widgets directly there. `call_from_thread` raises `RuntimeError` inside an async worker.
- Don't use `run_worker(self.fn(), thread=True)` for sync code. It calls `fn` right away and passes the result. Pass the callable instead: `run_worker(self.fn, thread=True)`.
- `exclusive=True` plus `group=` cancels the earlier run in the same group. A thread worker has to poll `get_current_worker().is_cancelled` to notice.
- Engine progress arrives through `EventEmitter`. Subscribe in `on_mount`, and forward events to the UI with `call_from_thread` when they fire off the main thread.

## Other 8.x API facts (older docs get these wrong)
- Theme: `self.theme = "textual-dark"`. `App.dark` and `ENABLE_DARK_MODE` no longer exist.
- `DataTable` Enter fires `RowSelected` only when `cursor_type = "row"`; the default `"cell"` fires `CellSelected`. The row key is `event.row_key.value`.
- `SCREENS = {"name": ScreenClass}` takes classes or callables, not instances.
- TCSS has no `darken()`, `lighten()`, `fade()`, `var()`, `font-weight` or `::-webkit-scrollbar`. Use `$variables` and `text-style: bold`.

## Pilot tests (pytest-asyncio)

```python
import pytest
from textual.widgets import Label


@pytest.mark.asyncio
async def test_job_reports_result():
    app = Panel()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.click("#go")
        await app.workers.wait_for_complete()  # let workers finish
        await pilot.pause()                    # let posted messages process
        assert str(app.query_one("#status", Label).render()) == "result 3"
```

- Always pass `size=` so the layout is deterministic.
- After triggering work, run `await app.workers.wait_for_complete()` and then `await pilot.pause()`. Asserting without them makes tests flaky.
- Drive the app with `pilot.press("enter", "tab")`, `pilot.click("#id")` and `pilot.hover(...)`. Read state with `app.query_one(selector, Type)`.
- Mock engines at the `_get_engine`/executor boundary, never the widget internals. Existing examples live in `tests/interface/tui/`.
