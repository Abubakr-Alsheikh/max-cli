"""Several files, a folder or a pattern on one-file commands (interface/batch_cli)."""

from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from max_cli.common import logger
from max_cli.core.catalog import runner as catalog_runner
from max_cli.core.engines.task_manager import get_task_manager
from max_cli.core.operations.result import ActionResult
from max_cli.interface import batch_cli
from max_cli.interface.cli_audio import app as audio_app
from max_cli.interface.cli_media import app as media_app

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})


@pytest.fixture(autouse=True)
def plain_console(monkeypatch):
    plain = Console(width=300, color_system=None, force_terminal=False)
    for module in (logger, batch_cli):
        monkeypatch.setattr(module, "console", plain)


@pytest.fixture
def ran(monkeypatch) -> list[str]:
    """Each file's run, without FFmpeg; bad*.m4a fails."""
    names: list[str] = []

    def fake(action, args, **kwargs):
        target = Path(args["target"])
        names.append(target.name)
        if target.name.startswith("bad"):
            return ActionResult(False, "unreadable file")
        return ActionResult(True, "ok", [target.with_suffix(".mp3")])

    monkeypatch.setattr(catalog_runner, "run_action", fake)
    monkeypatch.setattr("max_cli.interface.cli_media._get_engine", lambda: None)
    return names


def _music(folder: Path) -> Path:
    for name in ("a.m4a", "b.m4a", "c.m4a", "c.mp3", "notes.txt"):
        (folder / name).write_bytes(b"\0")
    return folder


def test_a_folder_converts_only_what_is_left(tmp_path, ran):
    result = runner.invoke(media_app, ["audio-convert", str(_music(tmp_path))])

    assert result.exit_code == 0, result.output
    assert sorted(ran) == ["a.m4a", "b.m4a"]
    assert "1 file had their result already; --redo runs them again." in result.output
    assert "2 of 3 files done, 1 had their result already." in result.output


def test_redo_converts_them_all(tmp_path, ran):
    result = runner.invoke(
        media_app, ["audio-convert", str(_music(tmp_path)), "--redo"]
    )

    assert result.exit_code == 0, result.output
    assert sorted(ran) == ["a.m4a", "b.m4a", "c.m4a"]


def test_a_pattern_picks_the_files(tmp_path, ran):
    _music(tmp_path)

    result = runner.invoke(media_app, ["audio-convert", str(tmp_path / "a*.m4a")])

    assert result.exit_code == 0, result.output
    assert ran == ["a.m4a"]


def test_a_failed_file_is_named_and_the_command_fails(tmp_path, ran):
    _music(tmp_path)
    (tmp_path / "bad.m4a").write_bytes(b"\0")

    result = runner.invoke(media_app, ["audio-convert", str(tmp_path)])

    assert result.exit_code == 1
    assert "bad.m4a: unreadable file" in result.output


def test_queue_puts_each_file_in_the_background(tmp_path, ran, no_background_worker):
    result = runner.invoke(
        media_app, ["audio-convert", str(_music(tmp_path)), "--queue"]
    )

    assert result.exit_code == 0, result.output
    assert ran == []
    targets = [
        Path(t.payload["args"]["target"]).name for t in get_task_manager().get_all()
    ]
    assert sorted(targets) == ["a.m4a", "b.m4a"]
    assert "Queued 2 jobs." in result.output
    assert len(no_background_worker) == 1


def test_changing_files_in_place_asks_once(tmp_path, ran):
    _music(tmp_path)

    result = runner.invoke(audio_app, ["clear", str(tmp_path)], input="n\n")

    assert "audio clear changes 4 files in place." in result.output
    assert "Cancelled." in result.output
    assert ran == []
