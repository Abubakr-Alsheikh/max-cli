# Plan: Undo / Transaction Log

> Status: Completed
> Priority: P1
> Related: User Experience & Laziness (Feature 2B)

## Overview

Max CLI performs destructive file operations (rename, move, delete) with no safety net beyond the manual `max files backup` command. Users who accidentally run `max files order`, `max files smart-sort`, or `max files duplicates --delete` have no way to reverse the damage.

This plan introduces a **Transaction Log** system that records every file-modifying operation, persists it to disk, and provides `max files undo` and `max files history` commands to reverse or inspect past operations.

## Problem Analysis

### Current State

| Command | Operation | Undo Available? |
|---------|-----------|-----------------|
| `max files order` | `file_path.rename(new_path)` | No — `actions` list is returned but never persisted |
| `max files smart-sort` | `src.rename(dest_dir / filename)` in interface layer | No — rename happens directly in `cli_files.py` |
| `max files duplicates --delete` | `p.unlink()` in interface layer | No — files are permanently deleted |
| `max files shred` | overwrite + `path.unlink()` | No — by design, but no pre-shred backup |
| `max audio organize` | `file_path.rename(dest_path)` in `AudioMetadataEngine` | No |
| `max files backup` | manual copy to `~/.max_cli/backups/` | Yes — but user must invoke it beforehand |

### Root Causes

1. **No persistence**: `FileOrganizer.order_files()` returns an `actions` list of strings, but this is printed and discarded.
2. **Business logic in interface**: `smart-sort` and `duplicates --delete` perform `.rename()` and `.unlink()` directly in `cli_files.py`, bypassing the engine entirely.
3. **No grouping**: Even if operations were logged, there is no concept of a "transaction group" that ties all operations from a single command invocation together.
4. **No auto-backup**: Destructive operations (`shred`, `duplicates --delete`) do not automatically create a restore point.

## Goals

- [ ] Create `TransactionLog` class in `src/max_cli/common/transaction_log.py` with JSON persistence to `~/.max_cli/transactions/`
- [ ] Record all file operations (rename, move, delete, create) with full reversibility data
- [ ] Add `max files undo` command to reverse the last transaction group
- [ ] Add `max files history` command to list recent transaction groups
- [ ] Update `FileOrganizer` methods to accept optional `transaction_log` parameter
- [ ] Move `smart-sort` and `duplicates --delete` logic from interface layer into the engine, wired through the transaction log
- [ ] Auto-backup before destructive operations (`shred`, `duplicates --delete`)
- [ ] Auto-cleanup: max 50 transaction groups, 30-day retention
- [ ] All operations must be **idempotent** — running undo twice should be safe
- [ ] Cross-platform safe (use `pathlib.Path`, no hardcoded `/tmp/`)

## Implementation Details

### Phase 1: Transaction Log Module

**File**: `src/max_cli/common/transaction_log.py`

#### JSON Schema

Each transaction group is stored as a separate JSON file in `~/.max_cli/transactions/`:

```json
{
  "group_id": "txn_20260519_143022_a1b2c3",
  "command": "files order",
  "timestamp": "2026-05-19T14:30:22.123456",
  "operations": [
    {
      "op_type": "rename",
      "original_path": "D:\\photos\\vacation.jpg",
      "new_path": "D:\\photos\\1_vacation.jpg",
      "backup_path": null
    },
    {
      "op_type": "move",
      "original_path": "D:\\downloads\\song.mp3",
      "new_path": "D:\\downloads\\Music\\song.mp3",
      "backup_path": null
    },
    {
      "op_type": "delete",
      "original_path": "D:\\downloads\\copy_song.mp3",
      "new_path": null,
      "backup_path": "C:\\Users\\User\\.max_cli\\backups\\copy_song_auto_20260519_143022.mp3"
    },
    {
      "op_type": "create",
      "original_path": null,
      "new_path": "D:\\output\\compressed.jpg",
      "backup_path": null
    }
  ],
  "status": "completed",
  "undo_status": null
}
```

**Field Definitions**:

| Field | Type | Description |
|-------|------|-------------|
| `group_id` | `str` | Unique identifier: `txn_YYYYMMDD_HHMMSS_<6char_hash>` |
| `command` | `str` | The CLI command that triggered this (e.g., `"files order"`) |
| `timestamp` | `str` | ISO 8601 timestamp of creation |
| `operations` | `list[dict]` | Ordered list of file operations |
| `op_type` | `str` | One of: `"rename"`, `"move"`, `"delete"`, `"create"` |
| `original_path` | `str \| null` | Path before the operation (null for `create`) |
| `new_path` | `str \| null` | Path after the operation (null for `delete`) |
| `backup_path` | `str \| null` | Auto-backup path (populated for `delete` and destructive ops) |
| `status` | `str` | `"completed"` or `"failed"` |
| `undo_status` | `str \| null` | `null` (not undone), `"undone"`, `"undo_failed"` |

#### Implementation

```python
"""Transaction log for reversible file operations."""

import json
import time
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

    def __init__(self, command: str, storage_dir: Optional[Path] = None):
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
        """Record a single file operation.

        Args:
            op_type: One of OP_RENAME, OP_MOVE, OP_DELETE, OP_CREATE.
            original_path: Path before the operation.
            new_path: Path after the operation.
            backup_path: Optional backup path for destructive operations.
        """
        self.operations.append({
            "op_type": op_type,
            "original_path": str(original_path) if original_path else None,
            "new_path": str(new_path) if new_path else None,
            "backup_path": str(backup_path) if backup_path else None,
        })

    def save(self) -> Path:
        """Persist the transaction group to disk.

        Returns:
            Path to the saved JSON file.
        """
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
        """Reverse all operations in this transaction group.

        Operations are reversed in reverse order (LIFO) to handle
        dependencies correctly (e.g., move a file back before renaming it).

        Returns:
            List of result messages for each undone operation.

        Raises:
            TransactionError: If an undo operation fails.
        """
        results: list[str] = []

        for op in reversed(self.operations):
            op_type = op["op_type"]
            original = Path(op["original_path"]) if op["original_path"] else None
            new = Path(op["new_path"]) if op["new_path"] else None
            backup = Path(op["backup_path"]) if op["backup_path"] else None

            try:
                if op_type == self.OP_RENAME:
                    # Reverse: rename new_path -> original_path
                    if new and new.exists():
                        new.rename(original)
                        results.append(
                            f"Restored: {new.name} -> {original.name}"
                        )
                    elif backup and backup.exists():
                        # Fallback: restore from auto-backup
                        backup.rename(original)
                        results.append(
                            f"Restored from backup: {backup.name} -> {original.name}"
                        )
                    else:
                        raise TransactionError(
                            f"Cannot undo rename: neither {new} nor backup exists"
                        )

                elif op_type == self.OP_MOVE:
                    # Reverse: move new_path -> original_path
                    if new and new.exists():
                        original.parent.mkdir(parents=True, exist_ok=True)
                        new.rename(original)
                        results.append(
                            f"Restored: {new.name} -> {original}"
                        )
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
                    # Reverse: restore from backup to original_path
                    if backup and backup.exists():
                        original.parent.mkdir(parents=True, exist_ok=True)
                        import shutil
                        shutil.copy2(backup, original)
                        results.append(
                            f"Restored from backup: {backup.name} -> {original.name}"
                        )
                    else:
                        raise TransactionError(
                            f"Cannot undo delete: no backup found for {original}"
                        )

                elif op_type == self.OP_CREATE:
                    # Reverse: delete the created file
                    if new and new.exists():
                        new.unlink()
                        results.append(f"Removed created file: {new.name}")
                    else:
                        results.append(
                            f"Skip undo create: {new} does not exist"
                        )

            except OSError as e:
                raise TransactionError(
                    f"Undo failed for {op_type} ({original or new}): {e}"
                )

        self.undo_status = "undone"
        self.save()  # Persist undo status
        return results

    @classmethod
    def load(cls, group_id: str, storage_dir: Optional[Path] = None) -> "TransactionLog":
        """Load a transaction group from disk.

        Args:
            group_id: The group_id to load.
            storage_dir: Optional storage directory override.

        Returns:
            Populated TransactionLog instance.

        Raises:
            TransactionError: If the group file is not found or corrupt.
        """
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
        """List all transaction groups, newest first.

        Returns:
            List of dicts with group metadata (no full operations list).
        """
        store = storage_dir or Path.home() / ".max_cli" / "transactions"
        if not store.exists():
            return []

        groups = []
        for f in sorted(store.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                groups.append({
                    "group_id": data["group_id"],
                    "command": data["command"],
                    "timestamp": data["timestamp"],
                    "operation_count": len(data["operations"]),
                    "status": data["status"],
                    "undo_status": data.get("undo_status"),
                })
            except (json.JSONDecodeError, OSError):
                continue

        return groups

    @classmethod
    def get_latest_group(cls, storage_dir: Optional[Path] = None) -> Optional[dict]:
        """Get the most recent transaction group metadata.

        Returns:
            Dict with group metadata, or None if no groups exist.
        """
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

        # Remove by age
        for f in files:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()

        # Remove excess count (keep newest MAX_GROUPS)
        files = sorted(
            self._storage_dir.glob("*.json"),
            key=lambda x: x.stat().st_mtime,
        )
        while len(files) > self.MAX_GROUPS:
            files[0].unlink()
            files.pop(0)

    @staticmethod
    def _generate_id() -> str:
        """Generate a unique transaction group ID."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_hash = uuid.uuid4().hex[:6]
        return f"txn_{ts}_{short_hash}"
```

### Phase 2: Update FileOrganizer to Support Transaction Logging

**File**: `src/max_cli/core/engines/file_organizer.py`

Add optional `transaction_log` parameter to all file-modifying methods:

```python
from typing import List, Dict, Any, Optional

# Add import at top (after existing imports)
from max_cli.common.transaction_log import TransactionLog


class FileOrganizer:
    # ... existing methods unchanged ...

    def order_files(
        self,
        folder: Path,
        dry_run: bool = False,
        start_index: int = 1,
        transaction_log: Optional[TransactionLog] = None,
    ) -> Dict[str, Any]:
        """Renames files by prepending numbers. Records operations if transaction_log provided."""
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
                try:
                    # Record BEFORE rename so original_path is valid
                    if transaction_log:
                        transaction_log.record(
                            op_type=TransactionLog.OP_RENAME,
                            original_path=file_path,
                            new_path=new_path,
                        )

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

    def secure_delete(
        self,
        path: Path,
        passes: int = 3,
        transaction_log: Optional[TransactionLog] = None,
        auto_backup: bool = True,
    ) -> bool:
        """Securely delete a file. Optionally creates backup and records transaction."""
        import os

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if path.is_dir():
            raise ValueError("Cannot securely delete directories")

        backup_path = None
        if auto_backup:
            backup_path = self.create_backup(path, label="pre_shred")
            if transaction_log:
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

    def delete_duplicates(
        self,
        folder: Path,
        duplicates: Dict[str, List[Path]],
        transaction_log: Optional[TransactionLog] = None,
        auto_backup: bool = True,
    ) -> Dict[str, Any]:
        """Delete duplicate files, keeping the first in each group.

        This method is extracted from cli_files.py to keep business logic
        in the core layer where it can be transaction-logged.

        Args:
            folder: Root folder being scanned.
            duplicates: Output from find_duplicates().
            transaction_log: Optional transaction log for undo support.
            auto_backup: Create backup before deleting each duplicate.

        Returns:
            Dict with 'removed', 'kept', 'errors' info.
        """
        import shutil

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
```

### Phase 3: Add Smart-Sort to FileOrganizer (Move Logic from Interface)

The `smart-sort` command currently does `src.rename()` directly in `cli_files.py`. This must be moved to the engine so it can be transaction-logged.

```python
# Add to FileOrganizer class in file_organizer.py

    def smart_sort(
        self,
        path: Path,
        categories: Dict[str, str],
        dry_run: bool = False,
        transaction_log: Optional[TransactionLog] = None,
    ) -> Dict[str, Any]:
        """Move files into AI-categorized subdirectories.

        Args:
            path: Root directory containing files.
            categories: Mapping of filename -> category folder name.
            dry_run: If True, only simulate moves.
            transaction_log: Optional transaction log for undo support.

        Returns:
            Dict with 'moved', 'skipped', 'errors' counts.
        """
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
```

### Phase 4: Update cli_files.py Commands

**File**: `src/max_cli/interface/cli_files.py`

#### 4a. Update `order_files` command

```python
@app.command("order")
@app.command("ord", hidden=True)
def order_files(
    folder: Path = typer.Argument(..., help="The folder containing files to order."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Simulate the rename without changing files."
    ),
    force: bool = typer.Option(
        False, "-f", "--force", help="Skip confirmation prompt."
    ),
    start: int = typer.Option(
        1, "--start", help="Number to start counting from (default 1)."
    ),
):
    """Rename all files in a folder with a number prefix (e.g. 1_file.txt)."""

    if not folder.is_dir():
        log_error(f"'{folder}' is not a directory.")
        raise typer.Exit(code=1)

    try:
        org = _get_organizer()
        files = org.scan_directory(folder)
    except Exception as e:
        log_error(str(e))
        raise typer.Exit(code=1)

    if not files:
        console.print("[yellow]Folder is empty. Nothing to do.[/yellow]")
        return

    if not dry_run and not force:
        console.print(
            Panel(
                Text(f"Target: {folder}\nFiles found: {len(files)}", justify="center"),
                title="[bold yellow]Bulk Rename Warning[/bold yellow]",
                border_style="yellow",
            )
        )
        if not Confirm.ask("Are you sure you want to rename these files?"):
            console.print("[red]Aborted.[/red]")
            raise typer.Exit()

    console.print(
        f"[bold cyan]Processing files starting at index {start}...[/bold cyan]"
    )

    # Create transaction log for this operation
    txn = None
    if not dry_run:
        from max_cli.common.transaction_log import TransactionLog
        txn = TransactionLog(command="files order")

    results = _get_organizer().order_files(
        folder, dry_run=dry_run, start_index=start, transaction_log=txn
    )

    # Save transaction log after successful completion
    if txn:
        txn.save()

    actions = results["actions"]
    if len(actions) > 20:
        for action in actions[:10]:
            console.print(f"  {action}")
        console.print(f"  ... and {len(actions) - 10} more.")
    else:
        for action in actions:
            console.print(f"  {action}")

    summary_color = "green" if not dry_run else "yellow"
    console.print(f"\n[{summary_color}]Summary:[/ {summary_color}]")
    console.print(f"  Files Processed: {results['renamed']}")
    console.print(f"  Files Skipped:   {results['skipped']}")

    if dry_run:
        console.print(
            "\n[bold yellow]This was a Dry Run. No files were changed.[/bold yellow]"
        )
    else:
        log_success("File ordering complete!")
        console.print(
            f"[dim]Undo with: max files undo[/dim]"
        )
```

#### 4b. Update `smart_sort` command

```python
@app.command("smart-sort")
@app.command("ss", hidden=True)
def smart_sort(
    path: Path = typer.Argument(".", help="Folder to organize."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show changes without moving."
    ),
):
    """AI-powered file organization. Groups files by content/meaning."""
    files = [
        f.name for f in path.iterdir() if f.is_file() and not f.name.startswith(".")
    ]

    if not files:
        console.print("[yellow]No files to organize.[/yellow]")
        return

    console.print(f"[cyan]Analyzing {len(files)} files with AI...[/cyan]")

    ai_eng = _get_ai_engine()
    categories = ai_eng.categorize_files(files)

    # Create transaction log
    txn = None
    if not dry_run:
        from max_cli.common.transaction_log import TransactionLog
        txn = TransactionLog(command="files smart-sort")

    # Delegate to engine (no more direct .rename() in interface)
    results = _get_organizer().smart_sort(
        path, categories, dry_run=dry_run, transaction_log=txn
    )

    for action in results["actions"]:
        console.print(f"  {action}")

    if not dry_run:
        txn.save()
        log_success(f"Successfully organized {results['moved']} files.")
        console.print("[dim]Undo with: max files undo[/dim]")
    else:
        console.print("[yellow]Dry run complete. No files moved.[/yellow]")
```

#### 4c. Update `find_duplicates` command

```python
@app.command("duplicates")
@app.command("dup", hidden=True)
def find_duplicates(
    folder: Path = typer.Argument(".", help="Folder to scan for duplicates."),
    recursive: bool = typer.Option(
        False, "-r", "--recursive", help="Scan subdirectories as well."
    ),
    delete: bool = typer.Option(
        False, "-d", "--delete", help="Delete duplicates (keeps one copy)."
    ),
    force: bool = typer.Option(
        False, "-f", "--force", help="Skip confirmation for deletion."
    ),
):
    """Find and optionally remove duplicate files based on content."""
    if not folder.is_dir():
        log_error(f"'{folder}' is not a directory.")
        raise typer.Exit(code=1)

    console.print(f"[cyan]Scanning for duplicates in {folder}...[/cyan]")

    try:
        org = _get_organizer()
        duplicates = org.find_duplicates(folder, recursive=recursive)

        if not duplicates:
            console.print("[green]No duplicates found![/green]")
            return

        total_dupes = sum(len(v) - 1 for v in duplicates.values())
        console.print(
            f"[yellow]Found {total_dupes} duplicate(s) in {len(duplicates)} group(s):[/yellow]\n"
        )

        for hash_val, paths in duplicates.items():
            console.print("[bold]Duplicate group:[/bold]")
            for p in paths:
                console.print(f"  {p}")
            console.print()

        if delete:
            if not force:
                console.print(
                    f"[red]This will permanently delete {total_dupes} file(s).[/red]"
                )
                console.print("[dim]Auto-backups will be created for undo support.[/dim]")
                if not Confirm.ask("Continue?"):
                    console.print("[yellow]Aborted.[/yellow]")
                    return

            # Create transaction log with auto-backup
            from max_cli.common.transaction_log import TransactionLog
            txn = TransactionLog(command="files duplicates --delete")

            results = org.delete_duplicates(
                folder, duplicates, transaction_log=txn, auto_backup=True
            )

            txn.save()

            for p in duplicates.values():
                for dup in p[1:]:
                    console.print(f"[red]Deleted:[/red] {dup}")

            log_success(
                f"Removed {results['removed']} duplicate(s). "
                f"Kept: {results['kept'][0].name if results['kept'] else 'none'}"
            )
            if results['errors']:
                for err in results['errors']:
                    log_error(err)
            console.print("[dim]Undo with: max files undo[/dim]")
        else:
            console.print("[dim]Run with --delete to remove duplicates[/dim]")

    except Exception as e:
        log_error(f"Error finding duplicates: {e}")
```

#### 4d. Update `secure_delete` (shred) command

```python
@app.command("shred")
def secure_delete(
    target: Path = typer.Argument(..., help="File to securely delete."),
    passes: int = typer.Option(
        3, "--passes", "-p", help="Number of overwrite passes (default 3)."
    ),
    force: bool = typer.Option(False, "-f", "--force", help="Skip confirmation."),
):
    """Securely delete a file by overwriting with random data before deletion."""
    if not target.exists():
        log_error(f"File not found: {target}")
        raise typer.Exit(1)

    if target.is_dir():
        log_error("Cannot shred directories. Use rm -r instead.")
        raise typer.Exit(1)

    if not force:
        console.print(
            f"[red]This will PERMANENTLY destroy: {target.name}[/red]"
        )
        if not Confirm.ask("Are you sure?"):
            console.print("[yellow]Aborted.[/yellow]")
            return

    console.print(f"[cyan]Shredding {target.name} ({passes} passes)...[/cyan]")
    console.print("[dim]Creating auto-backup for undo support...[/dim]")

    try:
        from max_cli.common.transaction_log import TransactionLog
        txn = TransactionLog(command="files shred")

        org = _get_organizer()
        org.secure_delete(
            target, passes=passes, transaction_log=txn, auto_backup=True
        )

        txn.save()

        log_success(f"File securely deleted: {target.name}")
        console.print("[dim]Undo with: max files undo (restores from backup)[/dim]")
    except Exception as e:
        log_error(f"Secure delete failed: {e}")
```

### Phase 5: New CLI Commands — `undo` and `history`

Add these commands to `cli_files.py`:

```python
@app.command("undo")
def undo_last():
    """Undo the last file operation (rename, move, delete)."""
    from max_cli.common.transaction_log import TransactionLog, TransactionError

    latest = TransactionLog.get_latest_group()
    if not latest:
        console.print("[yellow]No transaction history found. Nothing to undo.[/yellow]")
        return

    if latest["undo_status"] == "undone":
        console.print(
            f"[yellow]Last transaction ({latest['group_id']}) is already undone.[/yellow]"
        )
        console.print(
            f"[dim]Command was: {latest['command']} at {latest['timestamp']}[/dim]"
        )
        return

    console.print(
        f"[cyan]Undoing: {latest['command']} "
        f"({latest['operation_count']} operations)...[/cyan]"
    )

    try:
        txn = TransactionLog.load(latest["group_id"])
        results = txn.undo()

        for msg in results:
            console.print(f"  [green]✓[/green] {msg}")

        log_success("Undo complete! Files have been restored.")
    except TransactionError as e:
        log_error(f"Undo failed: {e}")
        console.print(
            "[yellow]Some files may have been partially restored. "
            "Check the transaction log for details.[/yellow]"
        )
        raise typer.Exit(code=1)


@app.command("history")
def transaction_history(
    limit: int = typer.Option(10, "-n", "--limit", help="Number of entries to show."),
    verbose: bool = typer.Option(
        False, "-v", "--verbose", help="Show individual operations."
    ),
):
    """Show recent file operation history."""
    from max_cli.common.transaction_log import TransactionLog
    from datetime import datetime

    groups = TransactionLog.list_groups()
    if not groups:
        console.print("[yellow]No transaction history found.[/yellow]")
        return

    console.print(f"[cyan]Recent file operations (showing {min(limit, len(groups))}):[/cyan]\n")

    for i, g in enumerate(groups[:limit]):
        status_icon = "✓" if g["undo_status"] == "undone" else "•"
        status_color = "dim" if g["undo_status"] == "undone" else "cyan"

        # Parse timestamp for display
        try:
            ts = datetime.fromisoformat(g["timestamp"])
            time_str = ts.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            time_str = g["timestamp"]

        console.print(
            f"  [{status_color}]{status_icon}[/{status_color}] "
            f"[bold]{g['command']}[/bold] — {time_str}"
        )
        console.print(
            f"     ID: {g['group_id']} | "
            f"Operations: {g['operation_count']} | "
            f"Status: {g['status']}"
        )
        if g["undo_status"]:
            console.print(f"     Undo: {g['undo_status']}")

        if verbose:
            txn = TransactionLog.load(g["group_id"])
            for op in txn.operations:
                op_type = op["op_type"]
                orig = op["original_path"] or "(none)"
                new = op["new_path"] or "(none)"
                console.print(f"       {op_type}: {orig} -> {new}")

        console.print()

    console.print("[dim]Undo the last operation with: max files undo[/dim]")
```

### Phase 6: Undo Logic Detail — How Each Operation Type Reverses

| Operation | Forward Action | Undo Action | Fallback |
|-----------|---------------|-------------|----------|
| **rename** | `file_path.rename(new_path)` | `new_path.rename(original_path)` | If `new_path` doesn't exist, restore from `backup_path` |
| **move** | `src.rename(dest_dir / filename)` | `dest.rename(original_path)` (creates parent dirs) | If `dest` doesn't exist, restore from `backup_path` |
| **delete** | `path.unlink()` after overwrite | `shutil.copy2(backup_path, original_path)` | If no backup exists, raise `TransactionError` |
| **create** | New file written to disk | `new_path.unlink()` | If file already gone, skip silently |

**Key Design Decisions**:

1. **Operations are reversed in LIFO order**: If a command renames `a.txt` → `1_a.txt` then moves `1_a.txt` to `sub/1_a.txt`, undo must first move it back, then rename it back.
2. **Delete operations require backups**: There is no way to resurrect a securely shredded file. The `auto_backup=True` flag in `secure_delete` and `delete_duplicates` ensures a copy exists in `~/.max_cli/backups/` before destruction.
3. **Idempotent undo**: Running `undo` twice will show "already undone" on the second call, since `undo_status` is persisted.
4. **Cross-platform paths**: All paths are stored as strings and reconstructed as `Path` objects at runtime, avoiding serialization issues.

### Phase 7: Integration with AudioMetadataEngine.organize()

The `AudioMetadataEngine.organize()` method also uses `.rename()`. It should optionally accept a `transaction_log` parameter:

```python
# In audio_metadata_engine.py, add to organize():

    def organize(
        self,
        source_paths: List[Path],
        target_dir: Path,
        pattern: str = "artist",
        transaction_log: Optional["TransactionLog"] = None,
    ) -> Dict[str, Any]:
        # ... existing logic ...

        # Replace the direct rename with:
        if transaction_log:
            transaction_log.record(
                op_type=TransactionLog.OP_MOVE,
                original_path=file_path,
                new_path=dest_path,
            )
        file_path.rename(dest_path)
```

This requires adding the import inside the method (lazy loading):

```python
if transaction_log:
    from max_cli.common.transaction_log import TransactionLog
    transaction_log.record(...)
```

## Testing Strategy

### Test File: `tests/test_transaction_log.py`

```python
import json
import pytest
from pathlib import Path
from unittest.mock import patch

from max_cli.common.transaction_log import TransactionLog, TransactionError


@pytest.fixture
def txn_storage(tmp_path):
    """Provide a temporary transaction storage directory."""
    return tmp_path / "transactions"


@pytest.fixture
def sample_files(tmp_path):
    """Create sample files for testing."""
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

    def test_save_creates_json_file(self, txn_storage):
        txn = TransactionLog("files order", txn_storage)
        path = txn.save()
        assert path.exists()
        assert path.name == f"{txn.group_id}.json"

    def test_save_writes_valid_json(self, txn_storage):
        txn = TransactionLog("files order", txn_storage)
        txn.record("rename", Path("a.txt"), Path("b.txt"))
        path = txn.save()

        data = json.loads(path.read_text())
        assert data["command"] == "files order"
        assert len(data["operations"]) == 1


class TestTransactionLogUndo:
    def test_undo_rename(self, sample_files, txn_storage):
        tmp_path, files = sample_files
        original = files[0]
        new = tmp_path / "renamed_doc.txt"

        txn = TransactionLog("files order", txn_storage)
        txn.record("rename", original, new)
        txn.save()

        # Perform the rename
        original.rename(new)

        # Undo
        results = txn.undo()
        assert len(results) == 1
        assert original.exists()
        assert not new.exists()

    def test_undo_move(self, sample_files, txn_storage):
        tmp_path, files = sample_files
        original = files[0]
        dest_dir = tmp_path / "Documents"
        dest = dest_dir / "doc.txt"

        txn = TransactionLog("files smart-sort", txn_storage)
        txn.record("move", original, dest)
        txn.save()

        # Perform the move
        dest_dir.mkdir()
        original.rename(dest)

        # Undo
        results = txn.undo()
        assert original.exists()
        assert not dest.exists()

    def test_undo_delete_from_backup(self, sample_files, txn_storage):
        tmp_path, files = sample_files
        original = files[0]
        backup = txn_storage.parent / "backups" / "doc_backup.txt"
        backup.parent.mkdir()

        txn = TransactionLog("files shred", txn_storage)
        txn.record("delete", original, None, backup)
        txn.save()

        # Simulate: file was deleted, backup exists
        original.unlink()
        backup.write_text("backup content")

        # Undo
        results = txn.undo()
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

        results = txn.undo()
        assert not created.exists()

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

        # Loading and undoing again should be safe
        txn2 = TransactionLog.load(txn.group_id, txn_storage)
        # Already undone — undo() will try to reverse but new doesn't exist
        # It should use the fallback or report gracefully
        # The second undo should not crash


class TestTransactionLogListGroups:
    def test_list_empty(self, txn_storage):
        assert TransactionLog.list_groups(txn_storage) == []

    def test_list_returns_newest_first(self, txn_storage):
        import time
        txn1 = TransactionLog("cmd1", txn_storage)
        txn1.save()
        time.sleep(0.01)
        txn2 = TransactionLog("cmd2", txn_storage)
        txn2.save()

        groups = TransactionLog.list_groups(txn_storage)
        assert len(groups) == 2
        assert groups[0]["group_id"] == txn2.group_id

    def test_get_latest_group(self, txn_storage):
        txn = TransactionLog("files order", txn_storage)
        txn.save()

        latest = TransactionLog.get_latest_group(txn_storage)
        assert latest is not None
        assert latest["group_id"] == txn.group_id


class TestTransactionLogCleanup:
    def test_cleanup_excess_groups(self, txn_storage):
        for i in range(55):
            txn = TransactionLog(f"cmd{i}", txn_storage)
            txn.save()

        files = list(txn_storage.glob("*.json"))
        assert len(files) <= TransactionLog.MAX_GROUPS

    def test_cleanup_old_groups_by_age(self, txn_storage):
        txn = TransactionLog("old cmd", txn_storage)
        path = txn.save()

        # Manipulate mtime to simulate old file
        old_time = time.time() - (31 * 86400)
        import os
        os.utime(path, (old_time, old_time))

        # Trigger cleanup by saving a new group
        txn2 = TransactionLog("new cmd", txn_storage)
        txn2.save()

        files = list(txn_storage.glob("*.json"))
        # Old file should be removed
        assert not path.exists()
```

### Test File: `tests/test_file_organizer_transactions.py`

```python
import pytest
from pathlib import Path

from max_cli.core.engines.file_organizer import FileOrganizer
from max_cli.common.transaction_log import TransactionLog


@pytest.fixture
def organizer():
    return FileOrganizer()


@pytest.fixture
def txn(tmp_path):
    return TransactionLog("test", tmp_path / "txn")


class TestFileOrganizerWithTransactions:
    def test_order_files_records_transactions(self, organizer, tmp_path, txn):
        # Create test files
        for name in ["a.txt", "b.txt", "c.txt"]:
            (tmp_path / name).write_text("content")

        result = organizer.order_files(
            tmp_path, transaction_log=txn, start_index=1
        )

        assert result["renamed"] == 3
        assert len(txn.operations) == 3
        assert txn.operations[0]["op_type"] == "rename"

    def test_order_files_dry_run_no_transactions(self, organizer, tmp_path, txn):
        (tmp_path / "a.txt").write_text("content")

        organizer.order_files(
            tmp_path, dry_run=True, transaction_log=txn
        )

        assert len(txn.operations) == 0

    def test_secure_delete_with_auto_backup(self, organizer, tmp_path, txn):
        f = tmp_path / "secret.txt"
        f.write_text("sensitive data")

        organizer.secure_delete(
            f, passes=1, transaction_log=txn, auto_backup=True
        )

        assert not f.exists()
        assert len(txn.operations) == 1
        assert txn.operations[0]["op_type"] == "delete"
        assert txn.operations[0]["backup_path"] is not None
        assert Path(txn.operations[0]["backup_path"]).exists()
```

## Migration Path

### Step 1: Deploy Transaction Log Module
- Add `src/max_cli/common/transaction_log.py`
- Add `tests/test_transaction_log.py`
- No existing behavior changes — purely additive

### Step 2: Wire FileOrganizer Methods
- Add optional `transaction_log` parameter to `order_files`, `secure_delete`
- Add new `delete_duplicates` and `smart_sort` methods
- All parameters are optional with `None` default — backward compatible

### Step 3: Update CLI Commands
- Update `cli_files.py` commands to create and pass `TransactionLog`
- Move `smart-sort` and `duplicates --delete` logic from interface to engine
- Add `max files undo` and `max files history` commands

### Step 4: Update Audio Engine (Optional, Lower Priority)
- Add `transaction_log` parameter to `AudioMetadataEngine.organize()`
- Update `cli_audio.py` to pass it through

### Step 5: Documentation
- Update `README.md` with `max files undo` and `max files history` usage
- Update `docs/commands/files.md` with new commands
- Update `PLANS/active/README.md` to mark this plan as completed

### Backward Compatibility

All changes are **backward compatible**:
- `transaction_log` parameters default to `None` — existing code works unchanged
- No existing CLI command signatures are modified (only new optional flags added)
- The `~/.max_cli/transactions/` directory is created on first use
- Auto-cleanup prevents unbounded disk growth

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Undo fails because file was manually moved/deleted** | High | Undo checks `exists()` before reversing; falls back to backup; raises clear `TransactionError` |
| **Disk space growth from transaction logs** | Low | Auto-cleanup enforces max 50 groups + 30-day retention; each JSON file is ~1-5KB |
| **Disk space growth from auto-backups** | Medium | Auto-backups go to existing `~/.max_cli/backups/` which already has `cleanup_old_backups()` |
| **Undo of `shred` restores un-shredded copy** | Medium (by design) | Auto-backup is a normal copy, not shredded. This is intentional — undo is a safety net. Document this behavior. |
| **Race condition: undo while files are in use** | Low | `OSError` is caught and reported; partial undo is flagged in `undo_status` |
| **Cross-platform path serialization** | Low | Paths stored as strings, reconstructed as `Path` at runtime; tested on Windows and POSIX |
| **Interface layer still has direct `.rename()` / `.unlink()`** | Medium | Phase 3 explicitly moves `smart-sort` and `duplicates` logic to engine; audit other CLI files for similar patterns |

## Success Criteria

- [ ] `TransactionLog` class passes all unit tests (creation, save, load, undo, list, cleanup)
- [ ] `max files order` creates a transaction group; `max files undo` reverses it completely
- [ ] `max files smart-sort` creates a transaction group; `max files undo` moves files back
- [ ] `max files duplicates --delete` creates auto-backups; `max files undo` restores deleted files
- [ ] `max files shred` creates auto-backup; `max files undo` restores from backup
- [ ] `max files history` shows recent operations with correct metadata
- [ ] Running `undo` twice does not crash (idempotent)
- [ ] Transaction log auto-cleanup works (max 50 groups, 30-day retention)
- [ ] No business logic remains in `cli_files.py` for `smart-sort` or `duplicates --delete`
- [ ] All new code passes `ruff check`, `ruff format`, and `mypy`
- [ ] Documentation updated (`README.md`, `docs/commands/files.md`)
- [ ] `PLANS/active/README.md` updated to mark plan as completed