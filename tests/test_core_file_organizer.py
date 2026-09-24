import pytest
from pathlib import Path
from max_cli.core.engines.file_organizer import FileOrganizer
from max_cli.common.exceptions import ResourceNotFoundError


class TestFileOrganizer:
    """Tests for file organization operations."""

    def test_scan_directory(self, sample_directory):
        """Test scanning a directory for files."""
        engine = FileOrganizer()
        files = engine.scan_directory(sample_directory)

        assert len(files) == 4
        assert all(f.is_file() for f in files)

    def test_scan_directory_nonexistent(self):
        """Test scanning a nonexistent directory."""
        engine = FileOrganizer()

        with pytest.raises(ResourceNotFoundError):
            engine.scan_directory(Path("/nonexistent/path"))

    def test_scan_directory_single_file(self, tmp_path):
        """Test scanning directory with single file."""
        file_path = tmp_path / "single.txt"
        file_path.write_text("content")

        engine = FileOrganizer()
        files = engine.scan_directory(tmp_path)

        assert len(files) == 1
        assert files[0].name == "single.txt"

    def test_order_files_dry_run(self, sample_directory):
        """Test ordering files in dry run mode."""
        engine = FileOrganizer()
        result = engine.order_files(sample_directory, dry_run=True)

        assert result["total_files"] == 4
        assert result["renamed"] == 4
        assert result["skipped"] == 0
        assert len(result["actions"]) == 4

    def test_order_files_actual(self, tmp_path):
        """Test actual file ordering."""
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")

        engine = FileOrganizer()
        result = engine.order_files(tmp_path, dry_run=False, start_index=1)

        assert result["renamed"] == 2

        files = list(tmp_path.iterdir())
        names = [f.name for f in files]

        assert "1_a.txt" in names
        assert "2_b.txt" in names

    def test_order_files_already_numbered(self, tmp_path):
        """Test ordering skips already numbered files."""
        (tmp_path / "1_already.txt").write_text("content")
        (tmp_path / "new.txt").write_text("content")

        engine = FileOrganizer()
        result = engine.order_files(tmp_path, dry_run=False)

        assert result["skipped"] == 1
        assert result["renamed"] == 1

    def test_order_files_custom_start_index(self, tmp_path):
        """Test ordering with custom start index."""
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")

        engine = FileOrganizer()
        engine.order_files(tmp_path, dry_run=False, start_index=10)

        files = list(tmp_path.iterdir())
        names = [f.name for f in files]

        assert "10_a.txt" in names
        assert "11_b.txt" in names

    def test_scan_directory_excludes_subdirs(self, tmp_path):
        """Test that subdirectories are excluded."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file.txt").write_text("content")

        (tmp_path / "root_file.txt").write_text("content")

        engine = FileOrganizer()
        files = engine.scan_directory(tmp_path)

        assert len(files) == 1
        assert files[0].name == "root_file.txt"

    def test_order_files_error_handling(self, tmp_path):
        """Test error handling during rename."""
        (tmp_path / "file.txt").write_text("content")

        engine = FileOrganizer()

        result = engine.order_files(tmp_path, dry_run=False)

        assert result["renamed"] == 1
        assert len(result["actions"]) == 1


class TestSmartSortValidation:
    """AI-supplied names must never move files outside the target (hardening 1.6)."""

    @pytest.fixture
    def folder(self, tmp_path):
        target = tmp_path / "inbox"
        target.mkdir()
        (target / "report.pdf").write_text("pdf", encoding="utf-8")
        return target

    def test_valid_category_moves_file(self, folder):
        result = FileOrganizer().smart_sort(folder, {"report.pdf": "Documents"})

        assert result["moved"] == 1
        assert (folder / "Documents" / "report.pdf").exists()

    @pytest.mark.parametrize(
        "category",
        ["../escaped", "..", ".", "a/b", "a\\b", "", "   "],
    )
    def test_path_like_category_is_rejected(self, folder, category):
        result = FileOrganizer().smart_sort(folder, {"report.pdf": category})

        assert result["moved"] == 0
        assert result["errors"] == 1
        assert (folder / "report.pdf").exists()
        assert not (folder.parent / "escaped").exists()

    def test_absolute_category_is_rejected(self, folder, tmp_path):
        outside = tmp_path / "outside"

        result = FileOrganizer().smart_sort(folder, {"report.pdf": str(outside)})

        assert result["moved"] == 0
        assert not outside.exists()
        assert (folder / "report.pdf").exists()

    def test_path_like_filename_is_rejected(self, folder, tmp_path):
        secret = tmp_path / "secret.txt"
        secret.write_text("keep me here", encoding="utf-8")

        result = FileOrganizer().smart_sort(folder, {"../secret.txt": "Loot"})

        assert result["moved"] == 0
        assert secret.exists()
        assert not (folder / "Loot").exists()

    @pytest.mark.parametrize("bad_value", [None, 123, ["Docs"], {"x": "y"}])
    def test_non_string_values_are_rejected(self, folder, bad_value):
        result = FileOrganizer().smart_sort(folder, {"report.pdf": bad_value})

        assert result["moved"] == 0
        assert result["errors"] == 1

    def test_category_differing_only_in_case_is_accepted(self, folder):
        (folder / "Documents").mkdir()

        result = FileOrganizer().smart_sort(folder, {"report.pdf": "documents"})

        assert result["moved"] == 1
        assert result["errors"] == 0

    def test_existing_destination_is_not_overwritten(self, folder):
        (folder / "Documents").mkdir()
        existing = folder / "Documents" / "report.pdf"
        existing.write_text("older copy", encoding="utf-8")

        result = FileOrganizer().smart_sort(folder, {"report.pdf": "Documents"})

        assert result["skipped"] == 1
        assert existing.read_text(encoding="utf-8") == "older copy"
        assert (folder / "report.pdf").exists()


class TestSecureDelete:
    """Regression tests for secure_delete (hardening 1.1)."""

    SECRET = b"TOP-SECRET-PAYLOAD-" * 512

    def test_overwrites_original_bytes_in_place(self, tmp_path, monkeypatch):
        target = tmp_path / "secret.bin"
        target.write_bytes(self.SECRET)
        # Keep the file after the overwrite so we can inspect what remains on disk.
        monkeypatch.setattr(Path, "unlink", lambda self, missing_ok=False: None)

        FileOrganizer().secure_delete(target, passes=2, auto_backup=False)

        remaining = target.read_bytes()
        assert b"TOP-SECRET-PAYLOAD-" not in remaining
        assert len(remaining) == len(self.SECRET)

    def test_file_is_removed(self, tmp_path):
        target = tmp_path / "secret.bin"
        target.write_bytes(self.SECRET)

        assert FileOrganizer().secure_delete(target, auto_backup=False) is True
        assert not target.exists()

    def test_empty_file_is_removed(self, tmp_path):
        target = tmp_path / "empty.bin"
        target.write_bytes(b"")

        assert FileOrganizer().secure_delete(target, auto_backup=False) is True
        assert not target.exists()
