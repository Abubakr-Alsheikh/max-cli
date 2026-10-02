"""The agent loop: ask the model, run the tools it calls, repeat until it answers.

Rules from PLANS/active/dashboard-first-ai-agent.md (D4, step 4):
- It works only through catalog actions; there is no shell tool.
- Every path argument must sit under the allowed folders (`scope`).
- Actions that move, overwrite or delete files need `confirm` to say yes,
  whatever CONFIRM_DESTRUCTIVE says.
- A request stops after MAX_STEPS tool calls or TOKEN_LIMIT tokens.
- `dry_run` checks and reports each action without running it.
"""

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from max_cli.common.exceptions import AIError, ConfigurationError, MaxError
from max_cli.core.agent.scope import PathScope
from max_cli.core.agent.tools import (
    LOAD_GROUP,
    RUN_ACTION,
    agent_groups,
    group_actions,
    group_lines,
    tool_definitions,
)
from max_cli.core.catalog import get_action
from max_cli.core.catalog.spec import PATH_KINDS, Action, Danger, Surface
from max_cli.core.operations.result import ActionResult

logger = logging.getLogger(__name__)

CONFIRM_DANGERS = frozenset({Danger.MOVES, Danger.OVERWRITES, Danger.DELETES})
MAX_STEPS = 12  # tool calls per request
TOKEN_LIMIT = 60_000  # tokens per request, prompts and answers together
MAX_RESULT_CHARS = 4_000  # of an action's result sent back to the model
DECLINED_NOTE = (
    "The user said no, so it didn't run. Don't run it again unless they ask."
)

SYSTEM_PROMPT = """You are Max, an assistant that does file and media work on \
the user's computer by running Max's actions. You can only act through the \
tools; you never run shell commands.

Command groups, with their actions:
{groups}

How to work:
- The user is in {cwd}. "Here", "this folder" and relative paths mean that \
folder; don't ask which folder unless the request names another one.
- Call load_group(name) to see a group's actions and their arguments, then \
run_action(action, arguments). Never invent an action or an argument.
- You may use files under that folder and any folder the user names. If you \
need a folder outside them, ask the user to name it.
- Act; don't ask for permission. Max itself asks the user before an action \
moves, overwrites or deletes files. If they say no, don't retry.
- Run several actions when a request needs them. When you're done, say in one \
or two short sentences what you did and where the results are.
- If no action fits, say so and suggest what Max can do instead."""


class StepKind(str, Enum):
    LOADED = "loaded"  # read a group's actions
    RAN = "ran"  # ran an action and it worked
    FAILED = "failed"  # ran an action and it failed, or its arguments were wrong
    REFUSED = "refused"  # a path outside the allowed folders
    DECLINED = "declined"  # the user said no
    PLANNED = "planned"  # dry run: checked, not run


@dataclass(frozen=True)
class ActionCall:
    """An action the model wants to run, with its checked arguments."""

    action: Action
    arguments: dict[str, Any]

    def describe(self) -> str:
        """`files shred  target=C:\\notes.txt`, for a confirmation question."""
        shown = "  ".join(
            f"{name}={value}"
            for name, value in self.arguments.items()
            if value not in (None, "", False, [])
        )
        return f"{self.action.group} {self.action.name}  {shown}".rstrip()


@dataclass(frozen=True)
class Step:
    """One thing the agent did, for the CLI and the dashboard to show."""

    kind: StepKind
    action_id: str
    text: str
    result: Optional[ActionResult] = None


@dataclass
class AgentReply:
    text: str
    steps: list[Step] = field(default_factory=list)
    tokens: int = 0


Confirm = Callable[[ActionCall], bool]
OnStep = Callable[[Step], None]


def _ignore_step(step: Step) -> None:
    return None


class Agent:
    """One conversation with the model. `ask` can be called again and again;
    the model remembers the earlier requests and the groups it loaded."""

    def __init__(
        self,
        client: Any,
        model: str,
        *,
        confirm: Confirm,
        on_step: Optional[OnStep] = None,
        cwd: Optional[Path] = None,
        dry_run: bool = False,
        max_steps: int = MAX_STEPS,
        token_limit: int = TOKEN_LIMIT,
    ) -> None:
        self.client = client
        self.model = model
        self.confirm = confirm
        self.on_step = on_step or _ignore_step
        self.dry_run = dry_run
        self.max_steps = max_steps
        self.token_limit = token_limit
        self.scope = PathScope(cwd or Path.cwd())
        self.scope.allow(_download_folder())
        self.loaded: set[str] = set()
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt()}
        ]

    @classmethod
    def from_settings(cls, **kwargs: Any) -> "Agent":
        """An agent on the configured provider (settings: AI and Ollama)."""
        from max_cli.core.engines.ai_engine import chat_model, make_client

        client = make_client()
        if client is None:
            raise ConfigurationError(
                "No AI is set up. Add an API key (max config setup, or the "
                "dashboard's Settings page), or turn on Ollama."
            )
        return cls(client, chat_model(), **kwargs)

    def system_prompt(self) -> str:
        """The first prompt: the group list only, never the actions."""
        return SYSTEM_PROMPT.format(groups=group_lines(), cwd=self.scope.cwd)

    # --- the loop -----------------------------------------------------------

    def ask(self, request: str) -> AgentReply:
        """Work on one request until the model answers in words."""
        self.scope.add_from(request)
        self.messages.append({"role": "user", "content": request})
        reply = AgentReply("")
        calls = 0
        while True:
            response = self._complete()
            usage = getattr(response, "usage", None)
            reply.tokens += int(getattr(usage, "total_tokens", 0) or 0)
            message = response.choices[0].message
            tool_calls = list(message.tool_calls or [])
            if not tool_calls:
                reply.text = (message.content or "").strip() or "Done."
                self.messages.append({"role": "assistant", "content": reply.text})
                return reply
            self.messages.append(_assistant_message(message.content, tool_calls))
            for tool_call in tool_calls:
                calls += 1
                if calls > self.max_steps:
                    content = "Not run: the step limit for this request was reached."
                else:
                    content = self._tool(
                        tool_call.function.name, tool_call.function.arguments, reply
                    )
                self.messages.append(
                    {"role": "tool", "tool_call_id": tool_call.id, "content": content}
                )
            limit = self._limit_reached(calls, reply.tokens)
            if limit:
                reply.text = limit
                self.messages.append({"role": "assistant", "content": limit})
                return reply

    def _limit_reached(self, calls: int, tokens: int) -> str:
        if calls >= self.max_steps:
            return (
                f"I stopped after {self.max_steps} steps, the limit for one "
                "request. Ask me to go on if there's more to do."
            )
        if tokens >= self.token_limit:
            return (
                f"I stopped after using {tokens:,} tokens, the limit for one "
                "request. Ask me to go on if there's more to do."
            )
        return ""

    def _complete(self) -> Any:
        from openai import APIError, BadRequestError

        try:
            return self.client.chat.completions.create(
                model=self.model, messages=self.messages, tools=tool_definitions()
            )
        except BadRequestError as e:
            if "tool" in str(e).lower():
                raise AIError(
                    f"The model {self.model} can't call tools, so the agent can't "
                    "use it. Pick one that can (most OpenAI, Gemini, Claude and "
                    "Llama 3.1+ models do)."
                ) from e
            raise AIError(f"The AI refused the request: {e}") from e
        except APIError as e:
            raise AIError(f"The AI didn't answer: {e}") from e

    # --- tools --------------------------------------------------------------

    def _tool(self, name: str, raw_arguments: str, reply: AgentReply) -> str:
        try:
            arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError:
            return "Error: the arguments aren't valid JSON."
        if not isinstance(arguments, dict):
            return "Error: the arguments must be a JSON object."
        if name == LOAD_GROUP:
            return self._load_group(str(arguments.get("name", "")), reply)
        if name == RUN_ACTION:
            given = arguments.get("arguments") or {}
            if not isinstance(given, Mapping):
                return "Error: 'arguments' must be an object."
            return self._run(str(arguments.get("action", "")), dict(given), reply)
        return f"Error: there is no tool '{name}'. Use load_group or run_action."

    def _load_group(self, name: str, reply: AgentReply) -> str:
        if name not in agent_groups():
            return f"Error: no group '{name}'. Groups: {', '.join(agent_groups())}."
        self.loaded.add(name)
        self._report(
            reply, Step(StepKind.LOADED, name, f"Looked up the {name} actions")
        )
        return group_actions(name)

    def _run(self, action_id: str, given: dict[str, Any], reply: AgentReply) -> str:
        from max_cli.core.catalog.runner import coerce_args, run_action

        try:
            action = get_action(action_id)
        except KeyError:
            return f"Error: no action '{action_id}'. Call load_group to see them."
        label = f"{action.group} {action.name}"  # how steps name it
        if Surface.AGENT not in action.surfaces:
            return f"Error: {action_id} isn't available to the agent."
        if action.group not in self.loaded:
            return (
                f"Error: call load_group('{action.group}') first to see its arguments."
            )
        try:
            arguments = coerce_args(action, given)
        except MaxError as e:
            self._report(reply, Step(StepKind.FAILED, action_id, f"{label}: {e}"))
            return f"Error: {e}"

        call = ActionCall(action, arguments)
        outside = self.scope.outside(_paths(action, arguments))
        if outside:
            allowed = "; ".join(str(root) for root in self.scope.roots)
            text = f"{', '.join(outside)} is outside the folders I may use"
            self._report(reply, Step(StepKind.REFUSED, action_id, text))
            return (
                f"Error: {text} ({allowed}). Ask the user to name that folder "
                "in their request."
            )
        if self.dry_run:
            self._report(
                reply, Step(StepKind.PLANNED, action_id, f"Would run {call.describe()}")
            )
            return "Dry run: checked, not run. Carry on as if it worked."
        if action.danger in CONFIRM_DANGERS and not self.confirm(call):
            self._report(
                reply, Step(StepKind.DECLINED, action_id, f"Skipped {call.describe()}")
            )
            return DECLINED_NOTE

        try:
            result = run_action(action, given)
        except MaxError as e:
            self._report(reply, Step(StepKind.FAILED, action_id, f"{label}: {e}"))
            return f"Error: {e}"
        except Exception as e:  # noqa: BLE001 - the model hears about any failure
            logger.warning("Agent action %s failed", action_id, exc_info=True)
            self._report(reply, Step(StepKind.FAILED, action_id, f"{label}: {e}"))
            return f"Error: {e}"
        kind = StepKind.RAN if result.ok else StepKind.FAILED
        self._report(reply, Step(kind, action_id, f"{label}: {result.message}", result))
        return json.dumps(result.to_dict(), ensure_ascii=False, default=str)[
            :MAX_RESULT_CHARS
        ]

    def _report(self, reply: AgentReply, step: Step) -> None:
        reply.steps.append(step)
        self.on_step(step)


def _assistant_message(content: Optional[str], tool_calls: list[Any]) -> dict[str, Any]:
    """The model's tool-call turn, as the API expects it back."""
    return {
        "role": "assistant",
        "content": content or "",
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
            }
            for call in tool_calls
        ],
    }


def _paths(action: Action, arguments: Mapping[str, Any]) -> list[Any]:
    """Every path an action's arguments name."""
    paths: list[Any] = []
    for param in action.params:
        value = arguments.get(param.name)
        if param.kind not in PATH_KINDS or value in (None, ""):
            continue
        paths.extend(value if isinstance(value, (list, tuple)) else [value])
    return paths


def _download_folder() -> Path:
    """Max's own download folder: `grab download` saves there by default."""
    from max_cli.config import settings

    return Path(settings.GRAB_DEFAULT_PATH).expanduser()
