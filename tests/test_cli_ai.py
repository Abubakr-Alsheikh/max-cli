"""CliRunner tests for `max ai` (src/max_cli/interface/cli_ai.py).

Every test replaces `_get_engine` with a MagicMock, so no AI client, network
call or history file under the home folder is touched.
"""

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from max_cli.common.exceptions import MaxError
from max_cli.interface import cli_ai
from max_cli.interface.cli_ai import app as ai_app

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})

ENGINE_PATH = "max_cli.interface.cli_ai._get_engine"
DOWNLOAD_PATH = "max_cli.core.engines.ai_engine.download_image"

# The shared Rich console is built at import time, so it may still emit ANSI
# styles inside CliRunner. Strip them before substring checks.
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

VISIBLE_COMMANDS = ["ask", "analyze", "create", "edit", "chat", "search", "extract"]
HIDDEN_ALIASES = ["a", "ana", "c", "ch", "s"]


def _plain(result) -> str:
    return ANSI_ESCAPE.sub("", result.output)


@pytest.fixture
def main_app_ref(monkeypatch):
    """`ask` refuses to run until the root app registers itself."""
    root_app = typer.Typer()
    monkeypatch.setattr(cli_ai, "MAIN_APP_REF", root_app)
    return root_app


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
    def test_without_main_app_ref_exits_1(self, monkeypatch) -> None:
        monkeypatch.setattr(cli_ai, "MAIN_APP_REF", None)
        result = runner.invoke(ai_app, ["ask", "list files"])

        assert result.exit_code == 1
        assert "Main App reference not linked" in _plain(result)

    def test_confirmed_suggestion_runs_command(self, main_app_ref) -> None:
        engine = MagicMock()
        engine.interpret_intent.return_value = {
            "command": 'max images compress "my photo.jpg"',
            "thought": "Shrink the photo",
            "dangerous": False,
        }
        with (
            patch(ENGINE_PATH, return_value=engine),
            patch.object(cli_ai.Confirm, "ask", return_value=True),
            patch.object(cli_ai.subprocess, "run") as run_mock,
        ):
            result = runner.invoke(ai_app, ["ask", "compress my photo"])

        assert result.exit_code == 0, result.output
        engine.interpret_intent.assert_called_once_with(
            "compress my photo", main_app_ref
        )
        run_mock.assert_called_once_with(
            ["max", "images", "compress", "my photo.jpg"], check=True
        )
        output = _plain(result)
        assert "Max Suggests" in output
        assert "Shrink the photo" in output

    def test_declined_suggestion_is_aborted(self, main_app_ref) -> None:
        engine = MagicMock()
        engine.interpret_intent.return_value = {
            "command": "max files shred secret.txt",
            "thought": "Delete it",
            "dangerous": True,
            "explanation": "Overwrites then deletes the file.",
        }
        with (
            patch(ENGINE_PATH, return_value=engine),
            patch.object(cli_ai.Confirm, "ask", return_value=False),
            patch.object(cli_ai.subprocess, "run") as run_mock,
        ):
            result = runner.invoke(ai_app, ["ask", "delete secret", "--explain"])

        assert result.exit_code == 0, result.output
        run_mock.assert_not_called()
        output = _plain(result)
        assert "Overwrites then deletes the file." in output
        assert "Aborted." in output

    def test_ai_rejection_shows_error_panel(self, main_app_ref) -> None:
        engine = MagicMock()
        engine.interpret_intent.return_value = {"error": "I cannot do that."}
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(ai_app, ["ask", "hack the planet"])

        assert result.exit_code == 0
        assert "I cannot do that." in _plain(result)

    def test_engine_error_exits_1(self, main_app_ref) -> None:
        engine = MagicMock()
        engine.interpret_intent.side_effect = MaxError("AI Client not configured.")
        with patch(ENGINE_PATH, return_value=engine):
            result = runner.invoke(ai_app, ["ask", "anything"])

        assert result.exit_code == 1
        assert not isinstance(result.exception, MaxError)
        assert "AI Client not configured." in _plain(result)


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
        engine.generate_image.assert_called_once_with(
            "a cat", model="gemini-2.5-flash-image"
        )
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
        assert "Could not auto-download: disk full" in _plain(result)

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

    def test_interactive_session_answers_then_exits(self, main_app_ref) -> None:
        engine = MagicMock()
        engine.history = []
        engine.get_suggestions.return_value = ["compress photos"]
        engine.interpret_intent.return_value = {"thought": "Hello there!"}
        with (
            patch(ENGINE_PATH, return_value=engine),
            patch.object(cli_ai.Prompt, "ask", side_effect=["compress photos", "exit"]),
        ):
            result = runner.invoke(ai_app, ["chat"])

        assert result.exit_code == 0, result.output
        engine.interpret_intent.assert_called_once_with("compress photos", main_app_ref)
        output = _plain(result)
        assert "Max: Hello there!" in output
        assert "Goodbye!" in output

    def test_interactive_engine_error_is_reported(self, main_app_ref) -> None:
        engine = MagicMock()
        engine.history = []
        engine.get_suggestions.return_value = ["compress photos"]
        engine.interpret_intent.side_effect = MaxError("rate limited")
        with (
            patch(ENGINE_PATH, return_value=engine),
            patch.object(cli_ai.Prompt, "ask", side_effect=["compress photos", "quit"]),
        ):
            result = runner.invoke(ai_app, ["chat"])

        assert result.exit_code == 0
        assert result.exception is None
        output = _plain(result)
        assert "rate limited" in output
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

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "cli_ai.extract_data_cmd declares --schema as `str` and loops "
            "`for s in schema`, so it walks characters: 'total:Total amount' "
            "becomes {'t': '', 'o': '', ..., '': ''} instead of "
            "{'total': 'Total amount'}; repeated -s flags also keep only the last."
        ),
    )
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
