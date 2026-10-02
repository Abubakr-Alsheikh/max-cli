"""core/operations/files.py: every change is undoable, and nothing asks or prints.

The autouse isolated_home fixture keeps transaction logs and backups in a
temp home.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from max_cli.common.exceptions import ResourceNotFoundError, ValidationError
from max_cli.core.operations import files


@pytest.fixture
def work_dir(tmp_path) -> Path:
    folder = tmp_path / "work"
    folder.mkdir()
    return folder


def _names(folder: Path) -> list[str]:
    return sorted(path.name for path in folder.iterdir())


class TestOrderAndUndo:
    def test_order_records_an_undo_group_that_undo_reverses(self, work_dir):
        (work_dir / "alpha.txt").write_text("a", encoding="utf-8")
        (work_dir / "beta.txt").write_text("b", encoding="utf-8")

        result = files.order(work_dir)

        assert result.details["renamed"] == 2
        assert result.undo_group
        assert _names(work_dir) == ["1_alpha.txt", "2_beta.txt"]

        undone = files.undo()

        assert undone.undo_group == result.undo_group
        assert len(undone.details["steps"]) == 2
        assert _names(work_dir) == ["alpha.txt", "beta.txt"]
        assert "already undone" in files.undo().message

    def test_undo_again_steps_back_to_the_change_before(self, work_dir):
        """A second undo said "already undone" and stopped there."""
        (work_dir / "alpha.txt").write_text("a", encoding="utf-8")
        first = files.order(work_dir)
        (work_dir / "beta.txt").write_text("b", encoding="utf-8")
        second = files.order(work_dir)

        assert files.undo().undo_group == second.undo_group
        assert _names(work_dir) == ["1_alpha.txt", "beta.txt"]
        assert files.undo().undo_group == first.undo_group
        assert _names(work_dir) == ["alpha.txt", "beta.txt"]
        assert "already undone" in files.undo().message

    def test_dry_run_changes_nothing_and_records_nothing(self, work_dir):
        (work_dir / "alpha.txt").write_text("a", encoding="utf-8")

        result = files.order(work_dir, dry_run=True)

        assert result.undo_group is None
        assert _names(work_dir) == ["alpha.txt"]
        assert files.history().details["groups"] == []

    def test_not_a_folder(self, tmp_path):
        with pytest.raises(ValidationError, match="is not a directory"):
            files.order(tmp_path / "missing")

    def test_nothing_to_undo(self):
        assert files.undo().message.endswith("Nothing to undo.")


class TestSmartSort:
    def test_moves_files_into_the_ai_categories(self, work_dir):
        (work_dir / "invoice.pdf").write_bytes(b"%PDF")
        (work_dir / ".hidden").write_text("x", encoding="utf-8")
        ai_engine = MagicMock()
        ai_engine.categorize_files.return_value = {"invoice.pdf": "Finance"}

        result = files.smart_sort(work_dir, ai_engine=ai_engine)

        ai_engine.categorize_files.assert_called_once_with(["invoice.pdf"])
        assert (work_dir / "Finance" / "invoice.pdf").exists()
        assert result.undo_group and result.details["moved"] == 1

    def test_empty_folder_never_calls_the_ai(self, work_dir):
        ai_engine = MagicMock()

        result = files.smart_sort(work_dir, ai_engine=ai_engine)

        assert result.message == "No files to organize."
        ai_engine.categorize_files.assert_not_called()


class TestDuplicates:
    @pytest.fixture
    def copies(self, work_dir) -> Path:
        for name, text in [("a.txt", "same"), ("b.txt", "same"), ("c.txt", "other")]:
            (work_dir / name).write_text(text, encoding="utf-8")
        return work_dir

    def test_scan_only_deletes_nothing(self, copies):
        result = files.duplicates(copies)

        assert result.details["duplicate_count"] == 1
        assert result.undo_group is None
        assert len(_names(copies)) == 3

    def test_delete_uses_the_given_scan_and_can_be_undone(self, copies):
        groups = files.find_duplicates(copies)
        organizer = MagicMock(wraps=files._organizer(None))

        result = files.duplicates(
            copies, delete=True, organizer=organizer, groups=groups
        )

        organizer.find_duplicates.assert_not_called()
        assert result.details["removed"] == 1
        assert len(_names(copies)) == 2

        files.undo()

        assert len(_names(copies)) == 3


class TestShred:
    def test_checks_come_before_anything_else(self, work_dir):
        with pytest.raises(ValidationError, match="Cannot shred directories"):
            files.check_shred_target(work_dir)
        with pytest.raises(ResourceNotFoundError):
            files.shred(work_dir / "gone.txt")

    def test_needs_at_least_one_pass(self, work_dir):
        secret = work_dir / "secret.txt"
        secret.write_text("x", encoding="utf-8")

        with pytest.raises(ValidationError, match="Passes"):
            files.shred(secret, passes=0)
        assert secret.exists()

    def test_leaves_no_backup_and_no_undo_record(self, work_dir):
        secret = work_dir / "secret.txt"
        secret.write_text("x", encoding="utf-8")

        result = files.shred(secret, passes=1)

        assert not secret.exists()
        assert result.undo_group is None
        assert files.history().details["groups"] == []
        assert files.backups().details["backups"] == []


class TestPreview:
    def test_text_lines(self, work_dir):
        notes = work_dir / "notes.txt"
        notes.write_text("one\ntwo\nthree\n", encoding="utf-8")

        details = files.preview(notes, lines=2).details

        assert details["lines"] == ["one", "two"] and details["more_lines"] == 1

    def test_image_size(self, work_dir):
        photo = work_dir / "photo.png"
        Image.new("RGB", (30, 20)).save(photo)

        assert files.preview(photo).details["image"]["width"] == 30

    def test_unknown_type(self, work_dir):
        blob = work_dir / "data.bin"
        blob.write_bytes(b"\x00")

        assert "not available" in files.preview(blob).details["note"]


class TestBackups:
    def test_backup_list_restore(self, work_dir):
        report = work_dir / "report.txt"
        report.write_text("v1", encoding="utf-8")

        [backup_path] = files.backup(report, label="before").output_files
        listed = files.backups(filter="report").details["backups"]
        report.write_text("v2", encoding="utf-8")
        restore_dir = work_dir / "restored"
        restore_dir.mkdir()
        restored = files.backups(restore=backup_path, output=restore_dir)

        assert [entry["name"] for entry in listed] == [backup_path.name]
        assert restored.output_files[0].read_text(encoding="utf-8") == "v1"

    def test_cleanup_rejects_negative_days(self):
        with pytest.raises(ValidationError):
            files.backup_cleanup(days=-1)


def test_history_verbose_lists_each_step(work_dir):
    (work_dir / "alpha.txt").write_text("a", encoding="utf-8")
    files.order(work_dir)

    [group] = files.history(verbose=True).details["groups"]

    assert group["command"] == "files order"
    assert group["operations"][0]["op_type"]
