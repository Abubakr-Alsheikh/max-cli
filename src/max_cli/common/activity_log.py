import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from max_cli.common.atomic import atomic_write_json
from max_cli.common.file_lock import FileLock
from max_cli.common.retry import retry

logger = logging.getLogger(__name__)

# Windows refuses to read a file another thread is replacing, and to replace
# one another thread is reading: the AI page's worker logs while the app's
# badge refresh reads. A short wait clears it.
FILE_ATTEMPTS = 5
FILE_RETRY_SECONDS = 0.05
# Several processes write the log (the dashboard, CLI commands, the queue
# worker): each save waits this long for the others.
LOCK_SECONDS = 5


@retry(
    max_attempts=FILE_ATTEMPTS, delay=FILE_RETRY_SECONDS, exceptions=(PermissionError,)
)
def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@retry(
    max_attempts=FILE_ATTEMPTS, delay=FILE_RETRY_SECONDS, exceptions=(PermissionError,)
)
def _write_json(path: Path, data: Any) -> None:
    atomic_write_json(path, data)


# `max grab` downloads log under the command group name "grab", while the
# Home card, the History filter and get_stats() count them as "download".
CATEGORY_ALIASES = {"grab": "download"}


class ActivityEntry:
    def __init__(
        self,
        category: str,
        action: str,
        status: str = "pending",
        details: Optional[dict[str, Any]] = None,
        duration_ms: int = 0,
        entry_id: Optional[str] = None,
    ):
        self.id = entry_id or str(uuid.uuid4())[:8]
        self.timestamp = datetime.now().isoformat()
        self.category = CATEGORY_ALIASES.get(category, category)
        self.action = action
        self.status = status
        self.details = details or {}
        self.duration_ms = duration_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "category": self.category,
            "action": self.action,
            "status": self.status,
            "details": self.details,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActivityEntry":
        entry = cls(
            category=data["category"],
            action=data["action"],
            status=data.get("status", "pending"),
            details=data.get("details", {}),
            duration_ms=data.get("duration_ms", 0),
            entry_id=data.get("id"),
        )
        entry.timestamp = data.get("timestamp", entry.timestamp)
        return entry


class ActivityLog:
    LOG_FILE = Path.home() / ".max_cli" / "activity_log.json"
    MAX_ENTRIES = 500

    def __init__(self):
        self._entries: list[ActivityEntry] = []
        # A log that couldn't be read must never save: it would write its
        # empty list over the whole history.
        self._readable = True
        # What this instance added or changed: a save merges only these into
        # what's on disk, so writers in other processes and threads keep
        # their entries.
        self._changed: dict[str, ActivityEntry] = {}
        self._cleared = False
        self._load()

    def _ensure_dir(self) -> None:
        self.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        self._entries = self._read() or []

    def _read(self) -> Optional[list["ActivityEntry"]]:
        """The entries on disk; None when the file can't be read."""
        if not self.LOG_FILE.exists():
            return []
        try:
            data = json.loads(_read_text(self.LOG_FILE))
            return [ActivityEntry.from_dict(e) for e in data]
        except (json.JSONDecodeError, KeyError, TypeError):
            return []
        except PermissionError:
            logger.warning("Activity log locked; this change won't be logged")
            self._readable = False
            return None

    def _mark(self, entry: "ActivityEntry") -> None:
        self._changed[entry.id] = entry
        self._save()

    def _save(self) -> None:
        """Merge this instance's changes into the log on disk and write it.
        Skipped when the file stays locked: the log is a record, and failing
        here stopped the work that was being logged."""
        if not self._readable:
            return
        self._ensure_dir()
        lock = FileLock(self.LOG_FILE.with_name(self.LOG_FILE.stem + ".lock"))
        if not lock.acquire(timeout=LOCK_SECONDS):
            logger.warning("Activity log busy; this change wasn't saved")
            return
        try:
            on_disk = self._read()
            if on_disk is None:
                return
            if self._cleared:
                on_disk = []
            merged = {entry.id: entry for entry in on_disk}
            merged.update(self._changed)
            self._entries = sorted(
                merged.values(), key=lambda entry: entry.timestamp, reverse=True
            )[: self.MAX_ENTRIES]
            _write_json(self.LOG_FILE, [e.to_dict() for e in self._entries])
            self._changed = {}
            self._cleared = False
        except PermissionError:
            logger.warning("Activity log locked; this change wasn't saved")
        finally:
            lock.release()

    def start_entry(
        self,
        category: str,
        action: str,
        details: Optional[dict[str, Any]] = None,
    ) -> ActivityEntry:
        entry = ActivityEntry(category=category, action=action, details=details)
        self._entries.insert(0, entry)
        self._mark(entry)
        return entry

    def complete_entry(
        self,
        entry: ActivityEntry,
        status: str,
        result: Optional[dict[str, Any]] = None,
    ) -> None:
        entry.status = status
        if result:
            entry.details.update(result)
        self._mark(entry)

    def add_entry(
        self,
        category: str,
        action: str,
        status: str,
        details: Optional[dict[str, Any]] = None,
        duration_ms: int = 0,
    ) -> ActivityEntry:
        entry = ActivityEntry(
            category=category,
            action=action,
            status=status,
            details=details,
            duration_ms=duration_ms,
        )
        self._entries.insert(0, entry)
        self._mark(entry)
        return entry

    def get_entry(self, entry_id: str) -> Optional[ActivityEntry]:
        for entry in self._entries:
            if entry.id == entry_id:
                return entry
        return None

    def get_entries(
        self,
        limit: int = 100,
        category_filter: Optional[str] = None,
        status_filter: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> list[ActivityEntry]:
        entries = self._entries
        if category_filter and category_filter != "all":
            entries = [e for e in entries if e.category == category_filter]
        if status_filter and status_filter != "all":
            entries = [e for e in entries if e.status == status_filter]
        if date_from:
            entries = [e for e in entries if e.timestamp >= date_from]
        if date_to:
            entries = [e for e in entries if e.timestamp <= date_to]
        return entries[:limit]

    def get_stats(self) -> dict[str, Any]:
        stats: dict[str, int] = {
            "total": len(self._entries),
            "success": 0,
            "failed": 0,
            "download": 0,
            "task": 0,
            "file_op": 0,
            "command": 0,
            "ai": 0,
        }
        for entry in self._entries:
            if entry.status == "success":
                stats["success"] += 1
            elif entry.status == "failed":
                stats["failed"] += 1
            if entry.category in stats:
                stats[entry.category] += 1
        return stats

    def clear(self) -> int:
        count = len(self._entries)
        self._entries = []
        self._changed = {}
        self._cleared = True
        self._save()
        return count
