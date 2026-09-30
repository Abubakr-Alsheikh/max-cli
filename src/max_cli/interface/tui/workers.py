"""Hand a thread worker's result to its page.

A thread worker can finish after the app starts shutting down. Its page's
widgets are gone by then, and updating them raised NoMatches, which failed
the worker and, in tests, the test that happened to be closing. It happened
with the Settings sizes, the Download page's YouTube-fix check, and the
tool pages' file facts.
"""

from typing import Any, Callable

from textual.css.query import NoMatches
from textual.widget import Widget


def show_from_worker(page: Widget, show: Callable[..., None], *args: Any) -> None:
    """From a thread worker: run `show(*args)` on the UI thread, unless `page`
    is closing by then."""
    page.app.call_from_thread(_show_if_open, page, show, *args)


def _show_if_open(page: Widget, show: Callable[..., None], *args: Any) -> None:
    if not page.is_attached:
        return
    try:
        show(*args)
    except NoMatches:
        return  # the page's widgets were already removed
