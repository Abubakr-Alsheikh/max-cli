from pathlib import Path
from typing import TYPE_CHECKING, List, Dict, Any, Optional

if TYPE_CHECKING:
    from max_cli.common.transaction_log import TransactionLog

from max_cli.common.exceptions import ResourceNotFoundError


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
        import hashlib

        if not folder.exists() or not folder.is_dir():
            raise ResourceNotFoundError(f"Folder '{folder}' not found.")

        hash_map: Dict[str, List[Path]] = {}

        if recursive:
            files = [f for f in folder.rglob("*") if f.is_file()]
        else:
            files = [f for f in folder.iterdir() if f.is_file()]

        for file_path in files:
            try:
                with open(file_path, "rb") as f:
                    file_hash = hashlib.md5(f.read()).hexdigest()

                if file_hash in hash_map:
                    hash_map[file_hash].append(file_path)
                else:
                    hash_map[file_hash] = [file_path]
            except OSError:
                continue

        duplicates = {k: v for k, v in hash_map.items() if len(v) > 1}
        return duplicates

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

        for filename, category in categories.items():
            src = path / filename
            dest_dir = path / category
            dest = dest_dir / filename

            if not src.exists():
                errors += 1
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
        auto_backup: bool = True,
    ) -> bool:
        """
        Securely delete a file by overwriting with random data.

        Args:
            path: File to securely delete
            passes: Number of overwrite passes (default 3)
            transaction_log: Optional transaction log for recording operations
            auto_backup: Automatically create backup before deletion (default True)

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
            with open(path, "ba+") as f:
                for _ in range(passes):
                    f.seek(0)
                    f.write(os.urandom(file_size))
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

        backup_dir = self.get_backup_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{path.stem}_{label}_{timestamp}{path.suffix}"
        backup_path = backup_dir / backup_name

        import shutil

        shutil.copy2(path, backup_path)

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
        """
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_path}")

        import shutil

        if target_dir:
            target_dir.mkdir(parents=True, exist_ok=True)
            restore_path = target_dir / backup_path.name
        else:
            restore_path = backup_path.parent.parent / backup_path.name

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
            if f.stat().st_ctime < cutoff:
                f.unlink()
                removed += 1

        return removed
