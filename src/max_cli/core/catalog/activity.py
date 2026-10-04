"""Actions in the activity log, whoever runs them.

The dashboard's Home and History, and the agent's recent_activity, read the
activity log. The dashboard's forms and the agent log their own runs; this
module logs the rest: CLI commands, CLI batches, queued tasks when the
worker finishes them, and the Download page.

Logging never fails the work: a log that can't be written is a warning.
"""

import logging
import time
from collections.abc import Mapping
from functools import cache
from typing import Any, Callable, Optional, TypeVar

from max_cli.core.catalog.spec import Action
from max_cli.core.operations.result import ActionResult

logger = logging.getLogger(__name__)

# Keyword arguments that are tools, not the user's choices.
NOT_ARGUMENTS = frozenset({"engine", "emitter", "should_cancel", "progress_hook"})
MS_PER_SECOND = 1000

# What the operation returns: an ActionResult, or a helper's own value.
ResultT = TypeVar("ResultT")


def record(
    action: Action,
    args: Mapping[str, Any],
    result: Optional[ActionResult] = None,
    error: str = "",
    seconds: float = 0.0,
    via: str = "",
) -> None:
    """One finished run of `action`: its result, or the error that stopped it."""
    from max_cli.common.activity_log import ActivityLog

    details: dict[str, Any] = {
        "args": {
            name: _text(value)
            for name, value in args.items()
            if name not in NOT_ARGUMENTS and value not in (None, "", False, [])
        }
    }
    if via:
        details["via"] = via
    if result is not None:
        details.update(result.to_dict())
        status = "success" if result.ok else "failed"
    else:
        details["error"] = error
        status = "failed"
    try:
        ActivityLog().add_entry(
            action.group,
            action.name,
            status,
            details,
            duration_ms=int(seconds * MS_PER_SECOND),
        )
    except (OSError, TypeError, ValueError) as e:  # a file error, or details
        # that aren't JSON: the work itself went fine
        logger.warning("Couldn't log %s in the activity log: %s", action.id, e)


def run_recorded(
    operation: Callable[..., ResultT], via: str = "cli", **kwargs: Any
) -> ResultT:
    """Call an operation and log the run under its catalog action. An
    operation the catalog doesn't list runs without a log entry."""
    action = action_for(operation)
    started = time.monotonic()
    try:
        result = operation(**kwargs)
    except Exception as e:
        if action is not None:
            record(action, kwargs, error=str(e), seconds=_since(started), via=via)
        raise
    if action is not None and isinstance(result, ActionResult):
        record(action, kwargs, result, seconds=_since(started), via=via)
    return result


def action_for(operation: Callable[..., Any]) -> Optional[Action]:
    """The catalog action whose operation this is."""
    name = (
        f"{getattr(operation, '__module__', '')}:{getattr(operation, '__name__', '')}"
    )
    return _actions_by_operation().get(name)


@cache
def _actions_by_operation() -> dict[str, Action]:
    from max_cli.core.catalog import group_names, load_group

    return {
        action.operation: action
        for group in group_names()
        for action in load_group(group).actions
    }


def _since(started: float) -> float:
    return time.monotonic() - started


def _text(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    return value if isinstance(value, (int, float, bool)) else str(value)
