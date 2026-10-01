"""`max files` operations: renames, moves, deletes and backups, with undo records.

The CLI, the dashboard and the agent call these through the catalog
(`core/catalog/groups/files.py`). They never prompt or print: callers ask
first, based on the action's `danger` (the CLI's own prompts and --force stay
in the CLI). Every operation that changes files records it in a
TransactionLog and returns its id as `ActionResult.undo_group`, so
`max files undo` can reverse it. `shred` is the exception: a secure delete
must not leave a copy.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from max_cli.common.exceptions import ResourceNotFoundError, ValidationError
from max_cli.core.operations.result import ActionResult

if TYPE_CHECKING:
    from max_cli.common.transaction_log import TransactionLog
    from max_cli.core.engines.ai_engine import AIEngine
    from max_cli.core.engines.file_organizer import FileOrganizer

DEFAULT_SHRED_PASSES = 3
DEFAULT_PREVIEW_LINES = 20
DEFAULT_BACKUP_DAYS = 30
DEFAULT_HISTORY_LIMIT = 10
TEXT_EXTENSIONS = frozenset(
    {
        ".txt",
        ".md",
        ".py",
        ".js",
        ".json",
        ".yaml",
        ".yml",
        ".xml",
        ".html",
        ".css",
        ".sh",
        ".bat",
        ".ps1",
        ".ini",
        ".cfg",
        ".conf",
        ".log",
    }
)
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"})


def _organizer(organizer: Optional["FileOrganizer"]) -> "FileOrganizer":
    if organizer is not None:
        return organizer
    from max_cli.core.engines.file_organizer import FileOrganizer

    return FileOrganizer()


def _require_folder(folder: Path) -> None:
    if not folder.is_dir():
        raise ValidationError(f"'{folder}' is not a directory.")


def _transaction(command: str, dry_run: bool = False) -> Optional["TransactionLog"]:
    if dry_run:
        return None
    from max_cli.common.transaction_log import TransactionLog

    return TransactionLog(command=command)


def _saved_group(txn: Optional["TransactionLog"]) -> Optional[str]:
    if txn is None:
        return None
    txn.save()
    return txn.group_id


# --- order ---------------------------------------------------------------


def files_to_order(
    folder: Path, *, organizer: Optional["FileOrganizer"] = None
) -> list[Path]:
    """The files `order` would look at, so a caller can show them before asking."""
    _require_folder(folder)
    return _organizer(organizer).scan_directory(folder)


def order(
    folder: Path,
    dry_run: bool = False,
    start: int = 1,
    *,
    organizer: Optional["FileOrganizer"] = None,
) -> ActionResult:
    """Prefix each file with a number (1_name.txt). Numbered files are skipped."""
    if not files_to_order(folder, organizer=organizer):
        return ActionResult(
            True,
            "Folder is empty. Nothing to do.",
            details={"actions": [], "renamed": 0, "skipped": 0, "dry_run": dry_run},
        )
    txn = _transaction("files order", dry_run)
    results = _organizer(organizer).order_files(
        folder, dry_run=dry_run, start_index=start, transaction_log=txn
    )
    return ActionResult(
        True,
        "Dry run: no files were changed." if dry_run else "File ordering complete!",
        details={
            "actions": results["actions"],
            "renamed": results["renamed"],
            "skipped": results["skipped"],
            "dry_run": dry_run,
        },
        undo_group=_saved_group(txn),
    )


# --- smart-sort ------------------------------------------------------------


def smart_sort(
    path: Path = Path("."),
    dry_run: bool = False,
    *,
    organizer: Optional["FileOrganizer"] = None,
    ai_engine: Optional["AIEngine"] = None,
) -> ActionResult:
    """Ask the AI for a category per file, then move files into those folders."""
    _require_folder(path)
    files = [
        entry.name
        for entry in path.iterdir()
        if entry.is_file() and not entry.name.startswith(".")
    ]
    if not files:
        return ActionResult(
            True,
            "No files to organize.",
            details={"actions": [], "moved": 0, "dry_run": dry_run},
        )
    if ai_engine is None:
        from max_cli.core.engines.ai_engine import AIEngine

        ai_engine = AIEngine()
    categories = ai_engine.categorize_files(files)
    txn = _transaction("files smart-sort", dry_run)
    results = _organizer(organizer).smart_sort(
        path, categories, dry_run=dry_run, transaction_log=txn
    )
    message = (
        "Dry run complete. No files moved."
        if dry_run
        else f"Successfully organized {results['moved']} files."
    )
    return ActionResult(
        True,
        message,
        details={
            "actions": results["actions"],
            "moved": results["moved"],
            "dry_run": dry_run,
        },
        undo_group=_saved_group(txn),
    )


# --- duplicates ------------------------------------------------------------


def find_duplicates(
    folder: Path,
    recursive: bool = False,
    *,
    organizer: Optional["FileOrganizer"] = None,
) -> dict[str, list[Path]]:
    """Groups of identical files, keyed by content hash."""
    _require_folder(folder)
    return _organizer(organizer).find_duplicates(folder, recursive=recursive)


def duplicates(
    folder: Path = Path("."),
    recursive: bool = False,
    delete: bool = False,
    *,
    organizer: Optional["FileOrganizer"] = None,
    groups: Optional[dict[str, list[Path]]] = None,
) -> ActionResult:
    """Find duplicate files; with delete, keep one of each and back up the rest.

    Pass `groups` from find_duplicates() to skip hashing the folder again.
    """
    file_organizer = _organizer(organizer)
    if groups is None:
        groups = find_duplicates(folder, recursive, organizer=file_organizer)
    duplicate_count = sum(len(paths) - 1 for paths in groups.values())
    details: dict[str, Any] = {
        "groups": [[str(path) for path in paths] for paths in groups.values()],
        "duplicate_count": duplicate_count,
        "removed": 0,
        "errors": [],
    }
    if not groups:
        return ActionResult(True, "No duplicates found!", details=details)
    if not delete:
        return ActionResult(
            True,
            f"Found {duplicate_count} duplicate(s) in {len(groups)} group(s)",
            details=details,
        )
    txn = _transaction("files duplicates --delete")
    results = file_organizer.delete_duplicates(
        folder, groups, transaction_log=txn, auto_backup=True
    )
    details.update(removed=results["removed"], errors=results["errors"])
    return ActionResult(
        True,
        f"Removed {results['removed']} duplicate(s).",
        details=details,
        undo_group=_saved_group(txn),
    )


# --- shred -----------------------------------------------------------------


def check_shred_target(target: Path) -> None:
    """Raise unless `target` is a file shred can destroy. Callers check before asking."""
    if not target.exists():
        raise ResourceNotFoundError(f"File not found: {target}")
    if target.is_dir():
        raise ValidationError("Cannot shred directories. Use rm -r instead.")


def shred(
    target: Path,
    passes: int = DEFAULT_SHRED_PASSES,
    *,
    organizer: Optional["FileOrganizer"] = None,
) -> ActionResult:
    """Overwrite a file with random data, then delete it. No backup, no undo."""
    check_shred_target(target)
    if passes < 1:
        raise ValidationError("Passes must be at least 1.")
    _organizer(organizer).secure_delete(target, passes=passes)
    return ActionResult(True, f"File securely deleted: {target.name}")


# --- preview ---------------------------------------------------------------


def _text_preview(target: Path, lines: int) -> dict[str, Any]:
    try:
        content_lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError as e:
        return {"note": f"Could not read file content: {e}"}
    return {
        "lines": content_lines[:lines],
        "more_lines": max(0, len(content_lines) - lines),
    }


def _image_preview(target: Path) -> dict[str, Any]:
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(target) as img:
            return {
                "image": {"width": img.width, "height": img.height, "mode": img.mode}
            }
    except (OSError, UnidentifiedImageError):
        return {"note": "Could not read image info"}


def _pdf_preview(target: Path) -> dict[str, Any]:
    import fitz

    try:
        with fitz.open(target) as doc:
            metadata = doc.metadata or {}
            return {
                "pdf": {
                    "pages": doc.page_count,
                    "title": metadata.get("title") or "N/A",
                    "author": metadata.get("author") or "N/A",
                }
            }
    except (OSError, RuntimeError, ValueError):  # fitz raises RuntimeError subclasses
        return {"note": "Could not read PDF info"}


def preview(target: Path, lines: int = DEFAULT_PREVIEW_LINES) -> ActionResult:
    """A file's metadata, plus its first lines, image size or PDF info."""
    if not target.exists():
        raise ResourceNotFoundError(f"File not found: {target}")
    stat = target.stat()
    suffix = target.suffix.lower()
    details: dict[str, Any] = {
        "name": target.name,
        "path": str(target.absolute()),
        "type": target.suffix or "No extension",
        "size": stat.st_size,
        "created": datetime.fromtimestamp(stat.st_ctime).isoformat(" "),
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(" "),
        "accessed": datetime.fromtimestamp(stat.st_atime).isoformat(" "),
    }
    if suffix in TEXT_EXTENSIONS:
        details.update(_text_preview(target, lines))
    elif suffix in IMAGE_EXTENSIONS:
        details.update(_image_preview(target))
    elif suffix == ".pdf":
        details.update(_pdf_preview(target))
    else:
        details["note"] = "Preview not available for this file type"
    return ActionResult(True, target.name, details=details)


# --- backups ---------------------------------------------------------------


def backup(
    target: Path,
    label: str = "manual",
    *,
    organizer: Optional["FileOrganizer"] = None,
) -> ActionResult:
    if not target.exists():
        raise ResourceNotFoundError(f"File not found: {target}")
    backup_path = _organizer(organizer).create_backup(target, label=label)
    return ActionResult(True, f"Backup created: {backup_path}", [backup_path])


def backups(
    filter: Optional[str] = None,
    restore: Optional[Path] = None,
    output: Optional[Path] = None,
    *,
    organizer: Optional["FileOrganizer"] = None,
) -> ActionResult:
    """List backups (optionally by file name), or restore one."""
    file_organizer = _organizer(organizer)
    if restore is not None:
        restored = file_organizer.restore_backup(restore, output)
        return ActionResult(True, f"Restored: {restored}", [restored])
    found = file_organizer.list_backups(filter)
    listed = [
        {
            "name": entry["name"],
            "size": entry["size"],
            "created": datetime.fromtimestamp(entry["created"]).isoformat(" "),
            "path": str(entry["path"]),
        }
        for entry in found
    ]
    message = f"Found {len(listed)} backup(s)" if listed else "No backups found."
    return ActionResult(True, message, details={"backups": listed})


def backup_cleanup(
    days: int = DEFAULT_BACKUP_DAYS,
    *,
    organizer: Optional["FileOrganizer"] = None,
) -> ActionResult:
    if days < 0:
        raise ValidationError("Days must be 0 or more.")
    removed = _organizer(organizer).cleanup_old_backups(days)
    return ActionResult(
        True, f"Removed {removed} old backup(s)", details={"removed": removed}
    )


# --- undo and history --------------------------------------------------------


def undo() -> ActionResult:
    """Reverse the latest recorded file operation.

    Raises TransactionError when a step fails; some files may be restored.
    """
    from max_cli.common.transaction_log import TransactionLog

    latest = TransactionLog.get_latest_group()
    if not latest:
        return ActionResult(True, "No transaction history found. Nothing to undo.")
    summary = {"command": latest["command"], "timestamp": latest["timestamp"]}
    if latest["undo_status"] == "undone":
        return ActionResult(
            True,
            f"Last transaction ({latest['group_id']}) is already undone.",
            details=summary,
        )
    steps = TransactionLog.load(latest["group_id"]).undo()
    return ActionResult(
        True,
        "Undo complete! Files have been restored.",
        details={**summary, "steps": steps},
        undo_group=latest["group_id"],
    )


def history(limit: int = DEFAULT_HISTORY_LIMIT, verbose: bool = False) -> ActionResult:
    """Recent file operations, newest first; verbose adds each step."""
    from max_cli.common.transaction_log import TransactionLog

    groups = TransactionLog.list_groups()[: max(0, limit)]
    entries = []
    for group in groups:
        entry = {
            key: group[key]
            for key in (
                "group_id",
                "command",
                "timestamp",
                "operation_count",
                "status",
                "undo_status",
            )
        }
        if verbose:
            entry["operations"] = [
                {
                    "op_type": step["op_type"],
                    "original_path": step["original_path"],
                    "new_path": step["new_path"],
                }
                for step in TransactionLog.load(group["group_id"]).operations
            ]
        entries.append(entry)
    message = (
        f"Recent file operations (showing {len(entries)})"
        if entries
        else "No transaction history found."
    )
    return ActionResult(True, message, details={"groups": entries})


# --- describing a file or folder (the dashboard's Files page) ----------------

ORGANIZE_NOTE = "Organize actions work on the files directly in this folder."
EMPTY_FOLDER_NOTE = "This folder holds no files, only what its subfolders hold."


@dataclass
class PathFacts:
    """What a file, or a folder's own files, are, for the Files page."""

    path: Path
    size_bytes: int  # the file, or the folder's own files together
    is_folder: bool = False
    kind: str = ""  # a file's kind: file_kinds.VIDEO, PDF ...
    modified: Optional[datetime] = None
    # a folder: its own files, not those in subfolders
    file_count: int = 0
    folder_count: int = 0
    kinds: dict[str, int] = field(default_factory=dict)  # kind -> count, largest first
    biggest: Optional[Path] = None
    biggest_bytes: int = 0
    note: str = ""


def describe(target: Path) -> PathFacts:
    """A file's kind, size and date; for a folder, how many files and
    subfolders it holds, its files' total size, their kinds and the biggest."""
    from max_cli.common.file_kinds import kind_of

    target = Path(target).expanduser()
    if not target.exists():
        raise ResourceNotFoundError(f"Not found: {target}")
    if target.is_file():
        info = target.stat()
        return PathFacts(
            path=target,
            size_bytes=info.st_size,
            kind=kind_of(target),
            modified=datetime.fromtimestamp(info.st_mtime),
        )
    files: list[tuple[Path, int]] = []
    folder_count = 0
    for child in target.iterdir():
        try:
            if child.is_dir():
                folder_count += 1
            elif child.is_file():
                files.append((child, child.stat().st_size))
        except OSError:
            continue  # vanished, or a broken link
    kinds = Counter(kind_of(path) for path, _size in files)
    biggest = max(files, key=lambda item: item[1], default=None)
    return PathFacts(
        path=target,
        size_bytes=sum(size for _path, size in files),
        is_folder=True,
        file_count=len(files),
        folder_count=folder_count,
        kinds=dict(kinds.most_common()),
        biggest=biggest[0] if biggest else None,
        biggest_bytes=biggest[1] if biggest else 0,
        note=ORGANIZE_NOTE if files else EMPTY_FOLDER_NOTE,
    )
