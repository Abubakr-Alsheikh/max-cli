"""The agent loop: ask the model, run the tools it calls, repeat until it answers.

Rules from PLANS/active/dashboard-first-ai-agent.md (D4, step 4):
- It works only through catalog actions; there is no shell tool.
- Every path argument must sit under the allowed folders (`scope`).
- Actions that move, overwrite or delete files need `confirm` to say yes,
  whatever CONFIRM_DESTRUCTIVE says.
- A request stops after MAX_STEPS model turns, MAX_ACTIONS tool calls or
  TOKEN_LIMIT tokens.
- `dry_run` checks and reports each action without running it.
- The actions the model asks for in one turn run at the same time (up to
  PARALLEL_ACTIONS), unless their paths overlap.
"""

import json
import logging
import threading
import time
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional, Union

from max_cli.common.exceptions import AIError, ConfigurationError, MaxError
from max_cli.core.agent import looks
from max_cli.core.agent.scope import PathScope
from max_cli.core.agent.tools import (
    INSPECT,
    LIST_FOLDER,
    LOAD_GROUP,
    LOOK_TOOLS,
    PROBE_LINK,
    RECENT_ACTIVITY,
    RUN_ACTION,
    TOOL_NAMES,
    agent_groups,
    group_actions,
    group_lines,
    tool_definitions,
)
from max_cli.core.catalog import get_action
from max_cli.core.catalog.spec import PATH_KINDS, Action, Danger, ParamKind, Surface
from max_cli.core.operations.result import ActionResult

logger = logging.getLogger(__name__)

CONFIRM_DANGERS = frozenset({Danger.MOVES, Danger.OVERWRITES, Danger.DELETES})
MAX_STEPS = 12  # model turns per request
MAX_ACTIONS = 40  # tool calls per request
PARALLEL_ACTIONS = 4  # actions from one turn that run at the same time
TOKEN_LIMIT = 60_000  # tokens per request, prompts and answers together
MAX_RESULT_CHARS = 4_000  # of an action's result sent back to the model
DECLINED_NOTE = (
    "The user said no, so it didn't run. Don't run it again unless they ask."
)
NOT_RUN_NOTE = "Not run: the action limit for this request was reached."
CLASH_NOTE = (
    "Not run: its result would have the same name as another file's. "
    "Run it on its own with an output name."
)
MAX_EACH = 100  # files one run_action call may list in `each`
MAX_LISTED_OUTPUTS = 20  # output files named in a batch's summary

SYSTEM_PROMPT = """You are Max, an assistant that does file and media work on \
the user's computer by running Max's actions. You can only act through the \
tools; you never run shell commands.

Command groups, with their actions:
{groups}

How to work:
- Look before you act or advise, with the read-only tools (list_folder, inspect, find_files, probe_link, recent_activity). Base suggestions on what you saw.{queue_rule}
- The user is in {cwd}. "Here", "this folder" and relative paths mean that \
folder; don't ask which folder unless the request names another one.
- Call load_group(name) to see a group's actions and their arguments, then \
run_action(action, arguments). Never invent an action or an argument.
- You may use files under that folder and any folder the user names. If you \
need a folder outside them, ask the user to name it.
- Act; don't ask for permission. Max itself asks the user before an action \
moves, overwrites or deletes files. If they say no, don't retry.
- Plan first: work out which files the request needs. Skip files that already have the result (find_files with missing "mp3" lists the .m4a files without an .mp3) and say which you skipped. Never redo finished work unless asked.
- One action on several files: one run_action with the files, a folder or a pattern in `each`; Max runs them together, asks once, skips finished ones.
- When you're done, say in one or two short sentences what you did and where the results are.
- If no action fits, say so and suggest what Max can do instead."""


QUEUE_RULE = """
- Long jobs (video and audio work, OCR, downloads) can run in the \
background: run_action with queue true. Say they're queued and that {jobs} \
shows them."""
JOBS_WINDOW = "the Jobs window (J)"  # where the dashboard shows queued jobs
# The find_files arguments besides `path`.
FIND_FILTERS = (
    "kind",
    "name",
    "min_size_mb",
    "max_size_mb",
    "newer_than_days",
    "older_than_days",
    "sort",
    "missing",
)


class StepKind(str, Enum):
    LOADED = "loaded"  # read a group's actions
    LOOKED = "looked"  # listed a folder or inspected a file
    STARTED = "started"  # an action is running now; RAN or FAILED follows
    RAN = "ran"  # ran an action and it worked
    FAILED = "failed"  # ran an action and it failed, or its arguments were wrong
    REFUSED = "refused"  # a path outside the allowed folders
    DECLINED = "declined"  # the user said no
    PLANNED = "planned"  # dry run: checked, not run
    QUEUED = "queued"  # added to the queue; the dashboard runs it in the background


@dataclass(frozen=True)
class ActionCall:
    """An action the model wants to run, with its checked arguments."""

    action: Action
    arguments: dict[str, Any]

    def shown_arguments(self) -> dict[str, str]:
        """The arguments worth showing: set, and not off or empty."""
        return _shown(self.arguments)

    def describe(self) -> str:
        """`files shred  target=C:\\notes.txt`, for a confirmation question."""
        shown = "  ".join(
            f"{name}={value}" for name, value in self.shown_arguments().items()
        )
        return f"{self.action.group} {self.action.name}  {shown}".rstrip()


@dataclass(frozen=True)
class Step:
    """One thing the agent did, for the CLI and the dashboard to show.

    An action reports STARTED with its arguments, then RAN or FAILED with
    the same action id, its result and how long it took.
    """

    kind: StepKind
    action_id: str
    text: str
    result: Optional[ActionResult] = None
    arguments: dict[str, str] = field(default_factory=dict)
    seconds: float = 0.0
    # The model's tool call id: actions run side by side, so their RAN and
    # FAILED steps can come in any order.
    call_id: str = ""

    @property
    def label(self) -> str:
        """`files preview` for "files.preview"."""
        return self.action_id.replace(".", " ")


@dataclass
class AgentReply:
    text: str
    steps: list[Step] = field(default_factory=list)
    tokens: int = 0
    model: str = ""  # the model that answered
    fallback: bool = False  # the main provider failed and the fallback answered

    def facts(self) -> str:
        """`2 actions · 3,248 tokens · gemini-2.5-flash (fallback)`."""
        actions = sum(
            1
            for step in self.steps
            if step.kind in (StepKind.RAN, StepKind.FAILED, StepKind.QUEUED)
        )
        parts = []
        if actions:
            parts.append(f"{actions} action{'s' if actions != 1 else ''}")
        if self.tokens:
            parts.append(f"{self.tokens:,} tokens")
        if self.model:
            parts.append(f"{self.model} (fallback)" if self.fallback else self.model)
        return " · ".join(parts)


@dataclass(frozen=True)
class _Run:
    """An action that passed its checks and the user's yes, waiting to run."""

    call: ActionCall
    given: dict[str, Any]  # the model's arguments, for run_action
    call_id: str
    paths: tuple[Path, ...]  # what it reads or writes, resolved

    @property
    def action_id(self) -> str:
        return self.call.action.id

    @property
    def label(self) -> str:
        return f"{self.call.action.group} {self.call.action.name}"


@dataclass(frozen=True)
class _Outcome:
    """How a run went: the text for the model, and the result behind it."""

    text: str
    ok: bool
    result: Optional[ActionResult] = None


@dataclass(frozen=True)
class _Batch:
    """One run_action call with `each`: a run per file, plus the files that
    failed their checks before anything ran."""

    label: str
    runs: tuple[_Run, ...]
    refused: tuple[tuple[str, str], ...]  # (file, why)
    done_already: tuple[str, ...] = ()  # found, but their result exists

    def summary(self, outcomes: list[_Outcome]) -> str:
        """What the model hears: counts, failures and the files made."""
        failed = [{"file": name, "error": why} for name, why in self.refused]
        outputs: list[str] = []
        for run, outcome in zip(self.runs, outcomes):
            if not outcome.ok:
                why = outcome.result.message if outcome.result else outcome.text
                name = run.paths[0].name if run.paths else run.label
                failed.append({"file": name, "error": why})
            elif outcome.result is not None:
                outputs += [str(path) for path in outcome.result.output_files]
        return json.dumps(
            {
                "action": self.label,
                "files": len(self.runs) + len(self.refused),
                "worked": sum(outcome.ok for outcome in outcomes),
                "failed": failed,
                "outputs": outputs[:MAX_LISTED_OUTPUTS],
                "more_outputs": max(0, len(outputs) - MAX_LISTED_OUTPUTS),
                **_done_already(self.done_already),
            },
            ensure_ascii=False,
        )[:MAX_RESULT_CHARS]


def _lists_files(item: str) -> bool:
    """A folder or a pattern: reading it lists the files in it."""
    from max_cli.core.catalog.batch import WILDCARDS

    path = Path(item).expanduser()
    return path.is_dir() or bool(WILDCARDS & set(path.name))


def _done_already(names: tuple[str, ...]) -> dict[str, Any]:
    """The skipped files, with what to tell the user, when there are any."""
    if not names:
        return {}
    return {
        "done_already": list(names[:MAX_LISTED_OUTPUTS]),
        "done_already_count": len(names),
        "note": "These had their result already, so they didn't run. Tell the "
        "user you skipped them.",
    }


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
        max_actions: int = MAX_ACTIONS,
        parallel: int = PARALLEL_ACTIONS,
        token_limit: int = TOKEN_LIMIT,
        can_queue: bool = False,
        jobs_hint: str = JOBS_WINDOW,
    ) -> None:
        """`can_queue` lets the model queue long jobs, which the caller must
        then run: the dashboard's worker, or the background worker the CLI
        starts. `jobs_hint` names where the user follows them. `on_step`
        may be called from several threads at once, never two calls at the
        same time."""
        self.client = client
        self.can_queue = can_queue
        self.jobs_hint = jobs_hint
        self.model = model
        self.confirm = confirm
        self.on_step = on_step or _ignore_step
        self.dry_run = dry_run
        self.max_steps = max_steps
        self.max_actions = max_actions
        self.parallel = max(1, parallel)
        self.token_limit = token_limit
        self._report_lock = threading.Lock()
        self.scope = PathScope(cwd or Path.cwd())
        self.scope.allow(_download_folder())
        self.loaded: set[str] = set()
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt()}
        ]

    @classmethod
    def from_settings(cls, **kwargs: Any) -> "Agent":
        """An agent on the configured provider (settings: AI and Ollama)."""
        from max_cli.core.engines.ai_providers import (
            chat_model,
            main_provider,
            make_client,
        )

        client = make_client()
        if client is None:
            main = main_provider()
            raise ConfigurationError(
                f"The AI isn't set up: {main.label} has {main.missing()}. Fix it "
                "on the dashboard's Settings page (,) or with max config setup."
            )
        return cls(client, chat_model(), **kwargs)

    def system_prompt(self) -> str:
        """The first prompt: the group list only, never the actions."""
        return SYSTEM_PROMPT.format(
            groups=group_lines(),
            cwd=self.scope.cwd,
            queue_rule=QUEUE_RULE.format(jobs=self.jobs_hint) if self.can_queue else "",
        )

    # --- the loop -----------------------------------------------------------

    def ask(self, request: str) -> AgentReply:
        """Work on one request until the model answers in words.

        The request goes into the activity log (with each action it runs),
        whether it came from the CLI or the dashboard, so recent_activity
        and Activity's History show it.
        """
        from max_cli.common.activity_log import ActivityLog

        # One entry when it ends: an entry opened at the start and saved at
        # the end would write its stale copy of the log over the actions
        # logged in between.
        started = time.monotonic()
        try:
            reply = self._ask(request)
        except MaxError as e:
            ActivityLog().add_entry(
                "ai", "agent", "failed", {"prompt": request, "error": str(e)}
            )
            raise
        ActivityLog().add_entry(
            "ai",
            "agent",
            "success",
            {"prompt": request, "message": reply.text, "tokens": reply.tokens},
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return reply

    def _ask(self, request: str) -> AgentReply:
        self.scope.add_from(request)
        self.messages.append({"role": "user", "content": request})
        reply = AgentReply("")
        turns = calls = 0
        while True:
            response = self._complete()
            turns += 1
            usage = getattr(response, "usage", None)
            reply.tokens += int(getattr(usage, "total_tokens", 0) or 0)
            message = response.choices[0].message
            tool_calls = list(message.tool_calls or [])
            reply.model = str(getattr(self.client, "model", self.model))
            reply.fallback = bool(getattr(self.client, "used_fallback", False))
            if not tool_calls:
                reply.text = (message.content or "").strip() or "Done."
                self.messages.append({"role": "assistant", "content": reply.text})
                return reply
            self.messages.append(_assistant_message(message.content, tool_calls))
            answers = self._tools(tool_calls, reply, calls)
            calls += len(tool_calls)
            for tool_call, content in zip(tool_calls, answers):
                self.messages.append(
                    {"role": "tool", "tool_call_id": tool_call.id, "content": content}
                )
            limit = self._limit_reached(turns, calls, reply.tokens)
            if limit:
                reply.text = limit
                self.messages.append({"role": "assistant", "content": limit})
                return reply

    def _tools(self, tool_calls: list[Any], reply: AgentReply, done: int) -> list[str]:
        """An answer per tool call, in their order. Looks, checks and
        confirmations go one at a time; the actions that pass them then run
        together. `done` counts the tool calls of earlier turns."""
        answers: list[str] = []
        waiting: list[tuple[int, Union[_Run, _Batch]]] = []
        for index, tool_call in enumerate(tool_calls):
            if done + index >= self.max_actions:
                answers.append(NOT_RUN_NOTE)
                continue
            answer = self._tool(
                tool_call.function.name,
                tool_call.function.arguments,
                reply,
                call_id=str(tool_call.id),
            )
            if not isinstance(answer, str):
                waiting.append((index, answer))
                answer = ""  # filled in once it has run
            answers.append(answer)
        runs = [
            run
            for _, job in waiting
            for run in (job.runs if isinstance(job, _Batch) else (job,))
        ]
        outcomes = iter(self._run_all(runs, reply))
        for index, job in waiting:
            if isinstance(job, _Batch):
                answers[index] = job.summary([next(outcomes) for _ in job.runs])
            else:
                answers[index] = next(outcomes).text
        return answers

    def _run_all(self, runs: list[_Run], reply: AgentReply) -> list[_Outcome]:
        """Side by side when no two touch the same path, else in order."""
        if len(runs) < 2 or self.parallel < 2 or _overlap(runs):
            return [self._execute(run, reply) for run in runs]
        with ThreadPoolExecutor(max_workers=min(self.parallel, len(runs))) as pool:
            futures = [pool.submit(self._execute, run, reply) for run in runs]
            return [future.result() for future in futures]

    def _limit_reached(self, turns: int, calls: int, tokens: int) -> str:
        if turns >= self.max_steps:
            return (
                f"I stopped after {self.max_steps} steps, the limit for one "
                "request. Ask me to go on if there's more to do."
            )
        if calls >= self.max_actions:
            return (
                f"I stopped after {self.max_actions} actions, the limit for one "
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
                model=self.model,
                messages=self.messages,
                tools=tool_definitions(self.can_queue),
            )
        except BadRequestError as e:
            if "tool" in str(e).lower():
                model = getattr(self.client, "model", self.model)
                raise AIError(
                    f"The model {model} can't call tools, so the agent can't "
                    "use it. Pick one that can (most OpenAI, Gemini, Claude and "
                    "Llama 3.1+ models do)."
                ) from e
            raise AIError(f"The AI refused the request: {e}") from e
        except APIError as e:
            raise AIError(f"The AI didn't answer: {e}") from e

    # --- tools --------------------------------------------------------------

    def _tool(
        self, name: str, raw_arguments: str, reply: AgentReply, call_id: str = ""
    ) -> Union[str, _Run, _Batch]:
        """The tool's answer, or the actions that are ready to run."""
        try:
            arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError:
            return "Error: the arguments aren't valid JSON."
        if not isinstance(arguments, dict):
            return "Error: the arguments must be a JSON object."
        if name == LOAD_GROUP:
            return self._load_group(str(arguments.get("name", "")), reply)
        if name in LOOK_TOOLS:
            return self._look(name, arguments, reply)
        if name == RUN_ACTION:
            given = arguments.get("arguments") or {}
            if not isinstance(given, Mapping):
                return "Error: 'arguments' must be an object."
            queue = arguments.get("queue") is True
            each = arguments.get("each")
            if each is None and _names_many(str(arguments.get("action", "")), given):
                each = []  # the file argument holds the folder or pattern
            if each is not None:
                if not isinstance(each, list):
                    return "Error: 'each' must be a list of file paths."
                return self._run_each(
                    str(arguments.get("action", "")),
                    dict(given),
                    [str(path) for path in each],
                    reply,
                    queue=queue,
                    call_id=call_id,
                )
            return self._run(
                str(arguments.get("action", "")),
                dict(given),
                reply,
                queue=queue,
                call_id=call_id,
            )
        return f"Error: there is no tool '{name}'. Tools: {', '.join(TOOL_NAMES)}."

    def _look(self, tool: str, arguments: dict[str, Any], reply: AgentReply) -> str:
        """A read-only tool. Paths stay inside the allowed folders."""
        try:
            if tool == PROBE_LINK:
                url = str(arguments.get("url", "")).strip()
                found, what = looks.probe_link(url), f"Checked {url}"
            elif tool == RECENT_ACTIVITY:
                found = looks.recent_activity(int(arguments.get("limit") or 10))
                what = "Read the recent activity"
            else:
                path = self.scope.resolve(str(arguments.get("path") or "."))
                if not self.scope.allows(path):
                    allowed = "; ".join(str(root) for root in self.scope.roots)
                    text = f"{path} is outside the folders I may use"
                    self._report(reply, Step(StepKind.REFUSED, tool, text))
                    return f"Error: {text} ({allowed}). Ask the user to name it."
                found, what = self._look_at(tool, path, arguments)
        except MaxError as e:
            return f"Error: {e}"
        except (OSError, ValueError, TypeError) as e:
            return f"Error: {e}"
        self._report(reply, Step(StepKind.LOOKED, tool, what))
        return found

    @staticmethod
    def _look_at(tool: str, path: Path, arguments: dict[str, Any]) -> tuple[str, str]:
        name = path.name or str(path)
        if tool == LIST_FOLDER:
            return looks.list_folder(path), f"Listed {name}"
        if tool == INSPECT:
            return looks.inspect(path), f"Inspected {name}"
        filters = {
            key: arguments[key]
            for key in FIND_FILTERS
            if arguments.get(key) not in (None, "")
        }
        return looks.find_files(path, **filters), f"Searched {name}"

    def _load_group(self, name: str, reply: AgentReply) -> str:
        if name not in agent_groups():
            return f"Error: no group '{name}'. Groups: {', '.join(agent_groups())}."
        self.loaded.add(name)
        self._report(
            reply, Step(StepKind.LOADED, name, f"Looked up the {name} actions")
        )
        return group_actions(name)

    def _run(
        self,
        action_id: str,
        given: dict[str, Any],
        reply: AgentReply,
        queue: bool = False,
        call_id: str = "",
    ) -> Union[str, _Run]:
        """Check an action and ask the user when it changes files. Queued
        and dry-run actions end here; the rest come back as a `_Run`."""
        from max_cli.core.catalog.runner import coerce_args, enqueue_action

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
            self._report(
                reply,
                Step(
                    StepKind.FAILED,
                    action_id,
                    f"{label}: {e}",
                    arguments=_shown(given),
                    call_id=call_id,
                ),
            )
            return f"Error: {e}"

        call = ActionCall(action, arguments)
        shown = call.shown_arguments()
        paths = _paths(action, arguments)
        outside = self.scope.outside(paths)
        if outside:
            allowed = "; ".join(str(root) for root in self.scope.roots)
            text = f"{', '.join(outside)} is outside the folders I may use"
            self._report(
                reply,
                Step(
                    StepKind.REFUSED, action_id, text, arguments=shown, call_id=call_id
                ),
            )
            return (
                f"Error: {text} ({allowed}). Ask the user to name that folder "
                "in their request."
            )
        if self.dry_run:
            self._report(
                reply,
                Step(
                    StepKind.PLANNED,
                    action_id,
                    f"Would run {call.describe()}",
                    arguments=shown,
                    call_id=call_id,
                ),
            )
            return "Dry run: checked, not run. Carry on as if it worked."
        # A dry run (smart-sort --dry-run, organize --dry-run) changes
        # nothing, so it doesn't ask.
        changes_files = action.danger in CONFIRM_DANGERS and not arguments.get(
            "dry_run"
        )
        if changes_files and not self.confirm(call):
            self._report(
                reply,
                Step(
                    StepKind.DECLINED,
                    action_id,
                    f"Skipped {call.describe()}",
                    arguments=shown,
                    call_id=call_id,
                ),
            )
            return DECLINED_NOTE

        if queue and self.can_queue and action.queueable:
            try:
                task = enqueue_action(action, given)
            except MaxError as e:
                return f"Error: couldn't queue it: {e}"
            self._report(
                reply,
                Step(
                    StepKind.QUEUED,
                    action_id,
                    f"Queued {label}",
                    arguments=shown,
                    call_id=call_id,
                ),
            )
            return json.dumps(
                {
                    "queued": True,
                    "task_id": task.id,
                    "note": "It runs in the background; the user follows it "
                    f"with {self.jobs_hint}. Don't wait for it.",
                }
            )
        resolved = tuple(self.scope.resolve(str(path)) for path in paths)
        return _Run(call, given, call_id, resolved)

    def _execute(self, run: _Run, reply: AgentReply) -> _Outcome:
        """Run a checked action; its result (or error) for the model. Called
        from a worker thread when actions run side by side."""
        from max_cli.core.catalog.runner import run_action

        shown = run.call.shown_arguments()
        self._report(
            reply,
            Step(
                StepKind.STARTED,
                run.action_id,
                f"Running {run.label}",
                arguments=shown,
                call_id=run.call_id,
            ),
        )
        started = time.monotonic()
        try:
            result = run_action(run.call.action, run.given)
        except Exception as e:  # noqa: BLE001 - the model hears about any failure
            if not isinstance(e, MaxError):
                logger.warning("Agent action %s failed", run.action_id, exc_info=True)
            self._report(
                reply,
                Step(
                    StepKind.FAILED,
                    run.action_id,
                    f"{run.label}: {e}",
                    arguments=shown,
                    seconds=time.monotonic() - started,
                    call_id=run.call_id,
                ),
            )
            return _Outcome(f"Error: {e}", False)
        kind = StepKind.RAN if result.ok else StepKind.FAILED
        self._report(
            reply,
            Step(
                kind,
                run.action_id,
                f"{run.label}: {result.message}",
                result,
                arguments=shown,
                seconds=time.monotonic() - started,
                call_id=run.call_id,
            ),
        )
        text = json.dumps(result.to_dict(), ensure_ascii=False, default=str)
        return _Outcome(text[:MAX_RESULT_CHARS], result.ok, result)

    def _run_each(
        self,
        action_id: str,
        given: dict[str, Any],
        each: list[str],
        reply: AgentReply,
        queue: bool = False,
        call_id: str = "",
    ) -> Union[str, _Batch]:
        """One action over several files: each file in turn fills the action's
        file argument. Every file is checked first; then one question covers
        the files that passed, and they run together."""
        from max_cli.core.catalog.runner import coerce_args

        try:
            action = get_action(action_id)
        except KeyError:
            return f"Error: no action '{action_id}'. Call load_group to see them."
        if Surface.AGENT not in action.surfaces:
            return f"Error: {action_id} isn't available to the agent."
        if action.group not in self.loaded:
            return (
                f"Error: call load_group('{action.group}') first to see its arguments."
            )
        param = _each_param(action)
        if param is None:
            return f"Error: {action_id} takes no file, so 'each' doesn't fit it."
        done_already: list[Path] = []
        refused: list[tuple[str, str]] = []
        if action.each_param() is not None:
            # Folders and patterns become files, finished ones left out.
            from max_cli.core.catalog.batch import expand_each

            wanted = each or given.get(param.name)
            # Check folders and patterns before reading them: listing one
            # outside the scope would show the model its file names. Named
            # files get their own check below.
            asked = wanted if isinstance(wanted, list) else [wanted]
            outside = self.scope.outside(
                str(item) for item in asked if item and _lists_files(str(item))
            )
            if outside:
                return f"Error: {', '.join(outside)} is outside the folders I may use."
            try:
                found = expand_each(action, {**given, param.name: wanted})
            except MaxError as e:
                return f"Error: {e}"
            each = [str(path) for path in found.files]
            done_already = found.done_already
            refused = [(path.name, CLASH_NOTE) for path in found.clashes]
            if not each:
                return json.dumps(
                    {
                        "action": f"{action.group} {action.name}",
                        "files": 0,
                        **_done_already(tuple(path.name for path in done_already)),
                    },
                    ensure_ascii=False,
                )
        if not each:
            return "Error: 'each' must list at least one file."
        if len(each) > MAX_EACH:
            return f"Error: 'each' takes at most {MAX_EACH} files; split the list."
        label = f"{action.group} {action.name}"
        checked: list[tuple[str, ActionCall, dict[str, Any], tuple[Path, ...]]] = []
        for number, path in enumerate(each):
            file_given = {**given, param.name: [path] if param.multiple else path}
            try:
                arguments = coerce_args(action, file_given)
            except MaxError as e:
                refused.append((Path(path).name, str(e)))
                continue
            paths = _paths(action, arguments)
            outside = self.scope.outside(paths)
            if outside:
                refused.append(
                    (
                        Path(path).name,
                        f"{', '.join(outside)} is outside the folders I may use",
                    )
                )
                continue
            resolved = tuple(self.scope.resolve(str(found)) for found in paths)
            checked.append(
                (
                    f"{call_id}:{number}",
                    ActionCall(action, arguments),
                    file_given,
                    resolved,
                )
            )
        if not checked:
            return "Error: no file passed the checks: " + json.dumps(
                dict(refused), ensure_ascii=False
            )
        names = [Path(each_path).name for each_path in each]
        whole = ActionCall(
            action,
            {**checked[0][1].arguments, param.name: _files_text(names, len(checked))},
        )
        if self.dry_run:
            self._report(
                reply,
                Step(
                    StepKind.PLANNED,
                    action_id,
                    f"Would run {whole.describe()}",
                    arguments=whole.shown_arguments(),
                    call_id=call_id,
                ),
            )
            return "Dry run: checked, not run. Carry on as if it worked."
        changes_files = action.danger in CONFIRM_DANGERS and not given.get("dry_run")
        if changes_files and not self.confirm(whole):
            self._report(
                reply,
                Step(
                    StepKind.DECLINED,
                    action_id,
                    f"Skipped {whole.describe()}",
                    arguments=whole.shown_arguments(),
                    call_id=call_id,
                ),
            )
            return DECLINED_NOTE
        if queue and self.can_queue and action.queueable:
            from max_cli.core.catalog.runner import enqueue_action

            for each_id, call, file_given, _paths_found in checked:
                try:
                    enqueue_action(action, file_given)
                except MaxError as e:
                    return f"Error: couldn't queue the files: {e}"
                self._report(
                    reply,
                    Step(
                        StepKind.QUEUED,
                        action_id,
                        f"Queued {label}",
                        arguments=call.shown_arguments(),
                        call_id=each_id,
                    ),
                )
            return json.dumps(
                {
                    "queued": len(checked),
                    "failed": [{"file": n, "error": why} for n, why in refused],
                    "note": "They run in the background; the user follows "
                    f"them with {self.jobs_hint}. Don't wait for them.",
                },
                ensure_ascii=False,
            )
        runs = tuple(
            _Run(call, file_given, each_id, found)
            for each_id, call, file_given, found in checked
        )
        return _Batch(
            label, runs, tuple(refused), tuple(path.name for path in done_already)
        )

    def _report(self, reply: AgentReply, step: Step) -> None:
        # One at a time: actions running side by side report from their
        # threads, and the activity log is read, changed and saved whole.
        with self._report_lock:
            reply.steps.append(step)
            if step.kind in (StepKind.RAN, StepKind.FAILED, StepKind.QUEUED):
                _log_action(step)
            self.on_step(step)


def _assistant_message(content: Optional[str], tool_calls: list[Any]) -> dict[str, Any]:
    """The model's tool-call turn, as the API expects it back."""
    return {
        "role": "assistant",
        "content": content or "",
        "tool_calls": [_tool_call_message(call) for call in tool_calls],
    }


def _tool_call_message(call: Any) -> dict[str, Any]:
    """One tool call as sent back. Gemini adds `extra_content` (its thought
    signature) and refuses the next request without it."""
    message: dict[str, Any] = {
        "id": call.id,
        "type": "function",
        "function": {"name": call.function.name, "arguments": call.function.arguments},
    }
    extra = getattr(call, "extra_content", None)
    if isinstance(extra, Mapping):
        message["extra_content"] = dict(extra)
    return message


def _names_many(action_id: str, given: Mapping[str, Any]) -> bool:
    """True when a batch-ready action's file argument holds a list, a folder
    or a pattern rather than one file."""
    from max_cli.core.catalog.batch import is_batch

    try:
        action = get_action(action_id)
    except KeyError:
        return False
    return action.each_param() is not None and is_batch(action, given)


def _each_param(action: Action) -> Optional[Any]:
    """The argument `each` fills: the first input file, else the first folder."""
    for kind in (ParamKind.FILE, ParamKind.FOLDER):
        for param in action.params:
            if param.kind == kind:
                return param
    return None


def _files_text(names: list[str], count: int) -> str:
    """`11 files (a.m4a, b.m4a, c.m4a ...)` for the one question a batch asks."""
    shown = ", ".join(names[:3]) + (" ..." if len(names) > 3 else "")
    return f"{count} file{'s' if count != 1 else ''} ({shown})"


def _overlap(runs: list[_Run]) -> bool:
    """True when two actions name the same path, or one names a folder the
    other's path sits in: those run one after the other, in order."""
    for index, run in enumerate(runs):
        for other in runs[index + 1 :]:
            for path in run.paths:
                for other_path in other.paths:
                    if (
                        path == other_path
                        or path in other_path.parents
                        or other_path in path.parents
                    ):
                        return True
    return False


def _log_action(step: Step) -> None:
    """An action the agent ran, queued or failed, in the activity log."""
    from max_cli.common.activity_log import ActivityLog

    group, _, name = step.action_id.partition(".")
    if not name:
        return  # a look or lookup, not an action
    details: dict[str, Any] = {"args": step.arguments, "via": "ai"}
    if step.result is not None:
        details.update(step.result.to_dict())
    elif step.kind == StepKind.FAILED:
        details["error"] = step.text
    status = {StepKind.RAN: "success", StepKind.QUEUED: "queued"}.get(
        step.kind, "failed"
    )
    ActivityLog().add_entry(
        group, name, status, details, duration_ms=int(step.seconds * 1000)
    )


def _shown(arguments: Mapping[str, Any]) -> dict[str, str]:
    """Arguments as text, without the unset, off and empty ones."""
    return {
        name: ", ".join(str(item) for item in value)
        if isinstance(value, (list, tuple))
        else str(value)
        for name, value in arguments.items()
        if value not in (None, "", False, [])
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
