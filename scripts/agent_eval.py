"""Score the AI agent's choices on set requests, with your real AI model.

    python scripts/agent_eval.py               # every scenario
    python scripts/agent_eval.py --only batch  # one scenario by name
    python scripts/agent_eval.py --list        # their names and requests

Each scenario makes a temporary folder of small files and asks the agent in
dry-run mode: nothing runs, nothing changes, nothing is asked. Then it checks
what the agent chose: one batch call instead of a call per file, a plan
before multi-step work, looking before advising, saving a fact it was told.

It uses the AI you set up (max config setup), so each run costs a few model
requests. Max's own data (the activity log, the agent's notes) goes to a
temporary home, so your history and notes stay as they were. Exit code 1
when a scenario fails, so you can compare models or prompts run to run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
FILE_BYTES = b"\0" * 64  # small placeholder files: a dry run never runs on them
# A silent MPEG frame: an .mp3 the agent can read tags from (audio.get).
MP3_FRAME = b"\xff\xfb\x90\x64" + b"\0" * 413
MP3_FRAMES = 5


@dataclass
class Run:
    """What the agent did on one scenario."""

    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    tokens: int = 0
    seconds: float = 0.0
    reply: str = ""

    def named(self, tool: str) -> list[dict[str, Any]]:
        return [arguments for name, arguments in self.calls if name == tool]

    def actions(self, action: str) -> list[dict[str, Any]]:
        return [
            args for args in self.named("run_action") if args.get("action") == action
        ]


Check = Callable[[Run], Optional[str]]  # the problem, or None when it passed


def one_batch(action: str) -> Check:
    def check(run: Run) -> str | None:
        calls = run.actions(action)
        if len(calls) != 1:
            return f"{len(calls)} {action} calls; one batch call expected"
        return None

    return check


def called(tool: str) -> Check:
    def check(run: Run) -> str | None:
        return None if run.named(tool) else f"never called {tool}"

    return check


def never(action: str) -> Check:
    def check(run: Run) -> str | None:
        calls = run.actions(action)
        return f"called {action}, which is the wrong tool here" if calls else None

    return check


def ran_nothing(run: Run) -> str | None:
    actions = run.named("run_action")
    return (
        f"ran {len(actions)} actions; only looking was asked for" if actions else None
    )


def looked_first(run: Run) -> str | None:
    looks = {"list_folder", "find_files", "inspect"}
    return None if any(name in looks for name, _ in run.calls) else "never looked"


@dataclass(frozen=True)
class Scenario:
    name: str
    request: str
    files: tuple[str, ...]
    checks: tuple[Check, ...]


SCENARIOS = (
    Scenario(
        "batch",
        "Convert every m4a file under the music folder, subfolders too, to mp3.",
        ("music/a.m4a", "music/b.m4a", "music/live/c.m4a", "music/a.mp3"),
        (one_batch("video.audio-convert"),),
    ),
    Scenario(
        "track-numbers",
        "Fix the track numbers of the songs in this folder; they're all wrong.",
        ("01 Intro.mp3", "02 Night Drive.mp3", "03 Afterglow.mp3", "04 Outro.mp3"),
        (one_batch("audio.batch"), never("files.order")),
    ),
    Scenario(
        "plan",
        "Merge the two PDFs here into one file, then convert both photos to "
        "webp, then compress the merged PDF.",
        ("report1.pdf", "report2.pdf", "photo1.jpg", "photo2.jpg"),
        (called("plan"),),
    ),
    Scenario(
        "look-first",
        "What's taking the most space in this folder?",
        ("movie.mp4", "song.mp3", "notes.txt", "photos/a.jpg"),
        (looked_first, ran_nothing),
    ),
    Scenario(
        "memory",
        "Remember that my music lives in D:/Music.",
        (),
        (called("remember"),),
    ),
)


class RecordingClient:
    """Wraps the real client and records each tool call the model makes."""

    def __init__(self, client: Any, run: Run) -> None:
        self._client = client
        self._run = run
        self.chat = self  # agent calls client.chat.completions.create
        self.completions = self
        self.model = getattr(client, "model", "")

    def create(self, **request: Any) -> Any:
        response = self._client.chat.completions.create(**request)
        for call in response.choices[0].message.tool_calls or []:
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            self._run.calls.append((call.function.name, arguments))
        self.model = getattr(self._client, "model", self.model)
        return response


def run_scenario(scenario: Scenario, client: Any, model: str, folder: Path) -> Run:
    from max_cli.core.agent.agent import Agent
    from max_cli.core.agent.memory import AgentMemory

    for name in scenario.files:
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(
            MP3_FRAME * MP3_FRAMES if path.suffix == ".mp3" else FILE_BYTES
        )
    run = Run()
    agent = Agent(
        RecordingClient(client, run),
        model,
        confirm=lambda call: True,
        ask=lambda question: "go",
        cwd=folder,
        dry_run=True,
        memory=AgentMemory(folder.parent / "notes.json"),
        shell=False,
    )
    started = time.monotonic()
    reply = agent.ask(scenario.request)
    run.seconds = time.monotonic() - started
    run.tokens = reply.tokens
    run.reply = reply.text
    return run


def score(scenario: Scenario, run: Run) -> list[str]:
    return [problem for check in scenario.checks if (problem := check(run))]


def _use_a_temporary_home(home: Path) -> None:
    """Point Max's data at `home` after the settings (your AI keys) loaded."""
    import max_cli.config  # noqa: F401 - reads ~/.max_config.env from the real home

    os.environ["HOME"] = str(home)
    os.environ["USERPROFILE"] = str(home)
    from max_cli.common.activity_log import ActivityLog

    ActivityLog.LOG_FILE = home / ".max_cli" / "activity_log.json"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="run one scenario, by name")
    parser.add_argument("--list", action="store_true", help="list the scenarios")
    options = parser.parse_args(argv)
    if options.list:
        for scenario in SCENARIOS:
            print(f"{scenario.name:<12} {scenario.request}")
        return 0
    chosen = [s for s in SCENARIOS if not options.only or s.name == options.only]
    if not chosen:
        print(f"No scenario called {options.only}; --list shows them.")
        return 1
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from max_cli.common.exceptions import MaxError
    from max_cli.core.engines.ai_providers import chat_model, make_client

    client = make_client()
    if client is None:
        print("The AI isn't set up: run `max config setup` first.")
        return 1
    failed = 0
    with tempfile.TemporaryDirectory(prefix="max-agent-eval-") as temp:
        _use_a_temporary_home(Path(temp) / "home")
        for scenario in chosen:
            folder = Path(temp) / scenario.name
            folder.mkdir()
            try:
                run = run_scenario(scenario, client, chat_model(), folder)
            except MaxError as e:
                failed += 1
                print(f"FAIL  {scenario.name:<12} {e}")
                continue
            problems = score(scenario, run)
            failed += bool(problems)
            calls = ", ".join(name for name, _ in run.calls) or "no tools"
            print(
                f"{'FAIL' if problems else 'PASS'}  {scenario.name:<12} "
                f"{run.tokens:,} tokens  {run.seconds:.1f}s  [{calls}]"
            )
            for problem in problems:
                print(f"      {problem}")
    print(f"\n{len(chosen) - failed} of {len(chosen)} passed on {chat_model()}.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
