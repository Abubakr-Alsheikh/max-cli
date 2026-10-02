"""What the agent sees of the catalog (PLANS/active/command-catalog.md, step 5).

The first prompt names only the command groups, one line each. The model
calls `load_group` to read a group's actions with their JSON Schema, then
`run_action` to run one. So a request about PDFs never pays for the video
group's twenty options.
"""

import json
from typing import Any

from max_cli.core.catalog import actions_for, group_names, load_group
from max_cli.core.catalog.schema import action_schema
from max_cli.core.catalog.spec import Surface

LOAD_GROUP = "load_group"
RUN_ACTION = "run_action"


def agent_groups() -> list[str]:
    """Groups with at least one action the agent may run."""
    return [name for name in group_names() if actions_for(name, Surface.AGENT)]


def group_lines() -> str:
    """One line per group for the system prompt: its summary and its action
    names, so the model knows which group to load ("files ... preview")."""
    lines = []
    for name in agent_groups():
        actions = ", ".join(action.name for action in actions_for(name, Surface.AGENT))
        lines.append(f"- {name}: {load_group(name).summary} Actions: {actions}.")
    return "\n".join(lines)


def group_actions(name: str) -> str:
    """A group's agent actions as compact JSON: what `load_group` returns."""
    schemas = [action_schema(action) for action in actions_for(name, Surface.AGENT)]
    return json.dumps(schemas, separators=(",", ":"), ensure_ascii=False)


def tool_definitions() -> list[dict[str, Any]]:
    """The two tools, in the OpenAI chat-completions format."""
    return [
        {
            "type": "function",
            "function": {
                "name": LOAD_GROUP,
                "description": (
                    "List a command group's actions with their arguments. Call "
                    "it before running an action of that group."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "enum": agent_groups()},
                    },
                    "required": ["name"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": RUN_ACTION,
                "description": (
                    "Run one action, such as video.compress, with arguments "
                    "that match the schema load_group returned."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": "The action id, e.g. pdf.merge.",
                        },
                        "arguments": {
                            "type": "object",
                            "description": "Argument names and values.",
                        },
                    },
                    "required": ["action", "arguments"],
                    "additionalProperties": False,
                },
            },
        },
    ]
