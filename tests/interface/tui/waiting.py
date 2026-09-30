"""Wait for the dashboard to reach a state, instead of counting pauses.

A fixed number of `pilot.pause()` calls passes on an idle machine and fails
when the full suite runs four Pythons at once; a condition doesn't.
"""

from typing import Any, Callable

from textual.css.query import NoMatches

WAIT_ATTEMPTS = 100
WAIT_STEP_SECONDS = 0.05


async def wait_until(pilot: Any, condition: Callable[[], Any]) -> bool:
    """Pause until `condition()` is true (up to 5 seconds). Returns the last result.

    A condition that raises NoMatches or AttributeError (a widget not
    mounted yet) counts as false.
    """
    for _ in range(WAIT_ATTEMPTS):
        try:
            if condition():
                return True
        except (NoMatches, AttributeError):
            # Not mounted yet: a query finds nothing, or a form is still None.
            pass
        await pilot.pause(WAIT_STEP_SECONDS)
    return bool(condition())
