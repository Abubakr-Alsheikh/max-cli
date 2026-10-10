"""What the agent's last request changed, so "undo what you just did" can put
it back: the files it made, the change groups it recorded (moves, renames,
deletes) and the actions that changed files in place with no record.

The record lives in `~/.max_cli/agent_last_request.json`, so `max ai undo`
or a later session can still undo it. Undo moves the files the request made
into Max's backups (so the undo can be undone by hand), reverses the change
groups newest first, and leaves alone any file changed since: its size or
time no longer matches.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from max_cli.common.atomic import atomic_write_json

RECORD_FILE_NAME = "agent_last_request.json"
UNDO_BACKUP_DIR = "agent-undo"
MAX_SHOWN = 5


def record_file() -> Path:
    return Path.home() / ".max_cli" / RECORD_FILE_NAME


@dataclass(frozen=True)
class MadeFile:
    path: str
    size: int
    modified: float

    @classmethod
    def of(cls, path: Path) -> Optional["MadeFile"]:
        try:
            info = path.stat()
        except OSError:
            return None
        if not path.is_file():
            return None
        return cls(str(path), info.st_size, info.st_mtime)

    def unchanged(self) -> bool:
        try:
            info = Path(self.path).stat()
        except OSError:
            return False
        return info.st_size == self.size and abs(info.st_mtime - self.modified) < 1


@dataclass
class RequestChanges:
    """What one request changed. `in_place` names actions that changed files
    in place and left no record to undo (audio tags, for example)."""

    request: str
    at: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    made: list[MadeFile] = field(default_factory=list)
    undo_groups: list[str] = field(default_factory=list)
    in_place: list[str] = field(default_factory=list)

    def any(self) -> bool:
        return bool(self.made or self.undo_groups or self.in_place)

    def describe(self) -> str:
        """`2 changes it recorded and 140 files it made (a.mp3, b.mp3 ...)`."""
        parts = []
        if self.undo_groups:
            count = len(self.undo_groups)
            parts.append(f"{count} file change{'s' if count != 1 else ''} it recorded")
        if self.made:
            names = ", ".join(Path(made.path).name for made in self.made[:3])
            more = " ..." if len(self.made) > 3 else ""
            count = len(self.made)
            parts.append(
                f"{count} file{'s' if count != 1 else ''} it made ({names}{more})"
            )
        return " and ".join(parts) or "nothing that can be undone"


def save(changes: RequestChanges) -> None:
    path = record_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, asdict(changes))


def load() -> Optional[RequestChanges]:
    try:
        data = json.loads(record_file().read_text(encoding="utf-8"))
        return RequestChanges(
            request=str(data["request"]),
            at=str(data.get("at", "")),
            made=[MadeFile(**item) for item in data.get("made", [])],
            undo_groups=[str(group) for group in data.get("undo_groups", [])],
            in_place=[str(name) for name in data.get("in_place", [])],
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None


def forget() -> None:
    record_file().unlink(missing_ok=True)


@dataclass
class UndoReport:
    moved: list[str] = field(default_factory=list)  # files made, now in backups
    kept: list[str] = field(default_factory=list)  # changed since: left alone
    reversed_groups: int = 0
    failed: list[str] = field(default_factory=list)
    backup_folder: str = ""
    in_place: list[str] = field(default_factory=list)

    def message(self) -> str:
        parts = []
        if self.moved:
            parts.append(
                f"Moved {len(self.moved)} file{'s' if len(self.moved) != 1 else ''} "
                f"it made to {self.backup_folder}"
            )
        if self.reversed_groups:
            parts.append(
                f"reversed {self.reversed_groups} recorded change"
                f"{'s' if self.reversed_groups != 1 else ''}"
            )
        if self.kept:
            parts.append(
                f"left {len(self.kept)} file{'s' if len(self.kept) != 1 else ''} "
                f"that changed since ({', '.join(self.kept[:MAX_SHOWN])})"
            )
        if self.in_place:
            parts.append(
                "can't undo what these changed in place: " + ", ".join(self.in_place)
            )
        if self.failed:
            parts.append("failed: " + "; ".join(self.failed[:MAX_SHOWN]))
        text = "; ".join(parts) or "Nothing to undo"
        return text[0].upper() + text[1:] + "."


def undo(changes: RequestChanges) -> UndoReport:
    """Put back what `changes` did, then forget the record."""
    import shutil

    from max_cli.common.transaction_log import TransactionError, TransactionLog

    report = UndoReport(in_place=list(changes.in_place))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = Path.home() / ".max_cli" / "backups" / UNDO_BACKUP_DIR / stamp
    for made in changes.made:
        path = Path(made.path)
        if not path.exists():
            continue
        if not made.unchanged():
            report.kept.append(path.name)
            continue
        target = backup / path.name
        counter = 1
        while target.exists():
            target = backup / f"{path.stem} ({counter}){path.suffix}"
            counter += 1
        try:
            backup.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(target))
        except OSError as e:
            report.failed.append(f"{path.name}: {e}")
            continue
        report.moved.append(path.name)
    if report.moved:
        report.backup_folder = str(backup)
    undone = {
        group["group_id"]
        for group in TransactionLog.list_groups()
        if group.get("undo_status") == "undone"
    }
    for group_id in reversed(changes.undo_groups):
        if group_id in undone:
            continue
        try:
            TransactionLog.load(group_id).undo()
        except (TransactionError, OSError, ValueError) as e:
            report.failed.append(f"change {group_id}: {e}")
            continue
        report.reversed_groups += 1
    forget()
    return report
