"""CliRunner tests for `max ai` (src/max_cli/interface/cli_ai.py).

Every test replaces `_get_engine` with a MagicMock, or the AI client with a
scripted model, so no network call or real history file is touched.
"""

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from max_cli.common.exceptions import MaxError
from max_cli.interface import cli_ai
from max_cli.interface.cli_ai import app as ai_app

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})

ENGINE_PATH = "max_cli.interface.cli_ai._get_engine"
CLIENT_PATH = "max_cli.core.engines.ai_providers.make_client"
DOWNLOAD_PATH = "max_cli.core.engines.ai_engine.download_image"

# The shared Rich console is built at import time, so it may still emit ANSI
# styles inside CliRunner. Strip them before substring checks.
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

VISIBLE_COMMANDS = [
    "ask",
    "analyze",
    "create",
    "edit",
    "chat",
    "search",
    "extract",
    "memory",
    "undo",
]
HIDDEN_ALIASES = ["a", "ana", "c", "ch", "s"]


def _plain(result) -> str:
    return ANSI_ESCAPE.sub("", result.output)


def _call(name: str, arguments: dict, call_id: str = "call-1") -> Any:
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def _answer(content: str = "", calls: tuple = ()) -> Any:
    message = SimpleNamespace(content=content, tool_calls=list(calls) or None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(total_tokens=42),
    )


class ScriptedModel:
    """An AI client that answers with the given responses, in order."""

    def __init__(self, *responses: Any) -> None:
        self._responses = list(responses)
        self.requests: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **request: Any) -> Any:
        self.requests.append(request)
        answer = self._responses.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def _shred_script(target: Path, final: str) -> ScriptedModel:
    return ScriptedModel(
        _answer(calls=(_call("load_group", {"name": "files"}),)),
        _answer(
            calls=(
                _call(
                    "run_action",
                    {"action": "files.shred", "arguments": {"target": str(target)}},
                    "call-2",
                ),
            )
        ),
        _answer(final),
    )


@pytest.fixture
def note(tmp_path, monkeypatch) -> Path:
    """A file in the folder the agent starts in."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "note.txt"
    target.write_text("hello", encoding="utf-8")
    return target


def test_group_help_lists_visible_commands() -> None:
    result = runner.invoke(ai_app, ["--help"])

    assert result.exit_code == 0
    for command in VISIBLE_COMMANDS:
        assert command in result.stdout


@pytest.mark.parametrize("command", VISIBLE_COMMANDS + HIDDEN_ALIASES)
def test_command_help(command: str) -> None:
    result = runner.invoke(ai_app, [command, "--help"])

    assert result.exit_code == 0, result.output
    assert "Usage" in result.stdout


class TestAsk:
    def test_runs_the_agent_and_shows_its_steps(self, note) -> None:
        model = ScriptedModel(
            _answer(calls=(_call("load_group", {"name": "files"}),)),
            _answer(
                calls=(
                    _call(
                        "run_action",
                        {
                            "action": "files.preview",
                            "arguments": {"target": "note.txt"},
                        },
                        "call-2",
                    ),
                )
            ),
            _answer("note.txt says hello."),
        )
        with patch(CLIENT_PATH, return_value=model):
            result = runner.invoke(ai_app, ["ask", "what does note.txt say?"])

        assert result.exit_code == 0, result.output
        output = _plain(result)
        assert "Looked up the files actions" in output
        assert "✓" in output
        assert "note.txt says hello." in output
        assert "126 tokens" in output  # three answers of 42

    @pytest.mark.parametrize("answer", [True, False])
    def test_asks_before_a_delete(self, note, answer: bool) -> None:
        model = _shred_script(note, "Done.")
        with (
            patch(CLIENT_PATH, return_value=model),
            patch.object(cli_ai.Confirm, "ask", return_value=answer) as asked,
        ):
            result = runner.invoke(ai_app, ["ask", "shred note.txt"])

        assert result.exit_code == 0, result.output
        assert "files shred" in asked.call_args.args[0]
        assert note.exists() is not answer

    def test_dry_run_runs_nothing(self, note) -> None:
        model = _shred_script(note, "I would shred it.")
        with (
            patch(CLIENT_PATH, return_value=model),
            patch.object(cli_ai.Confirm, "ask") as asked,
        ):
            result = runner.invoke(ai_app, ["ask", "shred note.txt", "--dry-run"])

        assert result.exit_code == 0, result.output
        assert note.exists()
        asked.assert_not_called()
        assert "Would run files shred" in _plain(result)

    def test_without_an_ai_set_up_exits_1(self, note) -> None:
        with patch(CLIENT_PATH, return_value=None):
            result = runner.invoke(ai_app, ["ask", "anything"])

        assert result.exit_code == 1
        assert "The AI isn't set up" in _plain(result)

    def test_old_explain_flag_still_works(self, note) -> None:
        with patch(CLIENT_PATH, return_value=ScriptedModel(_answer("Hi."))):
            result = runner.invoke(ai_app, ["ask", "hello", "--explain"])

        assert result.exit_code == 0, result.output

    def test_never_runs_other_programs(self) -> None:
        source = Path(cli_ai.__file__).read_text(encoding="utf-8")

        assert "subprocess" not in source


class TestAnalyze:
    def test_renders_analysis(self, dummy_image: Path) -> None:
        engine = MagicMock()
        engine.analyze_image_content.return_value = "A **red** square."
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(
                ai_app, ["analyze", str(dummy_image), "-p", "What colour?"]
            )

        assert result.exit_code == 0, result.output
        engine.analyze_image_content.assert_called_once_with(
            dummy_image, "What colour?"
        )
        output = _plain(result)
        assert "Analysis: test.jpg" in output
        assert "square" in output

    def test_missing_image_exits_1(self, tmp_path: Path) -> None:
        with patch(ENGINE_PATH) as get_engine:
            result = runner.invoke(ai_app, ["analyze", str(tmp_path / "none.png")])

        assert result.exit_code == 1
        get_engine.assert_not_called()
        assert "Image file not found" in _plain(result)

    def test_engine_error_exits_1(self, dummy_image: Path) -> None:
        engine = MagicMock()
        engine.analyze_image_content.side_effect = MaxError("vision model offline")
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(ai_app, ["analyze", str(dummy_image)])

        assert result.exit_code == 1
        assert not isinstance(result.exception, MaxError)
        assert "vision model offline" in _plain(result)


class TestCreateAndEdit:
    def test_create_downloads_generated_image(self, tmp_path: Path) -> None:
        engine = MagicMock()
        engine.generate_image.return_value = "https://img.example/cat.png"
        output = tmp_path / "cat.png"
        with (
            patch(ENGINE_PATH, return_value=engine),
            patch(DOWNLOAD_PATH) as download_mock,
        ):
            result = runner.invoke(ai_app, ["create", "a cat", "-o", str(output)])

        assert result.exit_code == 0, result.output
        # No --model: the image models picked in settings answer.
        engine.generate_image.assert_called_once_with("a cat", model=None)
        download_mock.assert_called_once_with("https://img.example/cat.png", output)
        output_text = _plain(result)
        assert "Image Ready!" in output_text
        assert "Saved to:" in output_text

    def test_create_download_failure_is_a_warning(self, tmp_path: Path) -> None:
        engine = MagicMock()
        engine.generate_image.return_value = "https://img.example/cat.png"
        with (
            patch(ENGINE_PATH, return_value=engine),
            patch(DOWNLOAD_PATH, side_effect=OSError("disk full")),
        ):
            result = runner.invoke(
                ai_app, ["create", "a cat", "-o", str(tmp_path / "cat.png")]
            )

        assert result.exit_code == 0, result.output
        assert "Could not save the image: disk full" in _plain(result)

    def test_create_engine_error_is_reported(self) -> None:
        engine = MagicMock()
        engine.generate_image.side_effect = MaxError("quota exceeded")
        with (
            patch(ENGINE_PATH, return_value=engine),
            patch(DOWNLOAD_PATH) as download_mock,
        ):
            result = runner.invoke(ai_app, ["create", "a cat"])

        assert result.exit_code == 0
        assert result.exception is None
        download_mock.assert_not_called()
        assert "quota exceeded" in _plain(result)

    def test_edit_uses_custom_model(self, dummy_image: Path, tmp_path: Path) -> None:
        engine = MagicMock()
        engine.edit_image.return_value = "https://img.example/edit.png"
        output = tmp_path / "edited.png"
        with (
            patch(ENGINE_PATH, return_value=engine),
            patch(DOWNLOAD_PATH) as download_mock,
        ):
            result = runner.invoke(
                ai_app,
                [
                    "edit",
                    str(dummy_image),
                    "make it blue",
                    "-o",
                    str(output),
                    "--model",
                    "custom-model",
                ],
            )

        assert result.exit_code == 0, result.output
        engine.edit_image.assert_called_once_with(
            dummy_image, "make it blue", model="custom-model"
        )
        download_mock.assert_called_once_with("https://img.example/edit.png", output)

    def test_edit_missing_file_exits_1(self, tmp_path: Path) -> None:
        result = runner.invoke(ai_app, ["edit", str(tmp_path / "none.png"), "x"])

        assert result.exit_code == 1
        assert "File not found" in _plain(result)

    def test_edit_engine_error_is_reported(self, dummy_image: Path) -> None:
        engine = MagicMock()
        engine.edit_image.side_effect = MaxError("edit refused")
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(ai_app, ["edit", str(dummy_image), "x"])

        assert result.exit_code == 0
        assert result.exception is None
        assert "edit refused" in _plain(result)


class TestChat:
    def test_clear_history(self) -> None:
        engine = MagicMock()
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(ai_app, ["chat", "--clear"])

        assert result.exit_code == 0, result.output
        engine.clear_history.assert_called_once_with()
        assert "Conversation history cleared." in _plain(result)

    def test_export_history(self, tmp_path: Path) -> None:
        engine = MagicMock()
        export_path = tmp_path / "chat.json"
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(ai_app, ["chat", "--export", str(export_path)])

        assert result.exit_code == 0, result.output
        engine.export_history.assert_called_once_with(export_path)
        assert "Conversation exported to" in _plain(result)

    def test_import_history(self, tmp_path: Path) -> None:
        engine = MagicMock()
        import_path = tmp_path / "chat.json"
        import_path.write_text(json.dumps({"history": []}), encoding="utf-8")
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(ai_app, ["chat", "--import", str(import_path)])

        assert result.exit_code == 0, result.output
        engine.import_history.assert_called_once_with(import_path)
        assert "Conversation imported from" in _plain(result)

    def test_import_missing_file_exits_1(self, tmp_path: Path) -> None:
        with patch(ENGINE_PATH) as get_engine:
            result = runner.invoke(
                ai_app, ["chat", "--import", str(tmp_path / "none.json")]
            )

        assert result.exit_code == 1
        get_engine.assert_not_called()
        assert "File not found" in _plain(result)

    def test_interactive_session_answers_then_exits(self, note) -> None:
        engine = MagicMock()
        engine.history = [{"role": "user", "content": "earlier"}]
        with (
            patch(ENGINE_PATH, return_value=engine),
            patch(CLIENT_PATH, return_value=ScriptedModel(_answer("Hello there!"))),
            patch.object(cli_ai.Prompt, "ask", side_effect=["hi", "exit"]),
        ):
            result = runner.invoke(ai_app, ["chat"])

        assert result.exit_code == 0, result.output
        output = _plain(result)
        assert "Hello there!" in output
        assert "Remembering 1 earlier messages" in output
        assert "Goodbye!" in output
        assert engine.history[-2:] == [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "Hello there!"},
        ]
        engine._save_history.assert_called_once()

    def test_interactive_error_is_reported_and_the_session_goes_on(self, note) -> None:
        from max_cli.common.exceptions import AIError

        engine = MagicMock()
        engine.history = []
        model = ScriptedModel(AIError("rate limited"), _answer("Back."))
        with (
            patch(ENGINE_PATH, return_value=engine),
            patch(CLIENT_PATH, return_value=model),
            patch.object(cli_ai.Prompt, "ask", side_effect=["one", "two", "quit"]),
        ):
            result = runner.invoke(ai_app, ["chat"])

        assert result.exit_code == 0
        assert result.exception is None
        output = _plain(result)
        assert "rate limited" in output
        assert "Back." in output
        assert "Goodbye!" in output

    def test_export_engine_error_propagates_to_main_handler(
        self, tmp_path: Path
    ) -> None:
        # --export has no local try/except; max_cli.main.main() reports MaxError.
        engine = MagicMock()
        engine.export_history.side_effect = MaxError("cannot write")
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(
                ai_app, ["chat", "--export", str(tmp_path / "chat.json")]
            )

        assert result.exit_code == 1
        assert isinstance(result.exception, MaxError)


class TestSearch:
    def test_lists_matches(self, tmp_path: Path) -> None:
        notes = tmp_path / "notes.md"
        notes.write_text("budget for 2026", encoding="utf-8")
        (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8")
        engine = MagicMock()
        engine.semantic_search.return_value = [
            {"file": str(notes), "reasoning": "Mentions the budget"}
        ]
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(ai_app, ["search", "budget", str(tmp_path)])

        assert result.exit_code == 0, result.output
        query, files = engine.semantic_search.call_args.args
        assert query == "budget"
        assert files == [notes]
        output = _plain(result)
        assert "Found 1 matching file(s)" in output
        assert "Mentions the budget" in output

    def test_no_searchable_files(self, tmp_path: Path) -> None:
        with patch(ENGINE_PATH) as get_engine:
            result = runner.invoke(ai_app, ["search", "budget", str(tmp_path)])

        assert result.exit_code == 0
        get_engine.assert_not_called()
        assert "No matching files found." in _plain(result)

    def test_missing_folder_exits_1(self, tmp_path: Path) -> None:
        result = runner.invoke(ai_app, ["search", "x", str(tmp_path / "missing")])

        assert result.exit_code == 1
        assert "Folder not found" in _plain(result)

    def test_engine_error_is_reported(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("text", encoding="utf-8")
        engine = MagicMock()
        engine.semantic_search.side_effect = MaxError("embedding failed")
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(ai_app, ["search", "x", str(tmp_path)])

        assert result.exit_code == 0
        assert result.exception is None
        assert "Search failed: embedding failed" in _plain(result)


class TestExtract:
    def test_prints_and_saves_result(self, dummy_image: Path, tmp_path: Path) -> None:
        engine = MagicMock()
        engine.extract_structured_data.return_value = {"total": "9.99"}
        output = tmp_path / "out.json"
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(
                ai_app,
                [
                    "extract",
                    str(dummy_image),
                    "-s",
                    "total:Total amount",
                    "-o",
                    str(output),
                ],
            )

        assert result.exit_code == 0, result.output
        assert json.loads(output.read_text(encoding="utf-8")) == {"total": "9.99"}
        output_text = _plain(result)
        assert "Extracted Data:" in output_text
        assert '"total": "9.99"' in output_text

    def test_schema_field_reaches_engine(self, dummy_image: Path) -> None:
        engine = MagicMock()
        engine.extract_structured_data.return_value = {}
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(
                ai_app,
                [
                    "extract",
                    str(dummy_image),
                    "-s",
                    "total:Total amount",
                    "-s",
                    "date:Date",
                ],
            )

        assert result.exit_code == 0, result.output
        engine.extract_structured_data.assert_called_once_with(
            dummy_image, {"total": "Total amount", "date": "Date"}
        )

    def test_missing_file_exits_1(self, tmp_path: Path) -> None:
        result = runner.invoke(
            ai_app, ["extract", str(tmp_path / "none.png"), "-s", "total"]
        )

        assert result.exit_code == 1
        assert "File not found" in _plain(result)

    def test_engine_error_is_reported(self, dummy_image: Path) -> None:
        engine = MagicMock()
        engine.extract_structured_data.side_effect = MaxError(
            "AI Client not configured."
        )
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(ai_app, ["extract", str(dummy_image), "-s", "total"])

        assert result.exit_code == 0
        assert result.exception is None
        assert "Extraction failed: AI Client not configured." in _plain(result)


def test_search_warns_about_extensions_it_cannot_read(tmp_path: Path) -> None:
    """--ext pdf used to be accepted and then skipped without a word."""
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "paper.pdf").write_bytes(b"%PDF")
    engine = MagicMock()
    engine.semantic_search.return_value = []
    with patch(ENGINE_PATH, return_value=engine):
        result = runner.invoke(
            ai_app, ["search", "hello", str(tmp_path), "--ext", "txt,pdf"]
        )

    assert result.exit_code == 0, result.output
    assert "Skipping pdf" in _plain(result)
    searched = engine.semantic_search.call_args.args[1]
    assert [p.name for p in searched] == ["notes.txt"]


def test_a_result_after_another_actions_lines_names_its_action_again():
    from max_cli.common.logger import console
    from max_cli.core.agent.agent import Step, StepKind
    from max_cli.core.operations.result import ActionResult

    def step(kind: StepKind, call_id: str, target: str) -> Step:
        result = (
            ActionResult(True, f"Compressed {target}") if kind != "started" else None
        )
        return Step(
            kind,
            "audio.compress",
            "",
            result,
            arguments={"target": target},
            call_id=call_id,
        )

    show = cli_ai._StepPrinter()
    with console.capture() as captured:
        show(step(StepKind.STARTED, "a", "one.m4a"))
        show(step(StepKind.STARTED, "b", "two.m4a"))
        show(step(StepKind.RAN, "a", "one.m4a"))  # after b's lines
        show(step(StepKind.RAN, "a", "one.m4a"))  # right after its own

    lines = ANSI_ESCAPE.sub("", captured.get()).splitlines()
    assert sum("audio compress  one.m4a" in line for line in lines) == 1
    assert lines.index("  ⚙ audio compress  one.m4a") < lines.index(
        "      ✓ Compressed one.m4a"
    )


def test_a_queued_job_runs_in_the_background(
    dummy_video, monkeypatch, no_background_worker
) -> None:
    monkeypatch.chdir(dummy_video.parent)
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
                    "call-2",
                ),
            )
        ),
        _answer("Queued it."),
    )

    with patch(CLIENT_PATH, return_value=model):
        result = runner.invoke(ai_app, ["ask", "compress it in the background"])

    assert result.exit_code == 0, result.output
    assert len(no_background_worker) == 1
    output = _plain(result)
    assert "1 job running in the background" in output
    assert "max queue status" in output
    # The model heard where the user follows the job.
    system = model.requests[0]["messages"][0]["content"]
    assert "'max queue status'" in system


class TestMemoryCommand:
    def test_lists_forgets_and_clears_notes(self):
        from max_cli.core.agent.memory import AgentMemory

        kept = AgentMemory().remember("Music lives in D:/Music")
        gone = AgentMemory().remember("Use 128 kbps")

        listed = runner.invoke(ai_app, ["memory"])
        forgot = runner.invoke(ai_app, ["memory", "--forget", gone.id])
        cleared = runner.invoke(ai_app, ["memory", "--clear", "--force"])

        assert listed.exit_code == 0
        assert kept.id in _plain(listed)
        assert "Music lives in D:/Music" in _plain(listed)
        assert "Forgot: Use 128 kbps" in _plain(forgot)
        assert "Deleted 1 note." in _plain(cleared)
        assert AgentMemory().notes() == []

    def test_an_unknown_id_is_an_error(self):
        result = runner.invoke(ai_app, ["memory", "--forget", "nope"])

        assert "No note with id nope" in _plain(result)


class TestAnswersInTheTerminal:
    @pytest.mark.parametrize(
        ("typed", "answer"),
        [("", "go"), ("y", "go"), ("n", None), ("only mp3 files", "only mp3 files")],
    )
    def test_the_plan_question(self, monkeypatch, typed, answer):
        from max_cli.core.agent.agent import Question, QuestionKind

        monkeypatch.setattr(cli_ai.Prompt, "ask", lambda *args, **kwargs: typed)

        assert cli_ai._answer(Question(QuestionKind.PLAN, "1. a\n2. b")) == answer

    @pytest.mark.parametrize(("typed", "answer"), [("2", "Delete"), ("", None)])
    def test_a_question_takes_an_options_number(self, monkeypatch, typed, answer):
        from max_cli.core.agent.agent import Question, QuestionKind

        monkeypatch.setattr(cli_ai.Prompt, "ask", lambda *args, **kwargs: typed)
        question = Question(
            QuestionKind.QUESTION, "Move or delete?", ("Move", "Delete")
        )

        assert cli_ai._answer(question) == answer


class TestStopAndUndo:
    def test_the_first_ctrl_c_stops_the_agent_and_a_second_quits(self):
        import signal

        stopped = []
        agent = SimpleNamespace(stop=lambda: stopped.append(True))

        with cli_ai._stop_on_ctrl_c(agent):
            handler = signal.getsignal(signal.SIGINT)
            handler(signal.SIGINT, None)
            with pytest.raises(KeyboardInterrupt):
                handler(signal.SIGINT, None)

        assert stopped == [True]
        assert signal.getsignal(signal.SIGINT) is not handler

    def test_undo_puts_back_the_last_request(self, tmp_path):
        from max_cli.core.agent import changes

        made = tmp_path / "a.mp3"
        made.write_bytes(b"ID3")
        changes.save(
            changes.RequestChanges("convert", made=[changes.MadeFile.of(made)])
        )

        result = runner.invoke(ai_app, ["undo", "--force"])

        assert result.exit_code == 0, result.output
        assert "Moved 1 file it made" in _plain(result)
        assert not made.exists()

    def test_undo_with_nothing_recorded(self):
        result = runner.invoke(ai_app, ["undo"])

        assert "Nothing to undo" in _plain(result)
