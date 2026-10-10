"""Stopping a request, undoing the last one, and the context about jobs that
ended (core/agent/agent.py, changes.py, context.py). A scripted model, no
network; real files in tmp_path."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from max_cli.core.agent import changes
from max_cli.core.agent.agent import Agent, StepKind
from max_cli.core.operations.result import ActionResult


def _call(name: str, arguments: dict, call_id: str = "call-1") -> Any:
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def _answer(content: str = "", calls: tuple = ()) -> Any:
    message = SimpleNamespace(content=content, tool_calls=list(calls) or None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(total_tokens=10),
    )


class ScriptedModel:
    def __init__(self, *responses: Any) -> None:
        self._responses = list(responses)
        self.requests: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **request: Any) -> Any:
        self.requests.append(json.loads(json.dumps(request, default=str)))
        return self._responses.pop(0)


def _agent(model: ScriptedModel, cwd: Path, **kwargs: Any) -> Agent:
    kwargs.setdefault("ask", lambda question: "yes")
    return Agent(model, "test-model", confirm=lambda call: True, cwd=cwd, **kwargs)


def _convert(song: Path, call_id: str = "c2") -> Any:
    return _call(
        "run_action",
        {
            "action": "video.audio-convert",
            "arguments": {"target": str(song), "format": "mp3"},
        },
        call_id,
    )


def _fake_convert(monkeypatch, made: list, on_run: Any = None) -> None:
    """run_action that 'converts' by writing the .mp3 beside the song."""
    from max_cli.core.catalog import runner

    def run_action(action, given, **extra):
        output = Path(given["target"]).with_suffix(".mp3")
        output.write_bytes(b"ID3 converted")
        made.append(output)
        if on_run is not None:
            on_run()
        return ActionResult(True, "Converted", [output])

    monkeypatch.setattr(runner, "run_action", run_action)


# --- stop ------------------------------------------------------------------------


def test_stop_ends_the_request_after_the_running_step(tmp_path, monkeypatch):
    from max_cli.common.activity_log import ActivityLog

    songs = [tmp_path / "a.m4a", tmp_path / "b.m4a"]
    for song in songs:
        song.write_bytes(b"\0")
    made: list = []
    model = ScriptedModel(
        _answer(calls=(_call("load_group", {"name": "video"}),)),
        _answer(calls=(_convert(songs[0]),)),
        _answer(calls=(_convert(songs[1], "c3"),)),  # never asked for
        _answer("Done both."),
    )
    agent = _agent(model, tmp_path)
    _fake_convert(monkeypatch, made, on_run=agent.stop)

    reply = agent.ask("convert both")

    assert reply.stopped
    assert reply.text.startswith("Stopped, as you asked. 1 action finished")
    assert made == [tmp_path / "a.mp3"]
    assert len(model.requests) == 2
    request = ActivityLog().get_entries(limit=1, category_filter="ai")[0]
    assert request.status == "cancelled"


def test_the_next_request_runs_normally_after_a_stop(tmp_path):
    model = ScriptedModel(_answer("Hello."))
    agent = _agent(model, tmp_path)
    agent.stop()  # pressed while nothing ran: the next request clears it

    reply = agent.ask("hi")

    assert not reply.stopped
    assert reply.text == "Hello."


def test_actions_that_can_cancel_get_the_stop_switch():
    from max_cli.core.catalog import get_action
    from max_cli.core.catalog.runner import takes

    assert takes(get_action("grab.download"), "should_cancel")
    assert not takes(get_action("files.preview"), "should_cancel")


# --- undo the last request -------------------------------------------------------


def test_a_request_records_the_files_it_made_and_undo_puts_them_away(
    tmp_path, monkeypatch
):
    song = tmp_path / "a.m4a"
    song.write_bytes(b"\0")
    made: list = []
    _fake_convert(monkeypatch, made)
    model = ScriptedModel(
        _answer(calls=(_call("load_group", {"name": "video"}),)),
        _answer(calls=(_convert(song),)),
        _answer("Converted."),
        _answer(calls=(_call("undo_request", {}, "u1"),)),
        _answer("Put it back."),
    )
    asked = []
    agent = _agent(
        model, tmp_path, ask=lambda question: asked.append(question) or "yes"
    )

    agent.ask("convert it")
    record = changes.load()
    reply = agent.ask("undo what you just did")

    assert record is not None and [Path(m.path).name for m in record.made] == ["a.mp3"]
    assert "1 file it made (a.mp3)" in asked[0].text
    assert not (tmp_path / "a.mp3").exists()
    assert song.exists()
    [undone] = [step for step in reply.steps if step.kind == StepKind.UNDONE]
    assert undone.text.startswith("Moved 1 file it made to")
    assert changes.load() is None


def test_undo_leaves_a_file_changed_since(tmp_path):
    kept = tmp_path / "edited.mp3"
    kept.write_bytes(b"first")
    record = changes.RequestChanges("convert", made=[changes.MadeFile.of(kept)])
    kept.write_bytes(b"edited by the user afterwards")

    report = changes.undo(record)

    assert kept.exists()
    assert report.kept == ["edited.mp3"]
    assert "left 1 file that changed since" in report.message().lower()


def test_undo_reverses_recorded_renames(tmp_path):
    from max_cli.core.operations import files

    folder = tmp_path / "docs"
    folder.mkdir()
    for name in ("b.txt", "a.txt"):
        (folder / name).write_text(name, encoding="utf-8")
    result = files.order(folder)
    assert result.undo_group
    record = changes.RequestChanges("number them", undo_groups=[result.undo_group])

    report = changes.undo(record)

    assert report.reversed_groups == 1
    assert sorted(path.name for path in folder.iterdir()) == ["a.txt", "b.txt"]


def test_nothing_recorded_means_nothing_to_undo(tmp_path):
    model = ScriptedModel(
        _answer(calls=(_call("undo_request", {}),)), _answer("Nothing to undo.")
    )

    _agent(model, tmp_path).ask("undo that")

    assert "Nothing to undo" in model.requests[1]["messages"][-1]["content"]


def test_in_place_changes_are_named_as_not_undoable(tmp_path):
    record = changes.RequestChanges("tag them", in_place=["audio batch"])
    changes.save(record)

    report = changes.undo(changes.load())

    message = report.message().lower()

    assert "can't undo what these changed in place: audio batch" in message


# --- jobs that ended since the last request ----------------------------------------


def test_the_context_names_jobs_that_ended_since_the_last_request(tmp_path):
    from max_cli.common.activity_log import ActivityLog
    from max_cli.core.agent.context import finished_line
    from max_cli.core.engines.task_manager import get_task_manager
    from max_cli.core.engines.task_queue import TaskItem, TaskStatus, TaskType

    ActivityLog().add_entry("ai", "agent", "success", {"prompt": "queue them"})
    manager = get_task_manager()
    for title, status in (
        ("Compress a.mp4", TaskStatus.COMPLETED),
        ("b", TaskStatus.FAILED),
    ):
        manager.record(TaskItem(type=TaskType.ACTION, title=title, status=status))

    line = finished_line()

    assert line.startswith("Finished since your last request:")
    assert "Compress a.mp4 (done)" in line and "b (failed)" in line


def test_no_earlier_request_means_no_finished_line():
    from max_cli.core.agent.context import finished_line

    assert finished_line() == ""
