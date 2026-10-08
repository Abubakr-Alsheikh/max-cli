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
- A batch (`each`, narrowed with `select`) asks once, with the file count and
  size; over AUTO_QUEUE_FILES files a queueable action goes to the queue.
- Every result is checked: an output file that is missing or empty turns
  the run into a failure the model hears about.
- `remember` and `forget` keep notes across sessions (`memory.py`); the
  system prompt lists them.
- `plan` shows the steps and waits for the `ask` callback's go-ahead;
  `ask_user` asks a question through the same callback.
- Each request carries a few lines of context (`context.py`), and past
  COMPACT_AT_CHARS the oldest turns become one summary.
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
from max_cli.core.agent.memory import AgentMemory
from max_cli.core.agent.scope import PathScope
from max_cli.core.agent.tools import (
    FORGET,
    INSPECT,
    JOB_STATUS,
    LIST_FOLDER,
    LOAD_GROUP,
    LOOK_AT_IMAGE,
    LOOK_TOOLS,
    OPEN,
    PLAN,
    PROBE_LINK,
    PROCESSES,
    QUESTION_TOOLS,
    RECENT_ACTIVITY,
    REMEMBER,
    RUN_ACTION,
    RUN_COMMAND,
    SELECT_FIELDS,
    STOP_PROCESS,
    SYSTEM_INFO,
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
# Tokens per request, prompts and answers together. Each turn resends the
# conversation, so a request with two loaded groups used 60,000 in a few turns.
TOKEN_LIMIT = 100_000
MAX_RESULT_CHARS = 4_000  # of an action's result sent back to the model
DECLINED_NOTE = (
    "The user said no, so it didn't run. Don't run it again unless they ask."
)
ASKED_BEFORE_NOTE = (
    "The user already said no to {label} in this request, so Max didn't ask "
    "again. Use another action or ask what they want."
)
NOT_RUN_NOTE = "Not run: the action limit for this request was reached."
CLASH_NOTE = (
    "Not run: its result would have the same name as another file's. "
    "Run it on its own with an output name."
)
MAX_EACH = 500  # files one run_action call may run
# A batch of a queueable action with more files than this goes to the queue
# when the agent can queue: it would hold the conversation for a long time.
AUTO_QUEUE_FILES = 20
MAX_LISTED_OUTPUTS = 20  # output files named in a batch's summary
SIZE_SHOWN_FROM = 1024 * 1024  # a batch's question names its size from 1 MB
DRY_RUN_NOTE = (
    "Dry run: nothing ran and nothing changed, as asked. Don't call it again; "
    "tell the user what would happen."
)
DRY_RUN_CONTEXT = (
    "(Dry run: Max checks each action and runs nothing. Ask for each step "
    "once, then say what would happen.)"
)
REPEAT_NOTE = (
    "Already done in this request with these exact arguments: its answer is "
    "above. Don't repeat it."
)
# select's filters; recursive and redo go to expand_each.
MAX_PLAN_STEPS = 12
MAX_IMAGE_MB = 20  # look_at_image sends the whole file to the vision model
BYTES_PER_MB = 1024 * 1024
MAX_OPTIONS = 6
# Answers to a plan that mean "go ahead"; anything else is a change to make.
GO_ANSWERS = frozenset({"go", "go ahead", "yes", "y", "ok", "okay", "sure"})
NO_ANSWER_NOTE = (
    "The user can't answer here. Choose the safest option, carry on, and say "
    "what you assumed."
)
# Past this many characters of conversation (about 12,000 tokens) the oldest
# turns become one summary; the last KEEP_RECENT_REQUESTS stay as they were.
COMPACT_AT_CHARS = 48_000
KEEP_RECENT_REQUESTS = 2
MAX_SUMMARY_SOURCE_CHARS = 30_000
MAX_TRANSCRIPT_TOOL_CHARS = 300
SUMMARY_PROMPT = (
    "Summarize this conversation between a user and Max, an assistant that "
    "works on the user's files, so Max can continue it: the requests, what "
    "Max did (actions, folders, files made), decisions, preferences and "
    "anything unfinished. Plain text, at most 200 words."
)
SUMMARY_INTRO = "Summary of our earlier conversation:"
SELECT_FILTERS = tuple(
    name for name in SELECT_FIELDS if name not in ("recursive", "redo")
)

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
- Many files: ONE run_action with a folder, pattern or files in `each` (narrowed with `select`), never a call per file. Max asks once, skips finished files and queues big batches.
- Results come back checked: report failed, missing or empty outputs; never claim it all worked.
- "Undo that": the files group's undo action. job_status shows queued jobs.
- Save lasting facts and preferences the user gives (where files live, quality) with remember; use your notes below.
- The computer: system_info and processes; stop_process ends a program the user wants closed (Max asks them). open shows the user a file, folder or link they asked to see; never programs. look_at_image when you must see what a picture shows.
- Work with 3+ steps or many files: call plan first and follow the answer. If the request is unclear and a wrong guess would cost, ask_user; otherwise decide yourself. A worded answer is the user's instruction: follow it.
- When done, say in one or two short sentences what you did and where the results are.
- If no action fits, say so and suggest what Max can do instead.

Your notes from earlier sessions:
{memory}"""


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
    NOTED = "noted"  # saved or deleted a memory note, or summarised the chat
    PLAN = "plan"  # showed the plan; text holds the numbered steps
    OPENED = "opened"  # opened a file, folder or link for the user
    STOPPED = "stopped"  # ended a program the user agreed to stop
    COMMAND = "command"  # ran a command (AGENT_SHELL); text holds its output's end
    ASKED = "asked"  # asked the user a question or for a go-ahead


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
    problem: str = ""  # what the check after the run found wrong


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
                why = outcome.problem or (
                    outcome.result.message if outcome.result else outcome.text
                )
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


class QuestionKind(str, Enum):
    QUESTION = "question"  # ask_user: answer in words or pick an option
    PLAN = "plan"  # plan: "go", None to stop, or the changes to make
    CONFIRM = "confirm"  # yes or no: "yes", or None


@dataclass(frozen=True)
class Question:
    """What the agent asks the user. `text` is the question, or the plan's
    numbered steps."""

    kind: QuestionKind
    text: str
    options: tuple[str, ...] = ()


Confirm = Callable[[ActionCall], bool]
OnStep = Callable[[Step], None]
# The user's answer, or None when they gave none (closed it, cancelled).
Ask = Callable[[Question], Optional[str]]


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
        memory: Optional[AgentMemory] = None,
        ask: Optional[Ask] = None,
        context: bool = True,
        shell: Optional[bool] = None,
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
        self.memory = memory or AgentMemory()
        # Per request (_ask resets them): the kinds of file-changing actions
        # run, whether a plan was shown, the run_action calls asked (as JSON).
        self._changing_actions: set[str] = set()
        self._plan_shown = False
        self._actions_asked: set[str] = set()
        self._declined: set[str] = set()  # action ids the user said no to
        self.ask_user = ask
        self.context = context
        if shell is None:
            from max_cli.config import settings

            shell = settings.AGENT_SHELL
        self.shell = shell
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
            memory=self.memory.prompt_lines() or "(none yet)",
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
        # The kinds of file-changing actions this request ran, and whether it
        # showed a plan: a second kind without a plan asks for one first.
        self._changing_actions = set()
        self._plan_shown = False
        self._actions_asked = set()
        self._declined = set()
        reply = AgentReply("")
        self._compact(reply)
        self.messages.append({"role": "user", "content": self._with_context(request)})
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

    def _with_context(self, request: str) -> str:
        parts = [request]
        if self.context:
            from max_cli.core.agent.context import request_context

            parts.append(request_context(self.scope.cwd))
        if self.dry_run:
            parts.append(DRY_RUN_CONTEXT)
        return "\n\n".join(part for part in parts if part)

    def _compact(self, reply: AgentReply) -> None:
        """Turn the oldest turns into one summary when the conversation is
        long. Keeps everything as it was when the summary call fails."""
        from openai import APIError

        size = len(json.dumps(self.messages[1:], default=str))
        requests = [
            index
            for index, message in enumerate(self.messages)
            if index and message.get("role") == "user"
        ]
        if size < COMPACT_AT_CHARS or len(requests) <= KEEP_RECENT_REQUESTS:
            return
        cut = requests[-KEEP_RECENT_REQUESTS]
        transcript = _transcript(self.messages[1:cut])[-MAX_SUMMARY_SOURCE_CHARS:]
        from max_cli.config import settings

        try:
            response = self.client.chat.completions.create(
                # A cheaper model is enough for a summary (AI_FAST_MODEL).
                model=settings.AI_FAST_MODEL.strip() or self.model,
                messages=[
                    {"role": "system", "content": SUMMARY_PROMPT},
                    {"role": "user", "content": transcript},
                ],
            )
        except APIError:
            logger.warning("Couldn't summarise the conversation", exc_info=True)
            return
        summary = (response.choices[0].message.content or "").strip()
        if not summary:
            return
        usage = getattr(response, "usage", None)
        reply.tokens += int(getattr(usage, "total_tokens", 0) or 0)
        self.messages[1:cut] = [
            {"role": "user", "content": f"{SUMMARY_INTRO} {summary}"},
            {"role": "assistant", "content": "Noted."},
        ]
        self._report(
            reply,
            Step(StepKind.NOTED, "summary", "Summarised the earlier conversation"),
        )

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
                tools=tool_definitions(self.can_queue, self.shell),
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
        if name in (REMEMBER, FORGET):
            return self._note(name, arguments, reply)
        if name in QUESTION_TOOLS:
            return self._question(name, arguments, reply)
        if name == OPEN:
            return self._open(str(arguments.get("target", "")), reply)
        if name == STOP_PROCESS:
            return self._stop_process(arguments, reply)
        if name == RUN_COMMAND and self.shell:
            return self._run_command(arguments, reply)
        if name == RUN_ACTION:
            asked = json.dumps(arguments, sort_keys=True, default=str)
            if asked in self._actions_asked:
                return REPEAT_NOTE
            self._actions_asked.add(asked)
            given = arguments.get("arguments") or {}
            if not isinstance(given, Mapping):
                return "Error: 'arguments' must be an object."
            queue = arguments.get("queue") is True
            each = arguments.get("each")
            select = arguments.get("select") or {}
            if not isinstance(select, Mapping):
                return "Error: 'select' must be an object."
            if each is None and (
                select or _names_many(str(arguments.get("action", "")), given)
            ):
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
                    select=dict(select),
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
            elif tool == JOB_STATUS:
                found = looks.job_status(int(arguments.get("limit") or 10))
                what = "Checked the queued jobs"
            elif tool == SYSTEM_INFO:
                from max_cli.core.agent import pc

                found, what = pc.system_info(), "Checked this computer"
            elif tool == PROCESSES:
                from max_cli.core.agent import pc

                name = str(arguments.get("name") or "")
                found = pc.processes(name)
                what = f"Listed running programs{f' named {name}' if name else ''}"
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
        if tool == LOOK_AT_IMAGE:
            return _look_at_image(path, str(arguments.get("question") or "")), (
                f"Looked at {name}"
            )
        filters = {
            key: arguments[key]
            for key in FIND_FILTERS
            if arguments.get(key) not in (None, "")
        }
        return looks.find_files(path, **filters), f"Searched {name}"

    def _open(self, target: str, reply: AgentReply) -> str:
        """Open a link, or a file or folder inside the allowed folders."""
        from max_cli.core.agent import pc

        target = target.strip()
        if not target:
            return "Error: 'target' is empty."
        if not pc.is_web_link(target):
            path = self.scope.resolve(target)
            if not self.scope.allows(path):
                text = f"{path} is outside the folders I may use"
                self._report(reply, Step(StepKind.REFUSED, OPEN, text))
                return f"Error: {text}. Ask the user to name it."
            target = str(path)
        if self.dry_run:
            return f"Dry run: would open {target}. {DRY_RUN_NOTE}"
        try:
            pc.open_target(target)
        except MaxError as e:
            return f"Error: {e}"
        except OSError as e:
            return f"Error: couldn't open it: {e}"
        shown = Path(target).name if not pc.is_web_link(target) else target
        self._report(reply, Step(StepKind.OPENED, OPEN, f"Opened {shown}"))
        return json.dumps({"opened": target}, ensure_ascii=False)

    def _yes(self, question: str) -> bool:
        """The user's yes to `question`. No way to ask counts as no."""
        if self.ask_user is None:
            return False
        return self.ask_user(Question(QuestionKind.CONFIRM, question)) == "yes"

    def _stop_process(self, arguments: dict[str, Any], reply: AgentReply) -> str:
        from max_cli.core.agent import pc

        try:
            process = pc.find_process(
                int(arguments.get("pid") or 0), str(arguments.get("name") or "")
            )
        except (MaxError, ValueError) as e:
            return f"Error: {e}"
        described = pc.describe_process(process)
        if self.dry_run:
            return f"Dry run: would stop {described}. {DRY_RUN_NOTE}"
        if not self._yes(f"Max wants to stop {described}. Unsaved work in it is lost."):
            self._report(
                reply,
                Step(StepKind.DECLINED, STOP_PROCESS, f"Kept {described} running"),
            )
            return DECLINED_NOTE
        try:
            outcome = pc.stop_process(process)
        except MaxError as e:
            return f"Error: {e}"
        self._report(reply, Step(StepKind.STOPPED, STOP_PROCESS, outcome))
        return json.dumps({"result": outcome}, ensure_ascii=False)

    def _run_command(self, arguments: dict[str, Any], reply: AgentReply) -> str:
        """A program with its arguments, after the user's yes (AGENT_SHELL)."""
        from max_cli.common.activity_log import ActivityLog
        from max_cli.core.agent import pc

        command = str(arguments.get("command", "")).strip()
        folder = self.scope.resolve(str(arguments.get("folder") or "."))
        if not self.scope.allows(folder) or not folder.is_dir():
            return f"Error: {folder} isn't a folder I may use."
        try:
            words = pc.command_words(command)
        except MaxError as e:
            return f"Error: {e}"
        if self.dry_run:
            return f"Dry run: would run `{command}` in {folder}. {DRY_RUN_NOTE}"
        if not self._yes(f"Max wants to run this command in {folder}:\n\n  {command}"):
            self._report(
                reply, Step(StepKind.DECLINED, RUN_COMMAND, f"Didn't run {command}")
            )
            return DECLINED_NOTE
        started = time.monotonic()
        try:
            output = pc.run_command(words, folder)
        except MaxError as e:
            self._report(reply, Step(StepKind.FAILED, RUN_COMMAND, f"{command}: {e}"))
            return f"Error: {e}"
        result = json.loads(output)
        self._report(
            reply,
            Step(
                StepKind.COMMAND,
                RUN_COMMAND,
                f"Ran {command} (exit code {result['exit_code']})",
                arguments={"command": command, "folder": str(folder)},
                seconds=time.monotonic() - started,
            ),
        )
        ActivityLog().add_entry(
            "ai",
            "command",
            "success" if result["exit_code"] == 0 else "failed",
            {
                "command": command,
                "folder": str(folder),
                "exit_code": result["exit_code"],
            },
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return output

    def _note(self, tool: str, arguments: dict[str, Any], reply: AgentReply) -> str:
        """remember or forget: the memory notes later sessions start with."""
        if tool == REMEMBER:
            try:
                note = self.memory.remember(str(arguments.get("text", "")))
            except MaxError as e:
                return f"Error: {e}"
            self._report(reply, Step(StepKind.NOTED, tool, f"Remembered: {note.text}"))
            return json.dumps({"saved": note.id, "text": note.text}, ensure_ascii=False)
        gone = self.memory.forget(str(arguments.get("id", "")))
        if gone is None:
            return (
                "Error: no note with that id. Your notes show their ids in [brackets]."
            )
        self._report(reply, Step(StepKind.NOTED, tool, f"Forgot: {gone.text}"))
        return json.dumps({"deleted": gone.id}, ensure_ascii=False)

    def _question(self, tool: str, arguments: dict[str, Any], reply: AgentReply) -> str:
        """plan or ask_user: show it, wait for the answer, tell the model."""
        if tool == PLAN:
            return self._plan(arguments.get("steps"), reply)
        question = str(arguments.get("question", "")).strip()
        if not question:
            return "Error: 'question' is empty."
        given = arguments.get("options") or []
        options = tuple(str(option) for option in given if str(option).strip())
        if self.ask_user is None or self.dry_run:
            return NO_ANSWER_NOTE
        answer = self.ask_user(
            Question(QuestionKind.QUESTION, question, options[:MAX_OPTIONS])
        )
        self._report(
            reply,
            Step(
                StepKind.ASKED,
                tool,
                f"Asked: {question} · {answer if answer else 'no answer'}",
            ),
        )
        if not answer:
            return "The user didn't answer. Stop here and ask in your reply."
        return json.dumps({"answer": answer}, ensure_ascii=False)

    def _plan(self, given: Any, reply: AgentReply) -> str:
        if not isinstance(given, list):
            return "Error: 'steps' must be a list of short steps."
        steps = [str(step).strip() for step in given if str(step).strip()]
        if len(steps) < 2:
            return "Error: a plan needs at least 2 steps; for one step, just act."
        numbered = "\n".join(
            f"{number}. {step}"
            for number, step in enumerate(steps[:MAX_PLAN_STEPS], start=1)
        )
        self._report(reply, Step(StepKind.PLAN, PLAN, numbered))
        self._plan_shown = True
        if self.dry_run:
            return (
                "Dry run: the plan is shown and counts as approved. Carry it out "
                "now: Max checks each step and runs nothing."
            )
        if self.ask_user is None:
            return "Plan shown. Carry it out."
        answer = self.ask_user(Question(QuestionKind.PLAN, numbered))
        if answer is None:
            self._report(reply, Step(StepKind.ASKED, PLAN, "You stopped the plan"))
            return "The user stopped the plan. Do nothing more and say you stopped."
        if answer.strip().casefold() in GO_ANSWERS:
            self._report(reply, Step(StepKind.ASKED, PLAN, "You said go"))
            return "The user said go. Carry out the plan."
        self._report(reply, Step(StepKind.ASKED, PLAN, f"You asked for: {answer}"))
        return (
            f"The user wants changes: {answer}. Show a new plan with plan, or "
            "answer them."
        )

    def _load_group(self, name: str, reply: AgentReply) -> str:
        if name not in agent_groups():
            return f"Error: no group '{name}'. Groups: {', '.join(agent_groups())}."
        self.loaded.add(name)
        self._report(
            reply, Step(StepKind.LOADED, name, f"Looked up the {name} actions")
        )
        return group_actions(name)

    def _absolute(self, value: Any) -> Any:
        """A relative path (or pattern) as one under the agent's folder. The
        operations would read it from the process's folder, which can differ:
        the dashboard and the evals start the agent elsewhere."""
        if not isinstance(value, str) or not value.strip():
            return value
        path = Path(value).expanduser()
        return value if path.is_absolute() else str(self.scope.cwd / path)

    def _absolute_paths(self, action: Action, given: dict[str, Any]) -> dict[str, Any]:
        found = dict(given)
        for param in action.params:
            value = found.get(param.name)
            if param.kind not in PATH_KINDS or value in (None, ""):
                continue
            found[param.name] = (
                [self._absolute(item) for item in value]
                if isinstance(value, list)
                else self._absolute(value)
            )
        return found

    def _plan_first(self, action: Action) -> str:
        """Ask for a plan when a request turns to a second kind of action that
        changes files without one. Nobody to approve it means no plan needed."""
        if action.danger == Danger.NONE or self.ask_user is None:
            return ""
        changing = self._changing_actions
        if self._plan_shown or not changing or action.id in changing:
            changing.add(action.id)
            return ""
        return (
            "Error: this request needs more than one kind of action. Call plan "
            "with all the steps first, then run them."
        )

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
        plan_first = self._plan_first(action)
        if plan_first:
            return plan_first
        given = self._absolute_paths(action, given)
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
            return f"Dry run: checked {call.describe()}. {DRY_RUN_NOTE}"
        # A dry run (smart-sort --dry-run, organize --dry-run) changes
        # nothing, so it doesn't ask.
        changes_files = action.danger in CONFIRM_DANGERS and not arguments.get(
            "dry_run"
        )
        if changes_files and action.id in self._declined:
            return ASKED_BEFORE_NOTE.format(label=label)
        if changes_files and not self.confirm(call):
            self._declined.add(action.id)
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
        problem = _check_outputs(result) if result.ok else ""
        ok = result.ok and not problem
        message = f"{result.message} But {problem}" if problem else result.message
        self._report(
            reply,
            Step(
                StepKind.RAN if ok else StepKind.FAILED,
                run.action_id,
                f"{run.label}: {message}",
                result,
                arguments=shown,
                seconds=time.monotonic() - started,
                call_id=run.call_id,
            ),
        )
        answer = result.to_dict()
        if problem:
            answer["check"] = problem
        text = json.dumps(answer, ensure_ascii=False, default=str)
        return _Outcome(text[:MAX_RESULT_CHARS], ok, result, problem)

    def _run_each(
        self,
        action_id: str,
        given: dict[str, Any],
        each: list[str],
        reply: AgentReply,
        queue: bool = False,
        call_id: str = "",
        select: Optional[dict[str, Any]] = None,
    ) -> Union[str, _Batch]:
        """One action over several files: each file in turn fills the action's
        file argument. Every file is checked first; then one question covers
        the files that passed, and they run together. `select` narrows the
        files a folder or pattern gives."""
        from max_cli.core.catalog.runner import coerce_args

        select = select or {}
        try:
            limits = _file_filter(select)
        except ValueError as e:
            return f"Error: {e}"

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
        plan_first = self._plan_first(action)
        if plan_first:
            return plan_first
        given = self._absolute_paths(action, given)
        each = [self._absolute(item) for item in each]
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
                found = expand_each(
                    action,
                    {**given, param.name: wanted},
                    recursive=select.get("recursive") is True,
                    redo=select.get("redo") is True,
                )
            except MaxError as e:
                return f"Error: {e}"
            each = [str(path) for path in limits.select(found.files)]
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
            return (
                f"Error: that's {len(each)} files; one call takes at most "
                f"{MAX_EACH}. Narrow it with select (name, size, age) or a "
                "subfolder."
            )
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
        size = _total_size(Path(each_path) for each_path in each)
        whole = ActionCall(
            action,
            {
                **checked[0][1].arguments,
                param.name: _files_text(names, len(checked), size, len(done_already)),
            },
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
            return json.dumps(
                {
                    "dry_run": True,
                    "action": label,
                    "would_run": len(checked),
                    "size": _size_text(size),
                    "files": names[:MAX_LISTED_OUTPUTS],
                    "more_files": max(0, len(names) - MAX_LISTED_OUTPUTS),
                    "refused": [{"file": n, "error": why} for n, why in refused],
                    **_done_already(tuple(path.name for path in done_already)),
                    "note": DRY_RUN_NOTE,
                },
                ensure_ascii=False,
            )[:MAX_RESULT_CHARS]
        changes_files = action.danger in CONFIRM_DANGERS and not given.get("dry_run")
        if changes_files and action.id in self._declined:
            return ASKED_BEFORE_NOTE.format(label=label)
        if changes_files and not self.confirm(whole):
            self._declined.add(action.id)
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
        too_many = len(checked) > AUTO_QUEUE_FILES
        if (queue or too_many) and self.can_queue and action.queueable:
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
                    "note": (
                        f"{len(checked)} files is a long job, so Max queued it. "
                        if too_many and not queue
                        else ""
                    )
                    + "They run in the background; the user follows them with "
                    f"{self.jobs_hint}, and job_status shows how far they got. "
                    "Don't wait for them.",
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


def _look_at_image(path: Path, question: str) -> str:
    """The vision model's answer about one image in the allowed folders."""
    from max_cli.common.file_kinds import IMAGE, kind_of
    from max_cli.core.engines.ai_engine import AIEngine

    if not path.is_file() or kind_of(path) != IMAGE:
        raise ValueError(f"{path.name} isn't an image file.")
    if path.stat().st_size > MAX_IMAGE_MB * BYTES_PER_MB:
        raise ValueError(f"{path.name} is over {MAX_IMAGE_MB} MB; resize it first.")
    question = question.strip() or "Describe this image in two sentences."
    answer = AIEngine().analyze_image_content(path, question)
    return json.dumps(
        {"image": path.name, "answer": (answer or "").strip()[:MAX_RESULT_CHARS]},
        ensure_ascii=False,
    )


def _transcript(messages: list[dict[str, Any]]) -> str:
    """Messages as plain lines for the summary call: who said what, which
    tools ran, the start of each tool result."""
    lines = []
    for message in messages:
        role = message.get("role", "")
        content = str(message.get("content") or "")
        if role == "tool":
            lines.append(f"result: {content[:MAX_TRANSCRIPT_TOOL_CHARS]}")
            continue
        calls = message.get("tool_calls") or []
        names = ", ".join(
            f"{call['function']['name']}({call['function']['arguments']})"
            for call in calls
        )
        text = " ".join(
            part for part in (content, f"[calls {names}]" if names else "") if part
        )
        if text:
            lines.append(f"{role}: {text}")
    return "\n".join(lines)


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


def _files_text(names: list[str], count: int, size: int = 0, done: int = 0) -> str:
    """`142 files, 3.2 GB (a.m4a, b.m4a, c.m4a ...); 18 done already, skipped`
    for the one question a batch asks."""
    shown = ", ".join(names[:3]) + (" ..." if len(names) > 3 else "")
    text = f"{count} file{'s' if count != 1 else ''}"
    if size >= SIZE_SHOWN_FROM:
        text += f", {_size_text(size)}"
    text += f" ({shown})"
    if done:
        text += f"; {done} done already, skipped"
    return text


def _total_size(paths: Any) -> int:
    total = 0
    for path in paths:
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total


def _size_text(size: int) -> str:
    from max_cli.common.utils import format_size

    return format_size(size)


def _file_filter(select: Mapping[str, Any]) -> "looks.FileFilter":
    """select's limits; ValueError names one that isn't a number."""
    limits: dict[str, Any] = {}
    for name in SELECT_FILTERS:
        value = select.get(name)
        if value is None or value == "":
            continue
        if name == "name":
            limits[name] = str(value)
            continue
        try:
            limits[name] = float(value)
        except (TypeError, ValueError):
            raise ValueError(
                f"select.{name} must be a number, not {value!r}."
            ) from None
    return looks.FileFilter(**limits)


def _check_outputs(result: ActionResult) -> str:
    """What's wrong with the files a run reported, or "" when they look right:
    each must exist, and a file must not be empty."""
    missing: list[str] = []
    empty: list[str] = []
    for output in result.output_files:
        path = Path(output)
        try:
            if not path.exists():
                missing.append(path.name)
            elif path.is_file() and path.stat().st_size == 0:
                empty.append(path.name)
        except OSError:
            missing.append(path.name)
    problems = []
    if missing:
        problems.append(f"the check found no {', '.join(missing[:5])}")
    if empty:
        problems.append(
            f"{', '.join(empty[:5])} {'is' if len(empty) == 1 else 'are'} empty"
        )
    return "; ".join(problems) + ("." if problems else "")


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
