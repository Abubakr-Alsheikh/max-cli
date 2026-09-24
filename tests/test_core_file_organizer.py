import pytest
from pathlib import Path
from max_cli.core.engines import file_organizer as file_organizer_module
from max_cli.core.engines.file_organizer import FileOrganizer
from max_cli.common.exceptions import ResourceNotFoundError, ValidationError


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


class TestFindDuplicates:
    """Chunked hashing, size pre-grouping (hardening 1.10)."""

    def test_groups_identical_files(self, tmp_path):
        (tmp_path / "a.txt").write_bytes(b"same content")
        (tmp_path / "b.txt").write_bytes(b"same content")
        (tmp_path / "c.txt").write_bytes(b"different!!!")  # same size, other bytes

        groups = FileOrganizer().find_duplicates(tmp_path)

        assert [sorted(p.name for p in paths) for paths in groups.values()] == [
            ["a.txt", "b.txt"]
        ]

    def test_files_with_unique_sizes_are_never_hashed(self, tmp_path, monkeypatch):
        (tmp_path / "a.txt").write_bytes(b"dup")
        (tmp_path / "b.txt").write_bytes(b"dup")
        (tmp_path / "unique.bin").write_bytes(b"x" * 100)
        hashed = []
        original_digest = file_organizer_module._file_digest

        def spy(path):
            hashed.append(path.name)
            return original_digest(path)

        monkeypatch.setattr(file_organizer_module, "_file_digest", spy)

        FileOrganizer().find_duplicates(tmp_path)

        assert sorted(hashed) == ["a.txt", "b.txt"]

    def test_digest_reads_in_chunks(self, tmp_path, monkeypatch):
        import hashlib

        payload = bytes(range(256)) * 40
        target = tmp_path / "big.bin"
        target.write_bytes(payload)
        monkeypatch.setattr(file_organizer_module, "HASH_CHUNK_BYTES", 7)

        digest = file_organizer_module._file_digest(target)

        assert digest == hashlib.sha256(payload).hexdigest()

    def test_unreadable_file_is_skipped(self, tmp_path, monkeypatch):
        (tmp_path / "a.txt").write_bytes(b"dup")
        (tmp_path / "b.txt").write_bytes(b"dup")

        def failing_digest(path):
            raise PermissionError("locked")

        monkeypatch.setattr(file_organizer_module, "_file_digest", failing_digest)

        assert FileOrganizer().find_duplicates(tmp_path) == {}


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


class TestBackupRestore:
    """Restore goes back to the original location (hardening 1.13)."""

    @pytest.fixture
    def organizer(self, tmp_path, monkeypatch):
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        monkeypatch.setattr(FileOrganizer, "get_backup_dir", lambda self: backup_dir)
        return FileOrganizer()

    @pytest.fixture
    def original(self, tmp_path):
        folder = tmp_path / "work"
        folder.mkdir()
        path = folder / "report.txt"
        path.write_text("v1", encoding="utf-8")
        return path

    def test_restore_without_target_returns_file_to_original_path(
        self, organizer, original
    ):
        backup = organizer.create_backup(original)
        original.unlink()

        restored = organizer.restore_backup(backup)

        assert restored == original.resolve()
        assert original.read_text(encoding="utf-8") == "v1"

    def test_restore_refuses_to_overwrite_existing_original(self, organizer, original):
        backup = organizer.create_backup(original)
        original.write_text("v2 edited later", encoding="utf-8")

        with pytest.raises(ValidationError):
            organizer.restore_backup(backup)

        assert original.read_text(encoding="utf-8") == "v2 edited later"

    def test_restore_to_target_dir_uses_original_name(
        self, organizer, original, tmp_path
    ):
        backup = organizer.create_backup(original)
        target = tmp_path / "restored"

        restored = organizer.restore_backup(backup, target)

        assert restored == target / "report.txt"
        assert restored.read_text(encoding="utf-8") == "v1"

    def test_legacy_backup_without_metadata_requires_target(self, organizer, tmp_path):
        legacy = organizer.get_backup_dir() / "old_manual_20250101_000000.txt"
        legacy.write_text("old", encoding="utf-8")

        with pytest.raises(ValidationError):
            organizer.restore_backup(legacy)

        restored = organizer.restore_backup(legacy, tmp_path / "out")
        assert restored.read_text(encoding="utf-8") == "old"

    def test_metadata_files_are_not_listed_as_backups(self, organizer, original):
        organizer.create_backup(original)

        names = [info["name"] for info in organizer.list_backups()]

        assert len(names) == 1
        assert not names[0].endswith(".meta.json")

    def test_cleanup_counts_backups_and_removes_their_metadata(
        self, organizer, original
    ):
        organizer.create_backup(original)

        removed = organizer.cleanup_old_backups(days=-1)

        assert removed == 1
        assert list(organizer.get_backup_dir().iterdir()) == []


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
