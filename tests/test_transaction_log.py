import json
import os
import time

import pytest
from pathlib import Path

from max_cli.common.transaction_log import TransactionLog, TransactionError


@pytest.fixture
def txn_storage(tmp_path):
    return tmp_path / "transactions"


@pytest.fixture
def sample_files(tmp_path):
    files = []
    for name in ["doc.txt", "photo.jpg", "song.mp3"]:
        p = tmp_path / name
        p.write_text(f"content of {name}")
        files.append(p)
    return tmp_path, files


class TestTransactionLogCreation:
    def test_generate_unique_id(self, txn_storage):
        txn1 = TransactionLog("files order", txn_storage)
        txn2 = TransactionLog("files order", txn_storage)
        assert txn1.group_id != txn2.group_id

    def test_id_format(self, txn_storage):
        txn = TransactionLog("files order", txn_storage)
        assert txn.group_id.startswith("txn_")
        parts = txn.group_id.split("_")
        assert len(parts) == 4

    def test_save_creates_json_file(self, txn_storage):
        txn = TransactionLog("files order", txn_storage)
        path = txn.save()
        assert path.exists()
        assert path.name == f"{txn.group_id}.json"

    def test_save_writes_valid_json(self, txn_storage):
        txn = TransactionLog("files order", txn_storage)
        txn.record("rename", Path("a.txt"), Path("b.txt"))
        path = txn.save()

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["command"] == "files order"
        assert len(data["operations"]) == 1

    def test_record_stores_paths_as_strings(self, txn_storage):
        txn = TransactionLog("files order", txn_storage)
        txn.record(
            "rename",
            Path("original.txt"),
            Path("new.txt"),
            Path("backup.txt"),
        )
        assert txn.operations[0]["original_path"] == "original.txt"
        assert txn.operations[0]["new_path"] == "new.txt"
        assert txn.operations[0]["backup_path"] == "backup.txt"

    def test_record_with_none_paths(self, txn_storage):
        txn = TransactionLog("files order", txn_storage)
        txn.record("delete", Path("gone.txt"), None, None)
        assert txn.operations[0]["original_path"] == "gone.txt"
        assert txn.operations[0]["new_path"] is None
        assert txn.operations[0]["backup_path"] is None


class TestTransactionLogUndo:
    def test_undo_rename(self, sample_files, txn_storage):
        tmp_path, files = sample_files
        original = files[0]
        new = tmp_path / "renamed_doc.txt"

        txn = TransactionLog("files order", txn_storage)
        txn.record("rename", original, new)
        txn.save()

        original.rename(new)

        txn.undo()
        assert original.exists()
        assert not new.exists()

    def test_undo_move_creates_parent_dirs(self, sample_files, txn_storage):
        tmp_path, files = sample_files
        original = files[0]
        dest_dir = tmp_path / "Deep" / "Nested" / "Dir"
        dest = dest_dir / "doc.txt"

        txn = TransactionLog("files smart-sort", txn_storage)
        txn.record("move", original, dest)
        txn.save()

        dest_dir.mkdir(parents=True)
        original.rename(dest)

        txn.undo()
        assert original.exists()

    def test_undo_move_uses_backup_fallback(self, sample_files, txn_storage):
        tmp_path, files = sample_files
        original = files[0]
        dest = tmp_path / "moved" / "doc.txt"
        backup = txn_storage / "doc_backup.txt"

        txn = TransactionLog("files smart-sort", txn_storage)
        txn.record("move", original, dest, backup)
        txn.save()

        dest.parent.mkdir(parents=True)
        original.rename(dest)
        dest.unlink()
        backup.write_text("backup content")

        txn.undo()
        assert original.exists()
        assert original.read_text() == "backup content"

    def test_undo_delete_from_backup(self, sample_files, txn_storage):
        tmp_path, files = sample_files
        original = files[0]
        backup = txn_storage.parent / "backups" / "doc_backup.txt"
        backup.parent.mkdir(parents=True, exist_ok=True)

        txn = TransactionLog("files shred", txn_storage)
        txn.record("delete", original, None, backup)
        txn.save()

        original.unlink()
        backup.write_text("backup content")

        txn.undo()
        assert original.exists()
        assert original.read_text() == "backup content"

    def test_undo_delete_no_backup_raises(self, sample_files, txn_storage):
        tmp_path, files = sample_files
        original = files[0]

        txn = TransactionLog("files shred", txn_storage)
        txn.record("delete", original, None, None)
        txn.save()

        original.unlink()

        with pytest.raises(TransactionError, match="no backup found"):
            txn.undo()

    def test_undo_create(self, sample_files, txn_storage):
        tmp_path, _ = sample_files
        created = tmp_path / "new_file.txt"
        created.write_text("new content")

        txn = TransactionLog("some command", txn_storage)
        txn.record("create", None, created)
        txn.save()

        txn.undo()
        assert not created.exists()

    def test_undo_create_when_file_already_gone(self, sample_files, txn_storage):
        tmp_path, _ = sample_files
        created = tmp_path / "new_file.txt"
        created.write_text("new content")

        txn = TransactionLog("some command", txn_storage)
        txn.record("create", None, created)
        txn.save()

        created.unlink()

        results = txn.undo()
        assert "Skip undo create" in results[0]

    def test_undo_is_idempotent(self, sample_files, txn_storage):
        tmp_path, files = sample_files
        original = files[0]
        new = tmp_path / "renamed_doc.txt"

        txn = TransactionLog("files order", txn_storage)
        txn.record("rename", original, new)
        txn.save()

        original.rename(new)
        txn.undo()
        assert txn.undo_status == "undone"

        txn2 = TransactionLog.load(txn.group_id, txn_storage)
        txn2.undo()

    def test_undo_sets_status(self, sample_files, txn_storage):
        tmp_path, files = sample_files
        original = files[0]
        new = tmp_path / "renamed_doc.txt"

        txn = TransactionLog("files order", txn_storage)
        txn.record("rename", original, new)
        txn.save()

        original.rename(new)
        txn.undo()
        assert txn.undo_status == "undone"

    def test_undo_multiple_operations_lifo(self, sample_files, txn_storage):
        tmp_path, files = sample_files
        file_a = files[0]
        file_b = files[1]
        new_a = tmp_path / "new_a.txt"
        new_b = tmp_path / "new_b.txt"

        txn = TransactionLog("files order", txn_storage)
        txn.record("rename", file_a, new_a)
        txn.record("rename", file_b, new_b)
        txn.save()

        file_a.rename(new_a)
        file_b.rename(new_b)

        results = txn.undo()
        assert len(results) == 2
        assert file_a.exists()
        assert file_b.exists()
        assert not new_a.exists()
        assert not new_b.exists()


class TestTransactionLogListGroups:
    def test_list_empty(self, txn_storage):
        assert TransactionLog.list_groups(txn_storage) == []

    def test_list_returns_newest_first(self, txn_storage):
        txn1 = TransactionLog("cmd1", txn_storage)
        txn1.save()
        time.sleep(0.01)
        txn2 = TransactionLog("cmd2", txn_storage)
        txn2.save()

        groups = TransactionLog.list_groups(txn_storage)
        assert len(groups) == 2
        assert groups[0]["group_id"] == txn2.group_id
        assert groups[1]["group_id"] == txn1.group_id

    def test_get_latest_group(self, txn_storage):
        txn = TransactionLog("files order", txn_storage)
        txn.save()

        latest = TransactionLog.get_latest_group(txn_storage)
        assert latest is not None
        assert latest["group_id"] == txn.group_id

    def test_get_latest_group_empty(self, txn_storage):
        latest = TransactionLog.get_latest_group(txn_storage)
        assert latest is None

    def test_list_skips_corrupt_files(self, txn_storage):
        txn_storage.mkdir(parents=True, exist_ok=True)
        corrupt_file = txn_storage / "txn_corrupt.json"
        corrupt_file.write_text("not valid json")

        txn = TransactionLog("cmd1", txn_storage)
        txn.save()

        groups = TransactionLog.list_groups(txn_storage)
        assert len(groups) == 1
        assert groups[0]["group_id"] == txn.group_id


class TestTransactionLogCleanup:
    def test_cleanup_excess_groups(self, txn_storage):
        for i in range(55):
            txn = TransactionLog(f"cmd{i}", txn_storage)
            txn.save()
            time.sleep(0.001)

        files = list(txn_storage.glob("*.json"))
        assert len(files) <= TransactionLog.MAX_GROUPS

    def test_cleanup_old_groups_by_age(self, txn_storage):
        txn = TransactionLog("old cmd", txn_storage)
        path = txn.save()

        old_time = time.time() - (31 * 86400)
        os.utime(path, (old_time, old_time))

        txn2 = TransactionLog("new cmd", txn_storage)
        txn2.save()

        files = list(txn_storage.glob("*.json"))
        assert not path.exists()
        assert any(f.name == f"{txn2.group_id}.json" for f in files)

    def test_cleanup_does_not_remove_recent_groups(self, txn_storage):
        txn = TransactionLog("recent cmd", txn_storage)
        txn.save()

        files_before = list(txn_storage.glob("*.json"))
        assert len(files_before) == 1

        txn2 = TransactionLog("another cmd", txn_storage)
        txn2.save()

        files_after = list(txn_storage.glob("*.json"))
        assert len(files_after) == 2


class TestTransactionLogLoad:
    def test_load_corrupt_json_raises(self, txn_storage):
        txn_storage.mkdir(parents=True, exist_ok=True)
        corrupt_file = txn_storage / "txn_bad.json"
        corrupt_file.write_text("{invalid json")

        with pytest.raises(TransactionError, match="Corrupt transaction file"):
            TransactionLog.load("txn_bad", txn_storage)

    def test_load_missing_group_raises(self, txn_storage):
        with pytest.raises(TransactionError, match="Transaction group not found"):
            TransactionLog.load("txn_nonexistent", txn_storage)

    def test_load_roundtrip(self, txn_storage):
        txn = TransactionLog("files order", txn_storage)
        txn.record("rename", Path("a.txt"), Path("b.txt"))
        txn.save()

        loaded = TransactionLog.load(txn.group_id, txn_storage)
        assert loaded.group_id == txn.group_id
        assert loaded.command == "files order"
        assert len(loaded.operations) == 1
        assert loaded.operations[0]["op_type"] == "rename"
        assert loaded.status == "completed"
        assert loaded.undo_status is None

    def test_load_preserves_undo_status(self, txn_storage):
        txn = TransactionLog("files order", txn_storage)
        txn.undo_status = "undone"
        txn.save()

        loaded = TransactionLog.load(txn.group_id, txn_storage)
        assert loaded.undo_status == "undone"
