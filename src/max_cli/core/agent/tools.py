"""What the agent sees of the catalog (PLANS/active/command-catalog.md, step 5).

The first prompt names only the command groups, one line each. The model
calls `load_group` to read a group's actions with their JSON Schema, then
`run_action` to run one. So a request about PDFs never pays for the video
group's twenty options. `list_folder` and `inspect` (`looks.py`) let it see
the files first; they change nothing.
"""

import json
from typing import Any

from max_cli.core.catalog import actions_for, group_names, load_group
from max_cli.core.catalog.schema import action_schema
from max_cli.core.catalog.spec import Surface

LOAD_GROUP = "load_group"
RUN_ACTION = "run_action"
LIST_FOLDER = "list_folder"
INSPECT = "inspect"
LOOK_TOOLS = (LIST_FOLDER, INSPECT)


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


def _path_tool(name: str, description: str) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "A file or folder; relative paths start "
                        "in the user's folder.",
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    }


def tool_definitions() -> list[dict[str, Any]]:
    """The tools, in the OpenAI chat-completions format."""
    return [
        _path_tool(
            LIST_FOLDER,
            "See what a folder holds: subfolders, files with kind and size, "
            "counts by kind. Changes nothing.",
        ),
        _path_tool(
            INSPECT,
            "Facts about a file or folder: a song's tags (artist, album ...), "
            "a video's length and codecs, an image's size and camera, a PDF's "
            "pages; for a music or photo folder, a summary. Changes nothing.",
        ),
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
