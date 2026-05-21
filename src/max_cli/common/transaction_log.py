"""Transaction log for reversible file operations."""

import json
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from max_cli.common.exceptions import MaxError


class TransactionError(MaxError):
    """Raised when a transaction operation fails."""

    pass


class TransactionLog:
    """Records file operations and supports undo via JSON persistence.

    Each command invocation creates a transaction group stored as a JSON file
    in ~/.max_cli/transactions/. Operations within a group can be reversed
    atomically via undo().
    """

    OP_RENAME = "rename"
    OP_MOVE = "move"
    OP_DELETE = "delete"
    OP_CREATE = "create"

    MAX_GROUPS = 50
    RETENTION_DAYS = 30

    def __init__(self, command: str, storage_dir: Optional[Path] = None) -> None:
        self.group_id = self._generate_id()
        self.command = command
        self.timestamp = datetime.now().isoformat()
        self.operations: list[dict] = []
        self.status = "completed"
        self.undo_status: Optional[str] = None
        self._storage_dir = storage_dir or Path.home() / ".max_cli" / "transactions"
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        op_type: str,
        original_path: Optional[Path],
        new_path: Optional[Path],
        backup_path: Optional[Path] = None,
    ) -> None:
        """Record a single file operation."""
        self.operations.append(
            {
                "op_type": op_type,
                "original_path": str(original_path) if original_path else None,
                "new_path": str(new_path) if new_path else None,
                "backup_path": str(backup_path) if backup_path else None,
            }
        )

    def save(self) -> Path:
        """Persist the transaction group to disk."""
        data = {
            "group_id": self.group_id,
            "command": self.command,
            "timestamp": self.timestamp,
            "operations": self.operations,
            "status": self.status,
            "undo_status": self.undo_status,
        }
        file_path = self._storage_dir / f"{self.group_id}.json"
        file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self._cleanup_old_groups()
        return file_path

    def undo(self) -> list[str]:
        """Reverse all operations in this transaction group (LIFO order)."""
        results: list[str] = []

        for op in reversed(self.operations):
            op_type = op["op_type"]
            original = Path(op["original_path"]) if op["original_path"] else None
            new = Path(op["new_path"]) if op["new_path"] else None
            backup = Path(op["backup_path"]) if op["backup_path"] else None

            try:
                if op_type == self.OP_RENAME:
                    if original and original.exists():
                        results.append(f"Already restored: {original.name}")
                    elif new and new.exists():
                        new.rename(original)
                        results.append(f"Restored: {new.name} -> {original.name}")
                    elif backup and backup.exists():
                        backup.rename(original)
                        results.append(
                            f"Restored from backup: {backup.name} -> {original.name}"
                        )
                    else:
                        raise TransactionError(
                            f"Cannot undo rename: neither {new} nor backup exists"
                        )

                elif op_type == self.OP_MOVE:
                    if original and original.exists():
                        results.append(f"Already restored: {original}")
                    elif new and new.exists():
                        original.parent.mkdir(parents=True, exist_ok=True)
                        new.rename(original)
                        results.append(f"Restored: {new.name} -> {original}")
                    elif backup and backup.exists():
                        original.parent.mkdir(parents=True, exist_ok=True)
                        backup.rename(original)
                        results.append(
                            f"Restored from backup: {backup.name} -> {original}"
                        )
                    else:
                        raise TransactionError(
                            f"Cannot undo move: neither {new} nor backup exists"
                        )

                elif op_type == self.OP_DELETE:
                    if backup and backup.exists():
                        original.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(backup, original)
                        results.append(
                            f"Restored from backup: {backup.name} -> {original.name}"
                        )
                    else:
                        raise TransactionError(
                            f"Cannot undo delete: no backup found for {original}"
                        )

                elif op_type == self.OP_CREATE:
                    if new and new.exists():
                        new.unlink()
                        results.append(f"Removed created file: {new.name}")
                    else:
                        results.append(f"Skip undo create: {new} does not exist")

            except OSError as e:
                raise TransactionError(
                    f"Undo failed for {op_type} ({original or new}): {e}"
                )

        self.undo_status = "undone"
        self.save()
        return results

    @classmethod
    def load(
        cls, group_id: str, storage_dir: Optional[Path] = None
    ) -> "TransactionLog":
        """Load a transaction group from disk."""
        store = storage_dir or Path.home() / ".max_cli" / "transactions"
        file_path = store / f"{group_id}.json"

        if not file_path.exists():
            raise TransactionError(f"Transaction group not found: {group_id}")

        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            raise TransactionError(f"Corrupt transaction file: {e}")

        txn = cls(command=data["command"], storage_dir=store)
        txn.group_id = data["group_id"]
        txn.timestamp = data["timestamp"]
        txn.operations = data["operations"]
        txn.status = data["status"]
        txn.undo_status = data.get("undo_status")
        return txn

    @classmethod
    def list_groups(cls, storage_dir: Optional[Path] = None) -> list[dict]:
        """List all transaction groups, newest first."""
        store = storage_dir or Path.home() / ".max_cli" / "transactions"
        if not store.exists():
            return []

        groups = []
        for f in sorted(
            store.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True
        ):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                groups.append(
                    {
                        "group_id": data["group_id"],
                        "command": data["command"],
                        "timestamp": data["timestamp"],
                        "operation_count": len(data["operations"]),
                        "status": data["status"],
                        "undo_status": data.get("undo_status"),
                    }
                )
            except (json.JSONDecodeError, OSError):
                continue

        return groups

    @classmethod
    def get_latest_group(cls, storage_dir: Optional[Path] = None) -> Optional[dict]:
        """Get the most recent transaction group metadata."""
        groups = cls.list_groups(storage_dir)
        return groups[0] if groups else None

    def _cleanup_old_groups(self) -> None:
        """Remove groups exceeding MAX_GROUPS count or RETENTION_DAYS age."""
        if not self._storage_dir.exists():
            return

        cutoff = datetime.now() - timedelta(days=self.RETENTION_DAYS)
        files = sorted(
            self._storage_dir.glob("*.json"),
            key=lambda x: x.stat().st_mtime,
        )

        for f in files:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()

        files = sorted(
            self._storage_dir.glob("*.json"),
            key=lambda x: x.stat().st_mtime,
        )
        while len(files) > self.MAX_GROUPS:
            files[0].unlink()
            files.pop(0)

    @classmethod
    def cleanup_all(cls, storage_dir: Optional[Path] = None, days: int = 30) -> int:
        """Remove transaction logs older than specified days.

        Args:
            storage_dir: Transaction storage directory
            days: Retention period in days

        Returns:
            Number of transaction logs removed
        """
        store = storage_dir or Path.home() / ".max_cli" / "transactions"
        if not store.exists():
            return 0

        cutoff = datetime.now() - timedelta(days=days)
        count = 0
        for f in store.glob("*.json"):
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
                count += 1
        return count

    @staticmethod
    def _generate_id() -> str:
        """Generate a unique transaction group ID."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_hash = uuid.uuid4().hex[:6]
        return f"txn_{ts}_{short_hash}"
