"""JSON Schema for catalog actions: the agent's tool definitions."""

from typing import Any

from max_cli.core.catalog.spec import Action, Param, ParamKind

_JSON_TYPES = {
    ParamKind.INT: "integer",
    ParamKind.FLOAT: "number",
    ParamKind.BOOL: "boolean",
}


def _param_schema(param: Param) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": _JSON_TYPES.get(param.kind, "string"),
        "description": param.help,
    }
    if param.kind == ParamKind.CHOICE:
        schema["enum"] = list(param.choices)
    if not param.required and param.default is not None:
        schema["default"] = param.default
    return schema


def action_schema(action: Action) -> dict[str, Any]:
    """A tool definition: name, description and a JSON Schema for the arguments."""
    return {
        "name": action.id,
        "description": f"{action.summary} (danger: {action.danger.value})",
        "parameters": {
            "type": "object",
            "properties": {param.name: _param_schema(param) for param in action.params},
            "required": [param.name for param in action.params if param.required],
            "additionalProperties": False,
        },
    }
