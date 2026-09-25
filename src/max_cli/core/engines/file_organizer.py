from pathlib import Path
from typing import TYPE_CHECKING, List, Dict, Any, Optional

if TYPE_CHECKING:
    from max_cli.common.transaction_log import TransactionLog

from max_cli.common.atomic import atomic_write_json
from max_cli.common.exceptions import ResourceNotFoundError, ValidationError

SHRED_CHUNK_BYTES = 1024 * 1024
HASH_CHUNK_BYTES = 1024 * 1024
RESERVED_NAMES = {".", ".."}


BACKUP_METADATA_SUFFIX = ".meta.json"


def _backup_metadata_path(backup_path: Path) -> Path:
    return backup_path.with_name(backup_path.name + BACKUP_METADATA_SUFFIX)


def _read_original_path(backup_path: Path) -> Optional[Path]:
    """Original location recorded by create_backup, or None if unknown."""
    import json

    metadata_path = _backup_metadata_path(backup_path)
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    original = metadata.get("original_path") if isinstance(metadata, dict) else None
    return Path(original) if isinstance(original, str) and original else None


def _file_digest(path: Path) -> str:
    """SHA-256 of a file, read in chunks so large files never load whole."""
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_plain_name(value: object) -> bool:
    """True for a single, non-empty path component with no separators or drive."""
    if not isinstance(value, str) or not value.strip():
        return False
    if value in RESERVED_NAMES or "/" in value or "\\" in value:
        return False
    candidate = Path(value)
    return (
        candidate.name == value and not candidate.is_absolute() and not candidate.drive
    )


class FileOrganizer:
    """
    Core logic for organizing and renaming files.
    """

    def scan_directory(self, folder: Path) -> List[Path]:
        """Returns a sorted list of files in the folder (excluding subfolders)."""
        if not folder.exists() or not folder.is_dir():
            raise ResourceNotFoundError(f"Folder '{folder}' not found.")

        # Get all files, exclude directories
        files = [f for f in folder.iterdir() if f.is_file()]

        # Sort alphabetically so the ordering is deterministic
        files.sort(key=lambda f: f.name.lower())
        return files

    def order_files(
        self,
        folder: Path,
        dry_run: bool = False,
        start_index: int = 1,
        transaction_log: Optional["TransactionLog"] = None,
    ) -> Dict[str, Any]:
        """
        Renames files by prepending numbers (1_file.txt, 2_file.txt).
        Returns statistics about the operation.
        """
        files = self.scan_directory(folder)
        renamed_count = 0
        skipped_count = 0
        actions = []

        current_index = start_index

        for file_path in files:
            original_name = file_path.name

            parts = original_name.split("_")
            if len(parts) > 1 and parts[0].isdigit():
                skipped_count += 1
                continue

            new_name = f"{current_index}_{original_name}"
            new_path = folder / new_name

            if dry_run:
                actions.append(
                    f"[DRY RUN] Would rename '{original_name}' -> '{new_name}'"
                )
            else:
                if transaction_log:
                    from max_cli.common.transaction_log import TransactionLog

                    transaction_log.record(
                        op_type=TransactionLog.OP_RENAME,
                        original_path=file_path,
                        new_path=new_path,
                    )
                try:
                    file_path.rename(new_path)
                    actions.append(f"Renamed '{original_name}' -> '{new_name}'")
                except OSError as e:
                    actions.append(f"[Error] Could not rename '{original_name}': {e}")
                    continue

            renamed_count += 1
            current_index += 1

        return {
            "total_files": len(files),
            "renamed": renamed_count,
            "skipped": skipped_count,
            "actions": actions,
        }

    def find_duplicates(
        self, folder: Path, recursive: bool = False
    ) -> Dict[str, List[Path]]:
        """
        Find duplicate files based on content hash.

        Returns:
            Dictionary mapping hash to list of duplicate file paths
        """
        if not folder.exists() or not folder.is_dir():
            raise ResourceNotFoundError(f"Folder '{folder}' not found.")

        # Sort so every group lists paths in the same order on every OS;
        # delete_duplicates keeps the first path of each group.
        if recursive:
            files = sorted(f for f in folder.rglob("*") if f.is_file())
        else:
            files = sorted(f for f in folder.iterdir() if f.is_file())

        # Only files that share a size can be duplicates; skip hashing the rest.
        by_size: Dict[int, List[Path]] = {}
        for file_path in files:
            try:
                by_size.setdefault(file_path.stat().st_size, []).append(file_path)
            except OSError:
                continue

        hash_map: Dict[str, List[Path]] = {}
        for same_size_files in by_size.values():
            if len(same_size_files) < 2:
                continue
            for file_path in same_size_files:
                try:
                    file_hash = _file_digest(file_path)
                except OSError:
                    continue
                hash_map.setdefault(file_hash, []).append(file_path)

        return {digest: paths for digest, paths in hash_map.items() if len(paths) > 1}

    def delete_duplicates(
        self,
        folder: Path,
        duplicates: Dict[str, List[Path]],
        transaction_log: Optional["TransactionLog"] = None,
        auto_backup: bool = True,
    ) -> Dict[str, Any]:
        """Delete duplicate files, keeping the first in each group."""
        removed = 0
        kept_paths: list[Path] = []
        errors: list[str] = []

        for hash_val, paths in duplicates.items():
            keep = paths[0]
            kept_paths.append(keep)

            for p in paths[1:]:
                try:
                    backup_path = None
                    if auto_backup:
                        backup_path = self.create_backup(p, label="pre_dedupe")

                    if transaction_log:
                        from max_cli.common.transaction_log import TransactionLog

                        transaction_log.record(
                            op_type=TransactionLog.OP_DELETE,
                            original_path=p,
                            new_path=None,
                            backup_path=backup_path,
                        )

                    p.unlink()
                    removed += 1
                except OSError as e:
                    errors.append(f"Failed to delete {p}: {e}")

        return {
            "removed": removed,
            "kept": kept_paths,
            "errors": errors,
        }

    def smart_sort(
        self,
        path: Path,
        categories: Dict[str, str],
        dry_run: bool = False,
        transaction_log: Optional["TransactionLog"] = None,
    ) -> Dict[str, Any]:
        moved = 0
        skipped = 0
        errors = 0
        actions = []

        base = path.resolve()
        for filename, category in categories.items():
            # Names usually come from an AI response: treat them as untrusted.
            if not (_is_plain_name(filename) and _is_plain_name(category)):
                errors += 1
                actions.append(f"[Rejected] {filename!r} -> {category!r}: unsafe name")
                continue

            src = path / filename
            dest_dir = path / category
            dest = dest_dir / filename
            # Compare resolved paths on both sides: catches symlinked category
            # folders and stays correct on case-insensitive filesystems.
            if dest.resolve().parent.parent != base:
                errors += 1
                actions.append(
                    f"[Rejected] {filename!r} -> {category!r}: outside target"
                )
                continue

            if not src.exists():
                errors += 1
                continue

            if dest.exists():
                skipped += 1
                actions.append(f"[Skipped] {filename}: {category}/{filename} exists")
                continue

            if dry_run:
                actions.append(f"[DRY RUN] {filename} -> {category}/")
                continue

            try:
                if transaction_log:
                    from max_cli.common.transaction_log import TransactionLog

                    transaction_log.record(
                        op_type=TransactionLog.OP_MOVE,
                        original_path=src,
                        new_path=dest,
                    )

                dest_dir.mkdir(parents=True, exist_ok=True)
                src.rename(dest)
                actions.append(f"{filename} -> {category}/")
                moved += 1
            except OSError as e:
                errors += 1
                actions.append(f"[Error] {filename}: {e}")

        return {
            "moved": moved,
            "skipped": skipped,
            "errors": errors,
            "actions": actions,
        }

    def secure_delete(
        self,
        path: Path,
        passes: int = 3,
        transaction_log: Optional["TransactionLog"] = None,
        auto_backup: bool = False,
    ) -> bool:
        """
        Securely delete a file by overwriting with random data.

        Args:
            path: File to securely delete
            passes: Number of overwrite passes (default 3)
            transaction_log: Optional transaction log for recording operations
            auto_backup: Keep a backup copy first. Off by default: a backup
                defeats a secure delete, so only pass True for testing.

        Returns:
            True if successful
        """
        import os

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if path.is_dir():
            raise ValueError("Cannot securely delete directories")

        backup_path = None
        if auto_backup:
            backup_path = self.create_backup(path, label="pre_shred")

        if transaction_log:
            from max_cli.common.transaction_log import TransactionLog

            transaction_log.record(
                op_type=TransactionLog.OP_DELETE,
                original_path=path,
                new_path=None,
                backup_path=backup_path,
            )

        file_size = path.stat().st_size

        try:
            # "r+b" writes over existing bytes; append modes ignore seek() for writes.
            with open(path, "r+b") as f:
                for _ in range(passes):
                    f.seek(0)
                    remaining = file_size
                    while remaining > 0:
                        chunk_size = min(SHRED_CHUNK_BYTES, remaining)
                        f.write(os.urandom(chunk_size))
                        remaining -= chunk_size
                    f.flush()
                    os.fsync(f.fileno())

            path.unlink()
            return True
        except OSError as e:
            raise OSError(f"Secure delete failed: {e}")

    def get_backup_dir(self) -> Path:
        """Get or create the backup directory."""
        backup_dir = Path.home() / ".max_cli" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        return backup_dir

    def create_backup(self, path: Path, label: str = "manual") -> Path:
        """
        Create a backup of a file.

        Args:
            path: File to backup
            label: Optional label for the backup

        Returns:
            Path to the backup file
        """
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        from datetime import datetime

        import shutil

        backup_dir = self.get_backup_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{path.stem}_{label}_{timestamp}{path.suffix}"
        backup_path = backup_dir / backup_name

        shutil.copy2(path, backup_path)
        atomic_write_json(
            _backup_metadata_path(backup_path),
            {"original_path": str(path.resolve())},
            indent=None,
        )

        return backup_path

    def list_backups(self, filename: str = None) -> List[Dict[str, Any]]:
        """
        List available backups.

        Args:
            filename: Optional filename filter

        Returns:
            List of backup info dictionaries
        """
        backup_dir = self.get_backup_dir()

        backups = []
        for f in sorted(
            backup_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True
        ):
            if f.name.endswith(BACKUP_METADATA_SUFFIX):
                continue
            if filename and filename not in f.stem:
                continue

            stat = f.stat()
            backups.append(
                {
                    "path": f,
                    "name": f.name,
                    "size": stat.st_size,
                    "created": stat.st_ctime,
                }
            )

        return backups

    def restore_backup(self, backup_path: Path, target_dir: Path = None) -> Path:
        """
        Restore a backup to a target location.

        Args:
            backup_path: Path to the backup file
            target_dir: Optional target directory (defaults to original location)

        Returns:
            Path to the restored file

        Raises:
            ValidationError: no target_dir and the original location is unknown
                (backups made before locations were recorded), or a file
                already exists there.
        """
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_path}")

        import shutil

        original_path = _read_original_path(backup_path)
        if target_dir:
            target_dir.mkdir(parents=True, exist_ok=True)
            restore_name = original_path.name if original_path else backup_path.name
            restore_path = target_dir / restore_name
        elif original_path is None:
            raise ValidationError(
                f"No original location recorded for {backup_path.name}. "
                "Choose a folder to restore into."
            )
        elif original_path.exists():
            raise ValidationError(
                f"{original_path} already exists. Restore into another folder "
                "or move the current file first."
            )
        else:
            original_path.parent.mkdir(parents=True, exist_ok=True)
            restore_path = original_path

        shutil.copy2(backup_path, restore_path)
        return restore_path

    def cleanup_old_backups(self, days: int = 30) -> int:
        """
        Remove backups older than specified days.

        Args:
            days: Remove backups older than this many days

        Returns:
            Number of backups removed
        """
        import time

        backup_dir = self.get_backup_dir()
        cutoff = time.time() - (days * 86400)
        removed = 0

        for f in backup_dir.iterdir():
            if f.name.endswith(BACKUP_METADATA_SUFFIX):
                continue  # removed together with its backup below
            if f.stat().st_ctime < cutoff:
                f.unlink()
                _backup_metadata_path(f).unlink(missing_ok=True)
                removed += 1

        return removed


def _file_organize_executor(task: "TaskItem") -> Dict[str, Any]:
    from pathlib import Path

    engine = FileOrganizer()
    payload = task.payload
    path = Path(payload["path"])
    categories = payload.get("categories", {})
    dry_run = payload.get("dry_run", False)

    result = engine.smart_sort(path, categories, dry_run=dry_run)
    moved = result.get("moved", 0)
    errors = result.get("errors", 0)
    return {
        "moved": moved,
        "errors": errors,
        "output_files": [],
        "message": f"Moved {moved} files ({errors} errors)",
    }


def _file_duplicates_executor(task: "TaskItem") -> Dict[str, Any]:
    from pathlib import Path

    engine = FileOrganizer()
    payload = task.payload
    folder = Path(payload["folder"])
    recursive = payload.get("recursive", False)

    dupes = engine.find_duplicates(folder, recursive)
    groups = len(dupes)
    total_dupes = sum(len(v) - 1 for v in dupes.values() if isinstance(v, list))
    return {
        "duplicate_groups": groups,
        "total_duplicates": total_dupes,
        "output_files": [],
        "message": f"Found {groups} groups of duplicates ({total_dupes} duplicate files)",
    }


from max_cli.core.engines.task_queue import TaskItem, TaskType, register_executor  # noqa: E402

register_executor(TaskType.FILE_ORGANIZE, _file_organize_executor)
register_executor(TaskType.FILE_DUPLICATES, _file_duplicates_executor)
