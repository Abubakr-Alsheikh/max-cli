"""CliRunner tests for `max files` (src/max_cli/interface/cli_files.py).

TransactionLog and FileOrganizer backups resolve `Path.home()` on each call,
so the autouse `fake_home` fixture points it at tmp_path. Every destructive
command below touches only tmp_path.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console
from typer.testing import CliRunner

from max_cli.common import logger
from max_cli.common.exceptions import MaxError
from max_cli.interface import cli_files
from max_cli.interface.cli_files import app as files_app

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})

ORGANIZER_PATH = "max_cli.interface.cli_files._get_organizer"
AI_ENGINE_PATH = "max_cli.interface.cli_files._get_ai_engine"


@pytest.fixture(autouse=True)
def plain_console(monkeypatch):
    """Swap the shared Rich console for a wide, colorless one.

    The logger console is built at import time, so the runner's NO_COLOR and
    COLUMNS never reach it; without this it emits ANSI codes and wraps paths.
    """
    plain = Console(
        theme=logger.custom_theme,
        width=300,
        height=1000,
        color_system=None,
        force_terminal=False,
        legacy_windows=False,
    )
    monkeypatch.setattr(logger, "console", plain)
    monkeypatch.setattr(cli_files, "console", plain)


@pytest.fixture(autouse=True)
def fake_home(tmp_path, monkeypatch):
    """Keep transaction logs and backups out of the real ~/.max_cli."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


@pytest.fixture
def work_dir(tmp_path):
    folder = tmp_path / "work"
    folder.mkdir()
    return folder


def _backup_files(home: Path):
    backup_dir = home / ".max_cli" / "backups"
    if not backup_dir.exists():
        return []
    return [f for f in backup_dir.iterdir() if not f.name.endswith(".meta.json")]


def _make_duplicates(folder: Path):
    (folder / "a.txt").write_text("same", encoding="utf-8")
    (folder / "b.txt").write_text("same", encoding="utf-8")
    (folder / "c.txt").write_text("different", encoding="utf-8")


@pytest.mark.parametrize(
    "command",
    [
        None,
        "order",
        "smart-sort",
        "duplicates",
        "shred",
        "preview",
        "backup",
        "backups",
        "backup-cleanup",
        "undo",
        "history",
    ],
)
def test_help(command):
    args = [command, "--help"] if command else ["--help"]
    result = runner.invoke(files_app, args)
    assert result.exit_code == 0, result.output
    assert "Usage" in result.output


class TestOrder:
    def test_force_renames_and_undo_restores(self, work_dir, fake_home):
        (work_dir / "alpha.txt").write_text("a", encoding="utf-8")
        (work_dir / "beta.txt").write_text("b", encoding="utf-8")

        result = runner.invoke(files_app, ["order", str(work_dir), "--force"])

        assert result.exit_code == 0, result.output
        assert "Files Processed: 2" in result.output
        assert sorted(p.name for p in work_dir.iterdir()) == [
            "1_alpha.txt",
            "2_beta.txt",
        ]
        assert list((fake_home / ".max_cli" / "transactions").glob("*.json"))

        history = runner.invoke(files_app, ["history"])
        assert history.exit_code == 0, history.output
        assert "files order" in history.output
        assert "Operations: 2" in history.output

        undo = runner.invoke(files_app, ["undo"])
        assert undo.exit_code == 0, undo.output
        assert "Undo complete!" in undo.output
        assert sorted(p.name for p in work_dir.iterdir()) == [
            "alpha.txt",
            "beta.txt",
        ]

    def test_skips_numbered_files_and_honors_start(self, work_dir):
        (work_dir / "1_done.txt").write_text("a", encoding="utf-8")
        (work_dir / "new.txt").write_text("b", encoding="utf-8")

        result = runner.invoke(
            files_app, ["order", str(work_dir), "--force", "--start", "5"]
        )

        assert result.exit_code == 0, result.output
        assert "Files Skipped:   1" in result.output
        assert (work_dir / "5_new.txt").exists()

    def test_dry_run_changes_nothing(self, work_dir):
        (work_dir / "alpha.txt").write_text("a", encoding="utf-8")

        result = runner.invoke(files_app, ["order", str(work_dir), "--dry-run"])

        assert result.exit_code == 0, result.output
        assert "Would rename 'alpha.txt' -> '1_alpha.txt'" in result.output
        assert "This was a Dry Run" in result.output
        assert (work_dir / "alpha.txt").exists()

    def test_declined_prompt_aborts(self, work_dir):
        (work_dir / "alpha.txt").write_text("a", encoding="utf-8")

        result = runner.invoke(files_app, ["order", str(work_dir)], input="n\n")

        assert result.exit_code == 0, result.output
        assert "Aborted." in result.output
        assert (work_dir / "alpha.txt").exists()

    def test_empty_folder(self, work_dir):
        result = runner.invoke(files_app, ["order", str(work_dir), "--force"])
        assert result.exit_code == 0, result.output
        assert "Folder is empty" in result.output

    def test_not_a_directory_fails(self, tmp_path):
        result = runner.invoke(files_app, ["order", str(tmp_path / "missing")])
        assert result.exit_code == 1
        assert "is not a directory" in result.output

    @patch(ORGANIZER_PATH)
    def test_organizer_error_exits_1(self, mock_get_organizer, work_dir):
        mock_get_organizer.return_value.scan_directory.side_effect = MaxError(
            "permission denied"
        )

        result = runner.invoke(files_app, ["order", str(work_dir), "--force"])

        assert result.exit_code == 1
        assert "Error: permission denied" in result.output
        assert "Traceback" not in result.output


class TestSmartSort:
    @patch(AI_ENGINE_PATH)
    def test_moves_files_into_ai_categories(self, mock_get_ai, work_dir):
        (work_dir / "invoice.pdf").write_text("pdf", encoding="utf-8")
        (work_dir / "cat.jpg").write_text("jpg", encoding="utf-8")
        mock_get_ai.return_value.categorize_files.return_value = {
            "invoice.pdf": "Finance",
            "cat.jpg": "Pictures",
        }

        result = runner.invoke(files_app, ["smart-sort", str(work_dir)])

        assert result.exit_code == 0, result.output
        assert "Successfully organized 2 files." in result.output
        assert (work_dir / "Finance" / "invoice.pdf").exists()
        assert (work_dir / "Pictures" / "cat.jpg").exists()

    @patch(AI_ENGINE_PATH)
    def test_dry_run_moves_nothing(self, mock_get_ai, work_dir):
        (work_dir / "invoice.pdf").write_text("pdf", encoding="utf-8")
        mock_get_ai.return_value.categorize_files.return_value = {
            "invoice.pdf": "Finance"
        }

        result = runner.invoke(files_app, ["smart-sort", str(work_dir), "--dry-run"])

        assert result.exit_code == 0, result.output
        assert "Dry run complete" in result.output
        assert (work_dir / "invoice.pdf").exists()

    @patch(AI_ENGINE_PATH)
    def test_empty_folder_skips_ai(self, mock_get_ai, work_dir):
        result = runner.invoke(files_app, ["smart-sort", str(work_dir)])

        assert result.exit_code == 0, result.output
        assert "No files to organize." in result.output
        mock_get_ai.assert_not_called()


class TestDuplicates:
    def test_reports_duplicates_without_deleting(self, work_dir):
        _make_duplicates(work_dir)

        result = runner.invoke(files_app, ["duplicates", str(work_dir)])

        assert result.exit_code == 0, result.output
        assert "Found 1 duplicate(s) in 1 group(s)" in result.output
        assert "Run with --delete" in result.output
        assert len(list(work_dir.iterdir())) == 3

    def test_delete_keeps_one_copy_and_backs_up(self, work_dir, fake_home):
        _make_duplicates(work_dir)

        result = runner.invoke(files_app, ["duplicates", str(work_dir), "--delete"])

        assert result.exit_code == 0, result.output
        assert "Removed 1 duplicate(s)." in result.output
        assert sorted(p.name for p in work_dir.iterdir()) == ["a.txt", "c.txt"]
        assert len(_backup_files(fake_home)) == 1

    def test_no_duplicates(self, work_dir):
        (work_dir / "only.txt").write_text("x", encoding="utf-8")
        result = runner.invoke(files_app, ["duplicates", str(work_dir)])
        assert result.exit_code == 0, result.output
        assert "No duplicates found!" in result.output

    @pytest.mark.xfail(
        strict=True,
        reason="cli_files.find_duplicates deletes on --delete with no "
        "Confirm.ask prompt and no --force flag, which AGENTS.md section 14 "
        "requires for destructive commands",
    )
    def test_delete_asks_for_confirmation(self, work_dir):
        _make_duplicates(work_dir)

        runner.invoke(files_app, ["duplicates", str(work_dir), "--delete"], input="n\n")

        assert (work_dir / "b.txt").exists()

    @patch(ORGANIZER_PATH)
    def test_organizer_error_is_reported(self, mock_get_organizer, work_dir):
        mock_get_organizer.return_value.find_duplicates.side_effect = MaxError(
            "unreadable"
        )

        result = runner.invoke(files_app, ["duplicates", str(work_dir)])

        assert result.exception is None
        assert result.exit_code == 0
        assert "Error finding duplicates: unreadable" in result.output


class TestShred:
    def test_force_deletes_and_backs_up(self, work_dir, fake_home):
        secret = work_dir / "secret.txt"
        secret.write_text("top secret", encoding="utf-8")

        result = runner.invoke(files_app, ["shred", str(secret), "--force"])

        assert result.exit_code == 0, result.output
        assert "File securely deleted: secret.txt" in result.output
        assert not secret.exists()
        [backup] = _backup_files(fake_home)
        assert backup.read_text(encoding="utf-8") == "top secret"

    def test_declined_prompt_keeps_file(self, work_dir):
        secret = work_dir / "secret.txt"
        secret.write_text("top secret", encoding="utf-8")

        result = runner.invoke(files_app, ["shred", str(secret)], input="n\n")

        assert result.exit_code == 0, result.output
        assert "Aborted." in result.output
        assert secret.exists()

    def test_missing_file_fails(self, work_dir):
        result = runner.invoke(files_app, ["shred", str(work_dir / "nope.txt")])
        assert result.exit_code == 1
        assert "File not found" in result.output

    def test_directory_is_refused(self, work_dir):
        result = runner.invoke(files_app, ["shred", str(work_dir), "--force"])
        assert result.exit_code == 1
        assert "Cannot shred directories" in result.output
        assert work_dir.exists()

    @patch(ORGANIZER_PATH)
    def test_organizer_error_is_reported(self, mock_get_organizer, work_dir):
        secret = work_dir / "secret.txt"
        secret.write_text("top secret", encoding="utf-8")
        mock_get_organizer.return_value.secure_delete.side_effect = MaxError("locked")

        result = runner.invoke(files_app, ["shred", str(secret), "--force"])

        assert result.exception is None
        assert "Secure delete failed: locked" in result.output
        assert secret.exists()


class TestPreview:
    def test_text_file_shows_lines(self, work_dir):
        notes = work_dir / "notes.txt"
        notes.write_text("line one\nline two\nline three\n", encoding="utf-8")

        result = runner.invoke(files_app, ["preview", str(notes), "-n", "2"])

        assert result.exit_code == 0, result.output
        assert "1: line one" in result.output
        assert "2: line two" in result.output
        assert "... and 1 more lines" in result.output

    def test_missing_file_fails(self, work_dir):
        result = runner.invoke(files_app, ["preview", str(work_dir / "nope.txt")])
        assert result.exit_code == 1
        assert "File not found" in result.output


class TestBackups:
    def test_backup_then_list(self, work_dir, fake_home):
        report = work_dir / "report.txt"
        report.write_text("v1", encoding="utf-8")

        backup = runner.invoke(files_app, ["backup", str(report), "-l", "before"])
        assert backup.exit_code == 0, backup.output
        assert "Backup created:" in backup.output
        [backup_path] = _backup_files(fake_home)
        assert backup_path.name.startswith("report_before_")

        listing = runner.invoke(files_app, ["backups"])
        assert listing.exit_code == 0, listing.output
        assert "Found 1 backup(s)" in listing.output
        assert backup_path.name in listing.output

    def test_empty_backup_list(self):
        result = runner.invoke(files_app, ["backups"])
        assert result.exit_code == 0, result.output
        assert "No backups found." in result.output

    @patch(ORGANIZER_PATH)
    def test_backup_error_is_reported(self, mock_get_organizer, work_dir):
        report = work_dir / "report.txt"
        report.write_text("v1", encoding="utf-8")
        mock_get_organizer.return_value.create_backup.side_effect = MaxError(
            "disk full"
        )

        result = runner.invoke(files_app, ["backup", str(report)])

        assert result.exception is None
        assert "Backup failed: disk full" in result.output

    @patch(ORGANIZER_PATH)
    def test_cleanup_force(self, mock_get_organizer):
        organizer = MagicMock()
        organizer.cleanup_old_backups.return_value = 2
        mock_get_organizer.return_value = organizer

        result = runner.invoke(files_app, ["backup-cleanup", "--force", "-d", "7"])

        assert result.exit_code == 0, result.output
        organizer.cleanup_old_backups.assert_called_once_with(7)
        assert "Removed 2 old backup(s)" in result.output

    @patch(ORGANIZER_PATH)
    def test_cleanup_declined(self, mock_get_organizer):
        result = runner.invoke(files_app, ["backup-cleanup"], input="n\n")

        assert result.exit_code == 0, result.output
        assert "Aborted." in result.output
        mock_get_organizer.assert_not_called()


class TestUndoAndHistory:
    def test_undo_without_history(self):
        result = runner.invoke(files_app, ["undo"])
        assert result.exit_code == 0, result.output
        assert "Nothing to undo." in result.output

    def test_history_without_entries(self):
        result = runner.invoke(files_app, ["history"])
        assert result.exit_code == 0, result.output
        assert "No transaction history found." in result.output
