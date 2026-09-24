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
