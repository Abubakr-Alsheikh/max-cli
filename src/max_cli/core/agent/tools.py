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
FIND_FILES = "find_files"
PROBE_LINK = "probe_link"
RECENT_ACTIVITY = "recent_activity"
JOB_STATUS = "job_status"
REMEMBER = "remember"
FORGET = "forget"
LOOK_TOOLS = (
    LIST_FOLDER,
    INSPECT,
    FIND_FILES,
    PROBE_LINK,
    RECENT_ACTIVITY,
    JOB_STATUS,
)
MEMORY_TOOLS = (REMEMBER, FORGET)
TOOL_NAMES = (*LOOK_TOOLS, *MEMORY_TOOLS, LOAD_GROUP, RUN_ACTION)
# run_action's `select`: limits for the files a folder or pattern gives.
SELECT_FIELDS = (
    "recursive",
    "redo",
    "name",
    "min_size_mb",
    "max_size_mb",
    "newer_than_days",
    "older_than_days",
)


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


def _tool(
    name: str, description: str, properties: dict[str, Any], required: list[str]
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


def _look_definitions() -> list[dict[str, Any]]:
    """find_files, probe_link and recent_activity."""
    from max_cli.common.file_kinds import KIND_SUFFIXES

    number = {"type": "number"}
    return [
        _tool(
            FIND_FILES,
            "Search a folder and its subfolders. Every filter is optional; "
            "use it for 'videos over 1 GB', 'photos from this year', 'what's "
            "taking space'. Changes nothing.",
            {
                "path": {"type": "string", "description": "Folder to search."},
                "kind": {"type": "string", "enum": sorted(KIND_SUFFIXES)},
                "name": {
                    "type": "string",
                    "description": "A name pattern, e.g. *.mp4 or invoice.",
                },
                "min_size_mb": number,
                "max_size_mb": number,
                "newer_than_days": number,
                "older_than_days": number,
                "sort": {
                    "type": "string",
                    "enum": ["size", "newest", "oldest", "name"],
                },
                "missing": {
                    "type": "string",
                    "description": "An extension, e.g. mp3: only files "
                    "without a same-name file of that type beside them.",
                },
            },
            ["path"],
        ),
        _tool(
            PROBE_LINK,
            "See what a video or playlist link holds before downloading it: "
            "title, length, qualities with sizes, playlist items. Changes nothing.",
            {"url": {"type": "string"}},
            ["url"],
        ),
        _tool(
            RECENT_ACTIVITY,
            "What Max did lately (actions, requests, results, files made) and "
            "the file changes undo can still reverse. Use it for 'undo that' or "
            "'what did I do yesterday'.",
            {"limit": {"type": "integer", "description": "How many, at most 15."}},
            [],
        ),
        _tool(
            JOB_STATUS,
            "Queued jobs: running and waiting ones with progress, then the "
            "latest finished ones with errors and outputs.",
            {"limit": {"type": "integer", "description": "How many, at most 15."}},
            [],
        ),
        _tool(
            REMEMBER,
            "Save one lasting fact or preference the user gave, for later "
            "sessions, e.g. 'Music lives in D:/Music'.",
            {"text": {"type": "string"}},
            ["text"],
        ),
        _tool(
            FORGET,
            "Delete a saved note by its [id] when it's wrong.",
            {"id": {"type": "string"}},
            ["id"],
        ),
    ]


def tool_definitions(can_queue: bool = False) -> list[dict[str, Any]]:
    """The tools, in the OpenAI chat-completions format. `can_queue` adds the
    run_action option that queues a long job (the dashboard runs the queue)."""
    run_properties: dict[str, Any] = {
        "action": {
            "type": "string",
            "description": "The action id, e.g. pdf.merge.",
        },
        "arguments": {
            "type": "object",
            "description": "Argument names and values.",
        },
        "each": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Files, folders or patterns (*.m4a): one run per file.",
        },
        "select": {
            "type": "object",
            "description": "Which files a folder or pattern gives: recursive "
            "(subfolders), redo (files already done), name (e.g. IMG_*), sizes, ages.",
            "properties": {
                "recursive": {"type": "boolean"},
                "redo": {"type": "boolean"},
                "name": {"type": "string"},
                "min_size_mb": {"type": "number"},
                "max_size_mb": {"type": "number"},
                "newer_than_days": {"type": "number"},
                "older_than_days": {"type": "number"},
            },
            "additionalProperties": False,
        },
    }
    if can_queue:
        run_properties["queue"] = {
            "type": "boolean",
            "description": "Run it in the background instead of waiting: for "
            "long video jobs and downloads. Only queueable actions.",
        }
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
        *_look_definitions(),
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
                    "Run an action, such as video.compress, with arguments "
                    "that match the schema load_group returned. For many files "
                    "use one call: a folder or pattern in `each`, narrowed "
                    "with `select`."
                ),
                "parameters": {
                    "type": "object",
                    "properties": run_properties,
                    "required": ["action", "arguments"],
                    "additionalProperties": False,
                },
            },
        },
    ]
