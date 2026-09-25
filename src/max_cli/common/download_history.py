"""Persistent download history tracker with duplicate detection."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from max_cli.common.atomic import atomic_write_json


class DownloadHistory:
    """Thread-safe singleton tracking downloaded URLs, output dirs, and settings."""

    _instance: Optional["DownloadHistory"] = None
    _lock = threading.Lock()

    MAX_ENTRIES = 200
    STORAGE_FILE = Path.home() / ".max_cli" / "download_history.json"

    def __new__(cls) -> "DownloadHistory":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._data_lock = threading.Lock()
        self._data: dict[str, Any] = {
            "downloads": [],
            "last_output": {},
            "last_settings": {},
        }
        self._load()
        self._initialized = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_download(
        self,
        url: str,
        title: str = "",
        output_files: list[str] | None = None,
        settings_used: dict | None = None,
        file_size: int = 0,
        status: str = "completed",
    ) -> None:
        """Record a completed download, deduplicating by URL."""
        domain = urlparse(url).netloc
        entry = {
            "url": url,
            "title": title,
            "domain": domain,
            "timestamp": datetime.now().isoformat(),
            "output_files": output_files or [],
            "settings": settings_used or {},
            "file_size": file_size,
            "status": status,
        }

        with self._data_lock:
            self._data["downloads"] = [
                d for d in self._data["downloads"] if d.get("url") != url
            ]
            self._data["downloads"].insert(0, entry)

            while len(self._data["downloads"]) > self.MAX_ENTRIES:
                self._data["downloads"].pop()

            if output_files:
                parent = str(Path(output_files[0]).parent)
                self._data["last_output"][domain] = parent

            if settings_used:
                self._data["last_settings"].update(settings_used)

            self._save()

    def is_already_downloaded(self, url: str) -> dict | None:
        """Return the entry dict if *url* was downloaded before, else None."""
        with self._data_lock:
            for entry in self._data["downloads"]:
                if entry.get("url") == url:
                    return entry
        return None

    def get_last_output_path(self, url: str) -> str | None:
        """Return last output directory for the domain of *url*, or None."""
        domain = urlparse(url).netloc
        with self._data_lock:
            return self._data["last_output"].get(domain)

    def get_last_settings(self) -> dict:
        """Return a copy of the last used download settings."""
        with self._data_lock:
            return dict(self._data["last_settings"])

    def get_recent(self, limit: int = 20) -> list[dict]:
        """Return the most recent *limit* download entries."""
        with self._data_lock:
            return list(self._data["downloads"][:limit])

    def get_stats(self) -> dict:
        """Return aggregate statistics."""
        with self._data_lock:
            downloads = self._data["downloads"]
            completed = sum(1 for d in downloads if d.get("status") == "completed")
            failed = sum(1 for d in downloads if d.get("status") == "failed")
            total_size = sum(d.get("file_size", 0) for d in downloads)
            unique_domains = len(
                {d.get("domain") for d in downloads if d.get("domain")}
            )
            return {
                "total": len(downloads),
                "completed": completed,
                "failed": failed,
                "total_size": total_size,
                "unique_domains": unique_domains,
            }

    def clear_history(self) -> int:
        """Clear all download entries and return the number removed."""
        with self._data_lock:
            count = len(self._data["downloads"])
            self._data["downloads"] = []
            self._save()
        return count

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load data from the JSON file, silently starting fresh on errors."""
        try:
            if self.STORAGE_FILE.exists():
                raw = self.STORAGE_FILE.read_text(encoding="utf-8")
                data = json.loads(raw)
                self._data["downloads"] = data.get("downloads", [])
                self._data["last_output"] = data.get("last_output", {})
                self._data["last_settings"] = data.get("last_settings", {})
        except (json.JSONDecodeError, OSError):
            self._data = {"downloads": [], "last_output": {}, "last_settings": {}}

    def _save(self) -> None:
        """Write data to the JSON file, auto-creating parent directories."""
        atomic_write_json(self.STORAGE_FILE, self._data)
