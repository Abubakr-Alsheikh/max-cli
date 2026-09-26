"""Run or queue a catalog action from loose values (form fields, agent JSON, task payloads).

The CLI calls operations directly, with values Typer already parsed. The
dashboard, the agent and the task queue pass strings or JSON, so they come
through `coerce_args` here first.
"""

import importlib
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from max_cli.common.exceptions import ProcessingError, ValidationError
from max_cli.core.catalog import get_action
from max_cli.core.catalog.spec import PATH_KINDS, Action, Param, ParamKind
from max_cli.core.engines.task_queue import TaskItem, TaskType, register_executor

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
        if _is_empty(value):
            if param.required:
                raise ValidationError(f"{action.id}: '{param.name}' is required")
            args[param.name] = param.resolved_default()
        else:
            args[param.name] = _coerce(action, param, value)
    return args


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


def enqueue_action(action: Action, raw_args: Mapping[str, Any]) -> TaskItem:
    """Check the arguments now, then add the action to the task queue."""
    if not action.queueable:
        raise ValidationError(f"{action.id} can't be queued")
    args = coerce_args(action, raw_args)
    target = args.get("target")
    subject = target.name if isinstance(target, Path) else ""
    task = TaskItem(
        type=TaskType.ACTION,
        title=f"{action.group} {action.name} {subject}".strip(),
        description=action.summary,
        payload={"action": action.id, "args": _json_safe(args)},
    )
    from max_cli.core.engines.task_manager import get_task_manager

    get_task_manager().add(task)
    return task


def _action_executor(task: TaskItem) -> dict[str, Any]:
    action = get_action(task.payload["action"])
    result = run_action(action, task.payload.get("args", {}))
    if not result.ok:
        raise ProcessingError(result.message)
    output_files = [str(path) for path in result.output_files]
    return {
        "output_files": output_files,
        "output_path": output_files[0] if output_files else None,
        "message": result.message,
    }


register_executor(TaskType.ACTION, _action_executor)
