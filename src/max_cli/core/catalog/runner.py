"""Run or queue a catalog action from loose values (form fields, agent JSON, task payloads).

The CLI calls operations directly, with values Typer already parsed. The
dashboard, the agent and the task queue pass strings or JSON, so they come
through `coerce_args` here first.
"""

import importlib
import inspect
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from max_cli.common.exceptions import ProcessingError, ValidationError
from max_cli.core.catalog import get_action
from max_cli.core.catalog.spec import (
    LIST_SEPARATOR,
    PATH_KINDS,
    Action,
    Param,
    ParamKind,
)
from max_cli.core.engines.task_queue import (
    TaskItem,
    TaskStatus,
    TaskType,
    register_executor,
)

if TYPE_CHECKING:
    from max_cli.core.operations.result import ActionResult

TRUE_WORDS = frozenset({"true", "yes", "y", "1", "on"})
FALSE_WORDS = frozenset({"false", "no", "n", "0", "off"})


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _coerce(action: Action, param: Param, value: Any) -> Any:
    kind = param.kind
    try:
        if kind in PATH_KINDS:
            return Path(str(value)).expanduser()
        if kind == ParamKind.INT:
            return int(value)
        if kind == ParamKind.FLOAT:
            return float(value)
        if kind == ParamKind.BOOL:
            if isinstance(value, bool):
                return value
            word = str(value).strip().lower()
            if word in TRUE_WORDS:
                return True
            if word in FALSE_WORDS:
                return False
            raise ValueError(value)
    except ValueError:
        raise ValidationError(
            f"{action.id}: '{param.name}' expects {kind.value}, got {value!r}"
        ) from None
    text = str(value)
    if kind == ParamKind.CHOICE and text not in param.choices:
        raise ValidationError(
            f"{action.id}: '{param.name}' must be one of {', '.join(param.choices)}"
        )
    return text


def coerce_args(action: Action, raw_args: Mapping[str, Any]) -> dict[str, Any]:
    """Typed keyword arguments for the operation. Empty values fall back to defaults."""
    known = {param.name for param in action.params}
    unknown = sorted(set(raw_args) - known)
    if unknown:
        raise ValidationError(f"{action.id}: unknown option(s) {', '.join(unknown)}")

    args: dict[str, Any] = {}
    for param in action.params:
        value = raw_args.get(param.name)
        if param.multiple and not _is_empty(value):
            items = _list_items(value)
            value = [_coerce(action, param, item) for item in items] or None
        if _is_empty(value) or value == []:
            if param.required:
                raise ValidationError(f"{action.id}: '{param.name}' is required")
            args[param.name] = param.resolved_default()
        elif param.multiple:
            args[param.name] = value
        else:
            args[param.name] = _coerce(action, param, value)
    return args


def _list_items(value: Any) -> list[Any]:
    """A list as given, or form text split on LIST_SEPARATOR, blanks dropped."""
    items = (
        value if isinstance(value, (list, tuple)) else str(value).split(LIST_SEPARATOR)
    )
    return [
        item.strip() if isinstance(item, str) else item
        for item in items
        if not _is_empty(item)
    ]


def _operation(action: Action) -> Callable[..., "ActionResult"]:
    module_name, _, function_name = action.operation.partition(":")
    operation: Callable[..., ActionResult] = getattr(
        importlib.import_module(module_name), function_name
    )
    return operation


def run_action(
    action: Action, raw_args: Mapping[str, Any], **operation_kwargs: Any
) -> "ActionResult":
    return _operation(action)(**coerce_args(action, raw_args), **operation_kwargs)


def _json_safe(args: Mapping[str, Any]) -> dict[str, Any]:
    return {
        name: str(value) if isinstance(value, Path) else value
        for name, value in args.items()
    }


def enqueue_action(
    action: Action, raw_args: Mapping[str, Any], title: Optional[str] = None
) -> TaskItem:
    """Check the arguments now, then add the action to the task queue.

    `title` names the job in the queue (e.g. a video's title); without it the
    job is named after the action and its file or link.
    """
    if not action.queueable:
        raise ValidationError(f"{action.id} can't be queued")
    args = coerce_args(action, raw_args)
    target = args.get("target")
    subject = target.name if isinstance(target, Path) else str(args.get("url") or "")
    task = TaskItem(
        type=TaskType.ACTION,
        title=title or f"{action.group} {action.name} {subject}".strip(),
        description=action.summary,
        payload={"action": action.id, "args": _json_safe(args)},
    )
    from max_cli.core.engines.task_manager import get_task_manager

    get_task_manager().add(task)
    return task


def _download_progress(task: TaskItem) -> Callable[[dict[str, Any]], None]:
    """A yt-dlp progress hook that writes percent, speed and ETA onto the task.

    speed and eta are text fields on TaskItem: a number assigned there saves
    fine but fails validation when the store is read back.
    """
    from max_cli.common.utils import format_size

    def record(status: dict[str, Any]) -> None:
        if status.get("status") != "downloading":
            return
        total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
        if total:
            task.progress = round(status.get("downloaded_bytes", 0) / total * 100, 1)
        speed = status.get("speed")
        task.speed = f"{format_size(speed)}/s" if speed else ""
        eta = status.get("eta")
        task.eta = _clock(int(eta)) if eta else ""

    return record


def _clock(seconds: int) -> str:
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"


def _task_hooks(task: TaskItem, operation: Callable[..., Any]) -> dict[str, Any]:
    """Cancel and progress hooks for operations that take them.

    Cancelling a running task only marks it CANCELLED; the operation sees
    that through should_cancel and stops (grab.download removes its partial
    files).
    """
    accepted = inspect.signature(operation).parameters
    hooks: dict[str, Any] = {}
    if "should_cancel" in accepted:
        hooks["should_cancel"] = lambda: task.status == TaskStatus.CANCELLED
    if "progress_hook" in accepted:
        hooks["progress_hook"] = _download_progress(task)
    return hooks


def _action_executor(task: TaskItem) -> dict[str, Any]:
    action = get_action(task.payload["action"])
    hooks = _task_hooks(task, _operation(action))
    result = run_action(action, task.payload.get("args", {}), **hooks)
    if not result.ok:
        raise ProcessingError(result.message)
    output_files = [str(path) for path in result.output_files]
    return {
        "output_files": output_files,
        "output_path": output_files[0] if output_files else None,
        "message": result.message,
    }


register_executor(TaskType.ACTION, _action_executor)
