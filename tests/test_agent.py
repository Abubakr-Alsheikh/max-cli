"""The agent loop (core/agent) with a scripted model: no network, real actions in tmp_path."""

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

import openai
import pytest

from max_cli.common.exceptions import AIError, ConfigurationError
from max_cli.core.agent.agent import ActionCall, Agent, StepKind
from max_cli.core.agent.scope import PathScope, folders_named_in
from max_cli.core.agent.tools import agent_groups, tool_definitions
from max_cli.core.catalog import actions_for
from max_cli.core.catalog.spec import Surface
from max_cli.core.operations.result import ActionResult

# The first prompt (system message plus the two tool definitions) must stay
# small: about 4 characters per token, so this is roughly 1,500 tokens.
# 6,000 until phase 1 added job_status, remember, forget and select; 8,000
# until phase 2 added plan and ask_user (PLANS/completed/agent-phase1-...md,
# PLANS/active/agent-phase2-plan-ask-context.md).
FIRST_PROMPT_CHAR_BUDGET = 9_000


def _call(name: str, arguments: Any, call_id: str = "call-1") -> SimpleNamespace:
    text = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return SimpleNamespace(
        id=call_id, function=SimpleNamespace(name=name, arguments=text)
    )


def _answer(content: str = "", calls: tuple = (), tokens: int = 10) -> Any:
    message = SimpleNamespace(content=content, tool_calls=list(calls) or None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(total_tokens=tokens),
    )


class ScriptedModel:
    """Answers with the given responses in order and records each request."""

    def __init__(self, *responses: Any) -> None:
        self._responses = list(responses)
        self.requests: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **request: Any) -> Any:
        self.requests.append(json.loads(json.dumps(request, default=str)))
        return self._responses.pop(0)


def _agent(
    model: ScriptedModel, cwd: Path, answer: bool = True, **kwargs: Any
) -> Agent:
    asked: list[ActionCall] = []

    def confirm(call: ActionCall) -> bool:
        asked.append(call)
        return answer

    agent = Agent(model, "test-model", confirm=confirm, cwd=cwd, **kwargs)
    agent.asked = asked  # type: ignore[attr-defined]  # the test reads what was asked
    return agent


def _note(folder: Path, text: str = "hello\nworld\n") -> Path:
    note = folder / "note.txt"
    note.write_text(text, encoding="utf-8")
    return note


# --- what the model sees first ------------------------------------------------


def test_the_first_prompt_holds_only_the_group_list(tmp_path):
    model = ScriptedModel(_answer("Hi."))
    agent = _agent(model, tmp_path)

    agent.ask("hello")

    first = model.requests[0]
    system = first["messages"][0]["content"]
    for group in agent_groups():
        assert f"- {group}:" in system
    # No action's arguments are in it: those come from load_group.
    for group in agent_groups():
        for action in actions_for(group, Surface.AGENT):
            assert action.id not in system
    # Without the folder's path: test folders are long on macOS and Windows.
    size = len(system.replace(str(agent.scope.cwd), "")) + len(
        json.dumps(first["tools"])
    )
    assert size < FIRST_PROMPT_CHAR_BUDGET, f"first prompt is {size} characters"


def test_the_tools_look_load_and_run():
    names = [tool["function"]["name"] for tool in tool_definitions()]
    assert names == [
        "list_folder",
        "inspect",
        "find_files",
        "probe_link",
        "recent_activity",
        "job_status",
        "remember",
        "plan",
        "ask_user",
        "forget",
        "load_group",
        "run_action",
    ]


def test_only_a_queueing_agent_offers_the_queue_option():
    def run_options(can_queue: bool) -> set:
        [run] = [
            tool
            for tool in tool_definitions(can_queue)
            if tool["function"]["name"] == "run_action"
        ]
        return set(run["function"]["parameters"]["properties"])

    assert "queue" not in run_options(False)
    assert "queue" in run_options(True)


# --- running actions ----------------------------------------------------------


def test_loads_a_group_then_runs_its_action(tmp_path):
    note = _note(tmp_path)
    model = ScriptedModel(
        _answer(calls=(_call("load_group", {"name": "files"}),)),
        _answer(
            calls=(
                _call(
                    "run_action",
                    {"action": "files.preview", "arguments": {"target": str(note)}},
                    "call-2",
                ),
            )
        ),
        _answer("It says hello world.", tokens=25),
    )
    seen = []
    agent = _agent(model, tmp_path)
    agent.on_step = seen.append

    reply = agent.ask("what's in note.txt?")

    assert reply.text == "It says hello world."
    assert [step.kind for step in reply.steps] == [
        StepKind.LOADED,
        StepKind.STARTED,
        StepKind.RAN,
    ]
    started, ran = reply.steps[1:]
    assert started.label == "files preview"
    assert started.arguments["target"] == str(note)
    assert ran.arguments == started.arguments
    assert ran.seconds >= 0 and ran.result is not None
    assert seen == reply.steps
    assert reply.tokens == 45
    group_reply = model.requests[1]["messages"][-1]
    assert group_reply["role"] == "tool" and "files.preview" in group_reply["content"]
    action_reply = model.requests[2]["messages"][-1]
    assert action_reply["tool_call_id"] == "call-2"
    assert "hello" in action_reply["content"]


def test_an_action_needs_its_group_loaded_first(tmp_path):
    note = _note(tmp_path)
    model = ScriptedModel(
        _answer(
            calls=(
                _call(
                    "run_action",
                    {"action": "files.shred", "arguments": {"target": str(note)}},
                ),
            )
        ),
        _answer("Sorry."),
    )
    agent = _agent(model, tmp_path)

    reply = agent.ask("shred note.txt")

    assert note.exists()
    assert agent.asked == []
    assert reply.steps == []
    assert "load_group('files')" in model.requests[1]["messages"][-1]["content"]


def test_wrong_arguments_go_back_to_the_model(tmp_path):
    model = ScriptedModel(
        _answer(calls=(_call("load_group", {"name": "files"}),)),
        _answer(
            calls=(
                _call(
                    "run_action",
                    {"action": "files.preview", "arguments": {"colour": "red"}},
                ),
            )
        ),
        _answer("I couldn't."),
    )

    reply = _agent(model, tmp_path).ask("preview")

    assert reply.steps[-1].kind == StepKind.FAILED
    assert "unknown option" in model.requests[2]["messages"][-1]["content"]


@pytest.mark.parametrize(
    "call",
    [
        _call("run_action", "{not json"),
        _call("shell", {"command": "rm -rf /"}),
        _call("run_action", {"action": "files.nothing", "arguments": {}}),
    ],
)
def test_bad_tool_calls_are_answered_with_an_error(tmp_path, call):
    model = ScriptedModel(_answer(calls=(call,)), _answer("OK."))

    reply = _agent(model, tmp_path).ask("do it")

    assert reply.text == "OK."
    assert model.requests[1]["messages"][-1]["content"].startswith("Error:")


# --- looking -----------------------------------------------------------------


def test_list_folder_shows_kinds_without_asking(tmp_path):
    (tmp_path / "song.mp3").write_bytes(b"x")
    (tmp_path / "clip.mp4").write_bytes(b"x")
    (tmp_path / "sub").mkdir()
    model = ScriptedModel(
        _answer(calls=(_call("list_folder", {"path": "."}),)), _answer("Seen.")
    )
    agent = _agent(model, tmp_path)

    reply = agent.ask("what's here?")

    listing = json.loads(model.requests[1]["messages"][-1]["content"])
    assert listing["kinds"] == {"audio": 1, "video": 1}
    assert listing["subfolders"] == ["sub"]
    assert [entry["name"] for entry in listing["files"]] == ["clip.mp4", "song.mp3"]
    assert [step.kind for step in reply.steps] == [StepKind.LOOKED]
    assert agent.asked == []


def test_inspect_gives_a_files_facts(tmp_path):
    note = _note(tmp_path)
    model = ScriptedModel(
        _answer(calls=(_call("inspect", {"path": "note.txt"}),)), _answer("A note.")
    )

    _agent(model, tmp_path).ask("what is note.txt?")

    facts = json.loads(model.requests[1]["messages"][-1]["content"])
    assert facts["basics"]["kind"] == "document"
    assert facts["basics"]["size_bytes"] == note.stat().st_size


def test_inspect_summarises_a_photo_folder(tmp_path, dummy_image):
    photos = tmp_path / "photos"
    photos.mkdir()
    for index in range(2):
        (photos / f"p{index}.jpg").write_bytes(dummy_image.read_bytes())
    model = ScriptedModel(
        _answer(calls=(_call("inspect", {"path": "photos"}),)), _answer("Photos.")
    )

    _agent(model, tmp_path).ask("what's in photos?")

    facts = json.loads(model.requests[1]["messages"][-1]["content"])
    assert facts["image"]["image_count"] == 2


def test_looking_outside_the_allowed_folders_is_refused(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    model = ScriptedModel(
        _answer(calls=(_call("list_folder", {"path": str(tmp_path)}),)),
        _answer("I can't."),
    )

    reply = _agent(model, work).ask("list the parent")

    assert reply.steps[-1].kind == StepKind.REFUSED
    assert "outside" in model.requests[1]["messages"][-1]["content"]


def test_a_dry_run_action_runs_without_asking(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    model = ScriptedModel(
        _answer(calls=(_call("load_group", {"name": "files"}),)),
        _answer(
            calls=(
                _call(
                    "run_action",
                    {
                        "action": "files.order",
                        "arguments": {"folder": str(tmp_path), "dry_run": True},
                    },
                ),
            )
        ),
        _answer("It would number a.txt."),
    )
    agent = _agent(model, tmp_path, answer=False)

    reply = agent.ask("what would numbering do?")

    assert agent.asked == []
    assert reply.steps[-1].kind == StepKind.RAN
    assert (tmp_path / "a.txt").exists()


def _look_answer(model: "ScriptedModel") -> Any:
    return json.loads(model.requests[1]["messages"][-1]["content"])


def test_find_files_searches_subfolders_with_filters(tmp_path):
    old = tmp_path / "a" / "old.mp4"
    old.parent.mkdir()
    old.write_bytes(b"x" * 2_000_000)
    (tmp_path / "a" / "b").mkdir()
    (tmp_path / "a" / "b" / "small.mp4").write_bytes(b"x")
    (tmp_path / "song.mp3").write_bytes(b"x" * 3_000_000)
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "big.mp4").write_bytes(b"x" * 5_000_000)
    model = ScriptedModel(
        _answer(
            calls=(
                _call(
                    "find_files",
                    {"path": ".", "kind": "video", "min_size_mb": 1, "sort": "size"},
                ),
            )
        ),
        _answer("One big video."),
    )

    reply = _agent(model, tmp_path).ask("videos over 1 MB?")

    found = _look_answer(model)
    assert found["matches"] == 1
    assert found["files"][0]["path"] == str(Path("a") / "old.mp4")
    assert reply.steps[-1].text == f"Searched {tmp_path.name}"


def test_probe_link_reports_what_a_link_holds(tmp_path, monkeypatch):
    from max_cli.core.operations import grab

    info = grab.MediaInfo(
        url="https://youtu.be/x",
        title="A talk",
        duration=600.0,
        qualities=[grab.QualityOption(height=1080, size_bytes=50_000_000)],
    )
    monkeypatch.setattr(grab, "probe", lambda url: info)
    model = ScriptedModel(
        _answer(calls=(_call("probe_link", {"url": "https://youtu.be/x"}),)),
        _answer("A 10 minute talk."),
    )

    _agent(model, tmp_path).ask("what's this link?")

    found = _look_answer(model)
    assert found["title"] == "A talk" and found["duration_seconds"] == 600.0
    assert found["qualities"][0]["quality"] == "1080p"


def test_recent_activity_lists_actions_and_undoable_changes(tmp_path):
    from max_cli.common.activity_log import ActivityLog

    ActivityLog().add_entry(
        "video", "compress", "success", details={"message": "Saved small.mp4"}
    )
    model = ScriptedModel(
        _answer(calls=(_call("recent_activity", {}),)), _answer("You compressed.")
    )

    _agent(model, tmp_path).ask("what did I do?")

    found = _look_answer(model)
    assert found["actions"][0]["what"] == "video compress"
    assert found["actions"][0]["message"] == "Saved small.mp4"
    assert "file_changes_undo_can_reverse" in found


def test_a_queueing_agent_queues_a_long_job(tmp_path, monkeypatch, dummy_video):
    from max_cli.core.engines.task_manager import get_task_manager

    model = ScriptedModel(
        _answer(calls=(_call("load_group", {"name": "video"}),)),
        _answer(
            calls=(
                _call(
                    "run_action",
                    {
                        "action": "video.compress",
                        "arguments": {"target": str(dummy_video)},
                        "queue": True,
                    },
                ),
            )
        ),
        _answer("Queued; see Jobs (J)."),
    )
    agent = _agent(model, dummy_video.parent, can_queue=True)

    reply = agent.ask("compress it in the background")

    assert reply.steps[-1].kind == StepKind.QUEUED
    queued = json.loads(model.requests[2]["messages"][-1]["content"])
    assert queued["queued"] is True
    pending = get_task_manager().get_pending()
    assert [task.payload["action"] for task in pending] == ["video.compress"]


def test_without_queueing_a_queue_request_just_runs(tmp_path):
    model = ScriptedModel(
        _answer(calls=(_call("load_group", {"name": "files"}),)),
        _answer(
            calls=(
                _call(
                    "run_action",
                    {
                        "action": "files.preview",
                        "arguments": {"target": str(_note(tmp_path))},
                        "queue": True,
                    },
                ),
            )
        ),
        _answer("Read it."),
    )

    reply = _agent(model, tmp_path).ask("read it")

    assert reply.steps[-1].kind == StepKind.RAN


def test_requests_and_actions_go_into_the_activity_log(tmp_path):
    from max_cli.common.activity_log import ActivityLog

    note = _note(tmp_path)
    model = ScriptedModel(
        _answer(calls=(_call("load_group", {"name": "files"}),)),
        _answer(
            calls=(
                _call(
                    "run_action",
                    {"action": "files.preview", "arguments": {"target": str(note)}},
                ),
            )
        ),
        _answer("It says hello."),
    )

    _agent(model, tmp_path).ask("read note.txt")

    request, action = ActivityLog().get_entries(limit=2)
    assert (request.category, request.action) == ("ai", "agent")
    assert request.details["prompt"] == "read note.txt"
    assert request.details["message"] == "It says hello."
    assert (action.category, action.action, action.status) == (
        "files",
        "preview",
        "success",
    )
    assert action.details["args"]["target"] == str(note)
    assert action.details["via"] == "ai"


# --- guardrails ---------------------------------------------------------------


def _shred(note: Path) -> tuple:
    return (
        _answer(calls=(_call("load_group", {"name": "files"}),)),
        _answer(
            calls=(
                _call(
                    "run_action",
                    {"action": "files.shred", "arguments": {"target": str(note)}},
                ),
            )
        ),
    )


def test_a_delete_asks_and_a_no_keeps_the_file(tmp_path):
    note = _note(tmp_path)
    model = ScriptedModel(*_shred(note), _answer("Left it."))
    agent = _agent(model, tmp_path, answer=False)

    reply = agent.ask("shred note.txt")

    assert note.exists()
    assert [call.action.id for call in agent.asked] == ["files.shred"]
    assert reply.steps[-1].kind == StepKind.DECLINED
    assert "said no" in model.requests[2]["messages"][-1]["content"]


def test_a_delete_runs_after_a_yes(tmp_path):
    note = _note(tmp_path)
    model = ScriptedModel(*_shred(note), _answer("Gone."))

    reply = _agent(model, tmp_path, answer=True).ask("shred note.txt")

    assert not note.exists()
    assert reply.steps[-1].kind == StepKind.RAN


def test_confirmation_does_not_follow_the_confirm_destructive_setting(
    tmp_path, monkeypatch
):
    from max_cli.config import settings

    monkeypatch.setattr(settings, "CONFIRM_DESTRUCTIVE", False)
    note = _note(tmp_path)
    model = ScriptedModel(*_shred(note), _answer("Left it."))
    agent = _agent(model, tmp_path, answer=False)

    agent.ask("shred note.txt")

    assert note.exists() and agent.asked


def test_a_path_outside_the_allowed_folders_is_refused(tmp_path):
    work, elsewhere = tmp_path / "work", tmp_path / "elsewhere"
    work.mkdir()
    elsewhere.mkdir()
    note = _note(elsewhere)
    model = ScriptedModel(*_shred(note), _answer("I can't."))
    agent = _agent(model, work)

    reply = agent.ask("shred the note")

    assert note.exists()
    assert agent.asked == []
    assert reply.steps[-1].kind == StepKind.REFUSED
    assert "outside" in model.requests[2]["messages"][-1]["content"]


def test_a_folder_named_in_the_request_is_allowed(tmp_path):
    work, elsewhere = tmp_path / "work", tmp_path / "elsewhere"
    work.mkdir()
    elsewhere.mkdir()
    note = _note(elsewhere)
    model = ScriptedModel(*_shred(note), _answer("Gone."))

    _agent(model, work).ask(f"shred the note in {elsewhere}")

    assert not note.exists()


def test_dry_run_checks_without_running(tmp_path):
    note = _note(tmp_path)
    model = ScriptedModel(*_shred(note), _answer("Would shred it."))
    agent = _agent(model, tmp_path, dry_run=True)

    reply = agent.ask("shred note.txt")

    assert note.exists()
    assert agent.asked == []
    assert reply.steps[-1].kind == StepKind.PLANNED


def test_the_step_limit_counts_model_turns(tmp_path):
    turn = _answer(calls=(_call("load_group", {"name": "files"}),))
    model = ScriptedModel(turn, turn, turn)
    agent = _agent(model, tmp_path, max_steps=2)

    reply = agent.ask("loop")

    assert "stopped after 2 steps" in reply.text
    assert len(model.requests) == 2
    assert agent.messages[-1] == {"role": "assistant", "content": reply.text}


def test_the_action_limit_stops_a_request(tmp_path):
    loads = [_call("load_group", {"name": "files"}, f"call-{n}") for n in range(3)]
    model = ScriptedModel(_answer(calls=tuple(loads)))
    agent = _agent(model, tmp_path, max_actions=2)

    reply = agent.ask("loop")

    assert "stopped after 2 actions" in reply.text
    assert len(model.requests) == 1
    # Every tool call got an answer, so the conversation can go on.
    answers = {
        m["tool_call_id"]: m["content"] for m in agent.messages if m["role"] == "tool"
    }
    assert set(answers) == {"call-0", "call-1", "call-2"}
    assert answers["call-2"].startswith("Not run")


# --- several actions in one turn ---------------------------------------------------


def _previews(*targets: Path) -> tuple:
    """Load files, then preview each target in one turn."""
    return (
        _answer(calls=(_call("load_group", {"name": "files"}),)),
        _answer(
            calls=tuple(
                _call(
                    "run_action",
                    {"action": "files.preview", "arguments": {"target": str(target)}},
                    f"run-{n}",
                )
                for n, target in enumerate(targets)
            )
        ),
        _answer("Done."),
    )


def _track_runs(monkeypatch, barrier: Optional[threading.Barrier] = None) -> dict:
    """Replace run_action; record the most actions running at once."""
    from max_cli.core.catalog import runner

    seen = {"running": 0, "most": 0}
    lock = threading.Lock()

    def run_action(action, given):
        with lock:
            seen["running"] += 1
            seen["most"] = max(seen["most"], seen["running"])
        if barrier is not None:
            barrier.wait()  # times out unless the other action runs too
        time.sleep(0.05)
        with lock:
            seen["running"] -= 1
        return ActionResult(True, f"Read {Path(given['target']).name}")

    monkeypatch.setattr(runner, "run_action", run_action)
    return seen


def test_actions_from_one_turn_run_side_by_side(tmp_path, monkeypatch):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first, second = _note(tmp_path / "a"), _note(tmp_path / "b")
    seen = _track_runs(monkeypatch, threading.Barrier(2, timeout=5))
    model = ScriptedModel(*_previews(first, second))

    reply = _agent(model, tmp_path).ask("read both notes")

    assert seen["most"] == 2
    # The answers keep the calls' order and ids.
    answers = [m for m in model.requests[2]["messages"] if m["role"] == "tool"][-2:]
    assert [m["tool_call_id"] for m in answers] == ["run-0", "run-1"]
    assert all(json.loads(m["content"])["ok"] for m in answers)
    ran = {step.call_id for step in reply.steps if step.kind == StepKind.RAN}
    assert ran == {"run-0", "run-1"}


def test_actions_on_the_same_file_run_in_order(tmp_path, monkeypatch):
    note = _note(tmp_path)
    seen = _track_runs(monkeypatch)
    model = ScriptedModel(*_previews(note, note))

    _agent(model, tmp_path).ask("read it twice")

    assert seen["most"] == 1


def test_gemini_thought_signatures_go_back_with_their_calls(tmp_path):
    signed = _call("load_group", {"name": "files"})
    signed.extra_content = {"google": {"thought_signature": "c2lnbg=="}}
    model = ScriptedModel(_answer(calls=(signed,)), _answer("Done."))

    _agent(model, tmp_path).ask("look")

    sent = model.requests[1]["messages"][2]["tool_calls"][0]
    assert sent["extra_content"] == {"google": {"thought_signature": "c2lnbg=="}}


def test_the_conversation_carries_on(tmp_path):
    model = ScriptedModel(_answer("First."), _answer("Second."))
    agent = _agent(model, tmp_path)

    agent.ask("one")
    agent.ask("two")

    roles = [message["role"] for message in model.requests[1]["messages"]]
    assert roles == ["system", "user", "assistant", "user"]


# --- the provider ---------------------------------------------------------------


def test_a_model_without_tool_support_gets_a_clear_message(tmp_path):
    # openai 1-2 build this error from an httpx response, openai 3 from an
    # httpx2 one; skip __init__ so the test runs on either.
    error = openai.BadRequestError.__new__(openai.BadRequestError)
    Exception.__init__(error, "This model does not support tools")

    class NoTools(ScriptedModel):
        def _create(self, **request: Any) -> Any:
            raise error

    with pytest.raises(AIError, match="can't call tools"):
        _agent(NoTools(), tmp_path).ask("hi")


def test_without_a_key_or_ollama_there_is_no_agent(monkeypatch):
    from max_cli.config import settings

    # Pin every provider setting: the real settings file may set one up.
    monkeypatch.setattr(settings, "AI_PROVIDER", "openai")
    monkeypatch.setattr(settings, "AI_FALLBACK_PROVIDER", "")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", False)

    with pytest.raises(ConfigurationError, match="The AI isn.t set up"):
        Agent.from_settings(confirm=lambda call: False)


# --- the allowed folders ------------------------------------------------------


def test_scope_reads_paths_and_usual_folders(tmp_path, isolated_home):
    (isolated_home / "Downloads").mkdir()
    photos = tmp_path / "Photos"
    photos.mkdir()

    found = folders_named_in(f'shrink "{photos}" and my downloads, and/or more')

    assert photos.resolve() in found
    assert (isolated_home / "Downloads").resolve() in found


def test_scope_never_opens_a_whole_drive(tmp_path):
    anchor = Path(tmp_path.anchor)

    assert folders_named_in(f"look in {anchor}") == []


def test_scope_checks_the_folder_of_a_pattern(tmp_path):
    scope = PathScope(tmp_path)

    assert scope.allows(tmp_path / "music" / "*.mp3")
    assert scope.allows("relative/file.txt")
    assert not scope.allows(tmp_path.parent / "other.txt")


# --- one action over several files (each) ---------------------------------------------


def _each(action: str, files: list, arguments: Optional[dict] = None) -> tuple:
    group = action.split(".")[0]
    return (
        _answer(calls=(_call("load_group", {"name": group}),)),
        _answer(
            calls=(
                _call(
                    "run_action",
                    {"action": action, "arguments": arguments or {}, "each": files},
                    "batch",
                ),
            )
        ),
        _answer("Done."),
    )


def test_each_runs_one_action_over_several_files_side_by_side(tmp_path, monkeypatch):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    files = [str(_note(tmp_path / "a")), str(_note(tmp_path / "b"))]
    seen = _track_runs(monkeypatch, threading.Barrier(2, timeout=5))
    model = ScriptedModel(*_each("files.preview", files))

    reply = _agent(model, tmp_path).ask("read both notes")

    assert seen["most"] == 2
    summary = json.loads(model.requests[2]["messages"][-1]["content"])
    assert summary["files"] == 2 and summary["worked"] == 2
    assert summary["failed"] == []
    ran = [step.call_id for step in reply.steps if step.kind == StepKind.RAN]
    assert sorted(ran) == ["batch:0", "batch:1"]


def test_each_asks_once_for_the_whole_batch(tmp_path):
    notes = [tmp_path / "one.txt", tmp_path / "two.txt"]
    for note in notes:
        note.write_text("x", encoding="utf-8")
    model = ScriptedModel(*_each("files.shred", [str(note) for note in notes]))
    agent = _agent(model, tmp_path)

    agent.ask("shred both")

    assert len(agent.asked) == 1
    assert "2 files (one.txt, two.txt)" in agent.asked[0].describe()
    assert not any(note.exists() for note in notes)


def test_each_reports_files_that_fail_their_checks(tmp_path, monkeypatch):
    _track_runs(monkeypatch)
    inside = _note(tmp_path)
    outside = tmp_path.parent / "elsewhere.txt"
    model = ScriptedModel(*_each("files.preview", [str(inside), str(outside)]))

    _agent(model, tmp_path).ask("read them")

    summary = json.loads(model.requests[2]["messages"][-1]["content"])
    assert summary["worked"] == 1
    assert summary["failed"][0]["file"] == "elsewhere.txt"
    assert "outside" in summary["failed"][0]["error"]


def test_find_files_missing_lists_only_the_work_left(tmp_path):
    from max_cli.core.agent import looks

    for name in ("done.m4a", "done.mp3", "todo.m4a"):
        (tmp_path / name).write_bytes(b"\0")

    found = json.loads(looks.find_files(tmp_path, kind="audio", missing="mp3"))

    assert [item["path"] for item in found["files"]] == ["todo.m4a"]
    assert found["already_done"]["count"] == 1
    assert found["already_done"]["files"] == ["done.m4a"]


def _music_folder(folder: Path) -> Path:
    for name in ("done.m4a", "done.mp3", "new.m4a"):
        (folder / name).write_bytes(b"\0")
    return folder


def _convert(arguments: dict, each: Optional[list] = None) -> tuple:
    call: dict[str, Any] = {"action": "video.audio-convert", "arguments": arguments}
    if each is not None:
        call["each"] = each
    return (
        _answer(calls=(_call("load_group", {"name": "video"}),)),
        _answer(calls=(_call("run_action", call, "batch"),)),
        _answer("Done."),
    )


def test_a_folder_as_the_file_runs_the_files_left(tmp_path, monkeypatch):
    seen = _track_runs(monkeypatch)
    folder = _music_folder(tmp_path)
    model = ScriptedModel(*_convert({"target": str(folder), "format": "mp3"}))

    reply = _agent(model, tmp_path).ask("convert the m4a files to mp3")

    ran = [step.text for step in reply.steps if step.kind == StepKind.RAN]
    assert ran == ["video audio-convert: Read new.m4a"]
    summary = json.loads(model.requests[2]["messages"][-1]["content"])
    assert summary["done_already"] == ["done.m4a"]
    assert "skipped them" in summary["note"]
    assert seen["most"] == 1


def test_each_takes_a_pattern(tmp_path, monkeypatch):
    _track_runs(monkeypatch)
    _music_folder(tmp_path)
    model = ScriptedModel(*_convert({"format": "mp3"}, each=[str(tmp_path / "*.m4a")]))

    reply = _agent(model, tmp_path).ask("convert them")

    ran = [step.text for step in reply.steps if step.kind == StepKind.RAN]
    assert ran == ["video audio-convert: Read new.m4a"]


def test_nothing_left_to_do_runs_nothing(tmp_path, monkeypatch):
    seen = _track_runs(monkeypatch)
    for name in ("a.m4a", "a.mp3"):
        (tmp_path / name).write_bytes(b"\0")
    model = ScriptedModel(*_convert({"target": str(tmp_path), "format": "mp3"}))

    _agent(model, tmp_path).ask("convert them")

    summary = json.loads(model.requests[2]["messages"][-1]["content"])
    assert summary["files"] == 0
    assert summary["done_already"] == ["a.m4a"]
    assert seen["most"] == 0


def test_a_folder_outside_the_scope_is_not_listed(tmp_path, monkeypatch):
    """Reading it first sent the model the outside files' names."""
    seen = _track_runs(monkeypatch)
    work = tmp_path / "work"
    work.mkdir()
    secret = tmp_path / "private"
    secret.mkdir()
    (secret / "salary-2026.m4a").write_bytes(b"\0")
    model = ScriptedModel(*_convert({"target": str(secret), "format": "mp3"}))

    _agent(model, work).ask("convert them")

    answer = model.requests[2]["messages"][-1]["content"]
    assert "outside the folders I may use" in answer
    assert "salary" not in answer
    assert seen["most"] == 0


def test_files_whose_results_share_a_name_run_once_for_the_agent(tmp_path, monkeypatch):
    _track_runs(monkeypatch)
    for name in ("song.wav", "song.flac"):
        (tmp_path / name).write_bytes(b"\0")
    model = ScriptedModel(*_convert({"target": str(tmp_path), "format": "mp3"}))

    _agent(model, tmp_path).ask("convert them")

    summary = json.loads(model.requests[2]["messages"][-1]["content"])
    assert summary["worked"] == 1
    assert summary["failed"][0]["file"] == "song.wav"
    assert "same name" in summary["failed"][0]["error"]


# --- phase 1: select, preview, auto-queue, checks, jobs, memory -------------------


def _select_call(select: dict, target: str) -> tuple:
    call = {
        "action": "video.audio-convert",
        "arguments": {"target": target, "format": "mp3"},
        "select": select,
    }
    return (
        _answer(calls=(_call("load_group", {"name": "video"}),)),
        _answer(calls=(_call("run_action", call, "batch"),)),
        _answer("Done."),
    )


def test_select_reaches_subfolders_and_narrows_by_name(tmp_path, monkeypatch):
    _track_runs(monkeypatch)
    (tmp_path / "live").mkdir()
    for name in ("live/set live.m4a", "live/studio.m4a", "top live.m4a"):
        (tmp_path / name).write_bytes(b"\0")
    model = ScriptedModel(
        *_select_call({"recursive": True, "name": "*live*"}, str(tmp_path))
    )

    reply = _agent(model, tmp_path).ask("convert the live recordings")

    ran = sorted(step.text for step in reply.steps if step.kind == StepKind.RAN)
    assert ran == [
        "video audio-convert: Read set live.m4a",
        "video audio-convert: Read top live.m4a",
    ]


def test_a_select_limit_that_isnt_a_number_goes_back_to_the_model(
    tmp_path, monkeypatch
):
    seen = _track_runs(monkeypatch)
    model = ScriptedModel(*_select_call({"min_size_mb": "big"}, str(tmp_path)))

    _agent(model, tmp_path).ask("convert the big ones")

    answer = model.requests[2]["messages"][-1]["content"]
    assert "select.min_size_mb must be a number" in answer
    assert seen["most"] == 0


def test_the_batch_question_names_the_count_the_size_and_the_skipped():
    from max_cli.core.agent.agent import _files_text

    text = _files_text(["a", "b", "c", "d"], 4, 3 * 1024 * 1024, 2)

    assert text == "4 files, 3.00 MB (a, b, c ...); 2 done already, skipped"


def test_a_dry_run_batch_lists_the_files_it_would_run(tmp_path, monkeypatch):
    seen = _track_runs(monkeypatch)
    folder = _music_folder(tmp_path)
    model = ScriptedModel(*_convert({"target": str(folder), "format": "mp3"}))

    _agent(model, tmp_path, dry_run=True).ask("convert them")

    preview = json.loads(model.requests[2]["messages"][-1]["content"])
    assert preview["dry_run"] is True
    assert preview["would_run"] == 1
    assert preview["files"] == ["new.m4a"]
    assert preview["done_already"] == ["done.m4a"]
    assert seen["most"] == 0


def test_a_big_batch_of_a_queueable_action_goes_to_the_queue(tmp_path, monkeypatch):
    from max_cli.core.agent import agent as agent_module
    from max_cli.core.engines.task_manager import get_task_manager

    seen = _track_runs(monkeypatch)
    monkeypatch.setattr(agent_module, "AUTO_QUEUE_FILES", 1)
    for name in ("a.m4a", "b.m4a"):
        (tmp_path / name).write_bytes(b"\0")
    model = ScriptedModel(*_convert({"target": str(tmp_path), "format": "mp3"}))

    reply = _agent(model, tmp_path, can_queue=True).ask("convert all of them")

    answer = json.loads(model.requests[2]["messages"][-1]["content"])
    assert answer["queued"] == 2
    assert "Max queued it" in answer["note"]
    assert [step.kind for step in reply.steps].count(StepKind.QUEUED) == 2
    assert len(get_task_manager().get_pending()) == 2
    assert seen["most"] == 0


def _runs_returning(monkeypatch, outputs: list) -> None:
    from max_cli.core.catalog import runner

    monkeypatch.setattr(
        runner,
        "run_action",
        lambda action, given: ActionResult(True, "Converted", list(outputs)),
    )


def _one_convert(target: Path) -> tuple:
    return _convert({"target": str(target), "format": "mp3"})


@pytest.mark.parametrize(
    ("make", "found"),
    [
        (lambda folder: folder / "never-made.mp3", "found no never-made.mp3"),
        (
            lambda folder: (folder / "empty.mp3").write_bytes(b"")
            or folder / "empty.mp3",
            "empty.mp3 is empty",
        ),
    ],
)
def test_a_missing_or_empty_output_turns_the_run_into_a_failure(
    tmp_path, monkeypatch, make, found
):
    song = tmp_path / "song.m4a"
    song.write_bytes(b"\0")
    _runs_returning(monkeypatch, [make(tmp_path)])
    model = ScriptedModel(*_one_convert(song))

    reply = _agent(model, tmp_path).ask("convert it")

    [failed] = [step for step in reply.steps if step.kind == StepKind.FAILED]
    assert found in failed.text
    assert found in json.loads(model.requests[2]["messages"][-1]["content"])["check"]


def test_a_real_output_passes_the_check(tmp_path, monkeypatch):
    song = tmp_path / "song.m4a"
    song.write_bytes(b"\0")
    made = tmp_path / "song.mp3"
    made.write_bytes(b"ID3")
    _runs_returning(monkeypatch, [made])
    model = ScriptedModel(*_one_convert(song))

    reply = _agent(model, tmp_path).ask("convert it")

    assert [step.kind for step in reply.steps][-1] == StepKind.RAN
    assert "check" not in json.loads(model.requests[2]["messages"][-1]["content"])


def test_job_status_shows_waiting_and_finished_jobs():
    from max_cli.core.agent import looks
    from max_cli.core.engines.task_manager import get_task_manager
    from max_cli.core.engines.task_queue import TaskItem, TaskType

    manager = get_task_manager()
    manager.add(TaskItem(type=TaskType.ACTION, title="Compress holiday.mp4"))

    status = json.loads(looks.job_status())

    [waiting] = status["running_or_waiting"]
    assert waiting["title"] == "Compress holiday.mp4"
    assert waiting["status"] == "pending"
    assert status["finished"] == []


def test_remember_saves_a_note_the_next_session_starts_with(tmp_path):
    from max_cli.core.agent.memory import AgentMemory

    model = ScriptedModel(
        _answer(calls=(_call("remember", {"text": "Music lives in D:/Music"}),)),
        _answer("Noted."),
    )
    reply = _agent(model, tmp_path).ask("my music lives in D:/Music, remember that")

    [note] = AgentMemory().notes()
    later = _agent(ScriptedModel(_answer("Hi.")), tmp_path)
    assert note.text == "Music lives in D:/Music"
    assert reply.steps[0].kind == StepKind.NOTED
    assert f"[{note.id}] Music lives in D:/Music" in later.system_prompt()


def test_forget_deletes_the_note(tmp_path):
    from max_cli.core.agent.memory import AgentMemory

    note = AgentMemory().remember("Use 128 kbps")
    model = ScriptedModel(
        _answer(calls=(_call("forget", {"id": note.id}),)),
        _answer(calls=(_call("forget", {"id": "nope"}, "call-2"),)),
        _answer("Forgot it."),
    )

    _agent(model, tmp_path).ask("that's wrong, forget it")

    assert AgentMemory().notes() == []
    assert "no note with that id" in model.requests[2]["messages"][-1]["content"]


# --- phase 2: plans, questions, context, long chats --------------------------------

PLAN_STEPS = ["Find the m4a files under Music", "Convert them to mp3"]


def _plan_then_answer() -> ScriptedModel:
    return ScriptedModel(
        _answer(calls=(_call("plan", {"steps": PLAN_STEPS}),)),
        _answer("All right."),
    )


@pytest.mark.parametrize(
    ("answer", "told"),
    [
        ("go", "The user said go"),
        (None, "The user stopped the plan"),
        ("only the live ones", "The user wants changes: only the live ones"),
    ],
)
def test_a_plan_waits_for_the_users_answer(tmp_path, answer, told):
    from max_cli.core.agent.agent import QuestionKind

    asked = []
    model = _plan_then_answer()
    agent = _agent(
        model, tmp_path, ask=lambda question: asked.append(question) or answer
    )

    reply = agent.ask("convert my music")

    [question] = asked
    assert question.kind == QuestionKind.PLAN
    assert question.text == "1. Find the m4a files under Music\n2. Convert them to mp3"
    assert reply.steps[0].kind == StepKind.PLAN
    assert told in model.requests[1]["messages"][-1]["content"]


def test_a_plan_with_one_step_is_refused(tmp_path):
    model = ScriptedModel(
        _answer(calls=(_call("plan", {"steps": ["Convert"]}),)), _answer("OK.")
    )

    _agent(model, tmp_path, ask=lambda question: "go").ask("convert")

    assert "at least 2 steps" in model.requests[1]["messages"][-1]["content"]


def test_without_a_way_to_ask_the_plan_just_shows(tmp_path):
    model = _plan_then_answer()

    reply = _agent(model, tmp_path).ask("convert my music")

    assert reply.steps[0].kind == StepKind.PLAN
    assert "Carry it out" in model.requests[1]["messages"][-1]["content"]


def test_ask_user_passes_the_options_and_returns_the_answer(tmp_path):
    asked = []
    model = ScriptedModel(
        _answer(
            calls=(
                _call(
                    "ask_user",
                    {"question": "Move or delete them?", "options": ["Move", "Delete"]},
                ),
            )
        ),
        _answer("Moving them."),
    )
    agent = _agent(
        model, tmp_path, ask=lambda question: asked.append(question) or "Move"
    )

    reply = agent.ask("get rid of the duplicates")

    assert asked[0].options == ("Move", "Delete")
    assert json.loads(model.requests[1]["messages"][-1]["content"]) == {
        "answer": "Move"
    }
    assert reply.steps[0].kind == StepKind.ASKED


def test_ask_user_without_anyone_to_ask_picks_the_safe_option(tmp_path):
    model = ScriptedModel(
        _answer(calls=(_call("ask_user", {"question": "Which folder?"}),)),
        _answer("OK."),
    )

    _agent(model, tmp_path).ask("tidy up")

    assert "safest option" in model.requests[1]["messages"][-1]["content"]


def test_each_request_carries_the_folder_context(tmp_path):
    for name in ("a.mp4", "b.mp4", "c.jpg"):
        (tmp_path / name).write_bytes(b"\0")
    (tmp_path / "sub").mkdir()
    model = ScriptedModel(_answer("Hi."))

    _agent(model, tmp_path).ask("what's here?")

    sent = model.requests[0]["messages"][-1]["content"]
    assert sent.startswith("what's here?\n\n(Context from Max")
    assert "3 files (2 video, 1 image), 1 folder." in sent


def test_context_can_be_left_out(tmp_path):
    model = ScriptedModel(_answer("Hi."))

    _agent(model, tmp_path, context=False).ask("hello")

    assert model.requests[0]["messages"][-1]["content"] == "hello"


def test_a_long_chat_turns_its_oldest_turns_into_a_summary(tmp_path, monkeypatch):
    from max_cli.core.agent import agent as agent_module

    monkeypatch.setattr(agent_module, "COMPACT_AT_CHARS", 200)
    monkeypatch.setattr(agent_module, "KEEP_RECENT_REQUESTS", 1)
    model = ScriptedModel(
        _answer("First answer " + "x" * 200),
        _answer("Second answer"),
        _answer("You asked about photos and videos."),  # the summary call
        _answer("Third answer"),
    )
    agent = _agent(model, tmp_path, context=False)
    agent.ask("first request about photos")
    agent.ask("second request about videos")

    reply = agent.ask("third request")

    summary_call = model.requests[2]["messages"]
    assert "first request about photos" in summary_call[1]["content"]
    roles = [message["role"] for message in agent.messages]
    assert roles == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert agent.messages[1]["content"].startswith(
        "Summary of our earlier conversation:"
    )
    assert agent.messages[3]["content"] == "second request about videos"
    assert any(
        step.text == "Summarised the earlier conversation" for step in reply.steps
    )


def test_a_failed_summary_keeps_the_whole_chat(tmp_path, monkeypatch):
    from max_cli.core.agent import agent as agent_module

    monkeypatch.setattr(agent_module, "COMPACT_AT_CHARS", 10)
    monkeypatch.setattr(agent_module, "KEEP_RECENT_REQUESTS", 1)
    error = openai.APIConnectionError.__new__(openai.APIConnectionError)

    class FailsOnSummary(ScriptedModel):
        def _create(self, **request: Any) -> Any:
            if (
                request.get("messages", [{}])[0].get("content")
                == agent_module.SUMMARY_PROMPT
            ):
                raise error
            return super()._create(**request)

    model = FailsOnSummary(_answer("One."), _answer("Two."))
    agent = _agent(model, tmp_path, context=False)
    agent.ask("first")

    agent.ask("second")

    assert [m["content"] for m in agent.messages if m["role"] == "user"] == [
        "first",
        "second",
    ]
