import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from max_cli.common.logger import console
from max_cli.common.retry import retry
from max_cli.common.exceptions import MaxError
from max_cli.config import settings
from max_cli.core.network_engine import NetworkEngine


class QueueError(MaxError):
    """Raised when queue operations fail."""

    pass


class QueueItem:
    """Represents a single download item in the queue."""

    def __init__(
        self,
        url: str,
        quality: str = "h",
        audio_only: bool = False,
        output_path: Optional[Path] = None,
        include_metadata: bool = True,
        playlist_items: Optional[str] = None,
        no_playlist: bool = False,
    ):
        self.id = str(uuid4())[:8]
        self.url = url
        self.quality = quality
        self.audio_only = audio_only
        self.output_path = output_path or settings.GRAB_DEFAULT_PATH
        self.include_metadata = include_metadata
        self.playlist_items = playlist_items
        self.no_playlist = no_playlist
        self.status = "pending"  # pending, downloading, completed, failed
        self.title = ""
        self.progress = 0.0
        self.speed = ""
        self.error = ""
        self.added_at = datetime.now().isoformat()
        self.completed_at: Optional[str] = None
        self.retry_count = 0
        # Additional fields for history
        self.file_path: Optional[str] = None
        self.file_size: int = 0
        self.duration: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "quality": self.quality,
            "audio_only": self.audio_only,
            "output_path": str(self.output_path),
            "include_metadata": self.include_metadata,
            "playlist_items": self.playlist_items,
            "no_playlist": self.no_playlist,
            "status": self.status,
            "title": self.title,
            "progress": self.progress,
            "speed": self.speed,
            "error": self.error,
            "added_at": self.added_at,
            "completed_at": self.completed_at,
            "retry_count": self.retry_count,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "duration": self.duration,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QueueItem":
        item = cls(
            url=data["url"],
            quality=data.get("quality", "h"),
            audio_only=data.get("audio_only", False),
            output_path=Path(data.get("output_path", settings.GRAB_DEFAULT_PATH)),
            include_metadata=data.get("include_metadata", True),
            playlist_items=data.get("playlist_items"),
            no_playlist=data.get("no_playlist", False),
        )
        item.id = data.get("id", item.id)
        item.status = data.get("status", "pending")
        item.title = data.get("title", "")
        item.progress = data.get("progress", 0.0)
        item.speed = data.get("speed", "")
        item.error = data.get("error", "")
        item.added_at = data.get("added_at", item.added_at)
        item.completed_at = data.get("completed_at")
        item.retry_count = data.get("retry_count", 0)
        item.file_path = data.get("file_path")
        item.file_size = data.get("file_size", 0)
        item.duration = data.get("duration")
        return item


class QueueManager:
    """
    Manages the download queue with persistence and background processing.
    """

    QUEUE_FILE = Path.home() / ".max_cli" / "grab_queue.json"
    HISTORY_FILE = Path.home() / ".max_cli" / "grab_history.json"

    def __init__(self):
        self._queue: List[QueueItem] = []
        self._history: List[QueueItem] = []
        self._lock = threading.Lock()
        self._engine = NetworkEngine()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._load_queue()
        self._load_history()

    def _ensure_queue_dir(self) -> None:
        self.QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)

    def _load_history(self) -> None:
        """Load download history from persistent storage."""
        if not self.HISTORY_FILE.exists():
            return
        try:
            data = json.loads(self.HISTORY_FILE.read_text())
            self._history = [QueueItem.from_dict(item) for item in data]
        except Exception:
            self._history = []

    def _save_history(self) -> None:
        """Save download history to persistent storage."""
        self._ensure_queue_dir()
        try:
            data = [item.to_dict() for item in self._history]
            self.HISTORY_FILE.write_text(json.dumps(data, indent=2))
        except Exception as e:
            console.print(f"[red]Failed to save history: {e}[/red]")

    def add_to_history(self, item: QueueItem) -> None:
        """Add a completed download to history."""
        with self._lock:
            self._history.insert(0, item)  # Add to beginning (most recent first)
            # Keep only last 100 items
            if len(self._history) > 100:
                self._history = self._history[:100]
        self._save_history()

    def get_history(self) -> List[QueueItem]:
        """Get download history."""
        with self._lock:
            return list(self._history)

    def clear_history(self) -> int:
        """Clear download history."""
        with self._lock:
            count = len(self._history)
            self._history = []
        self._save_history()
        return count

    def _load_queue(self) -> None:
        """Load queue from persistent storage."""
        if not self.QUEUE_FILE.exists():
            return
        try:
            data = json.loads(self.QUEUE_FILE.read_text())
            self._queue = [QueueItem.from_dict(item) for item in data]
        except Exception:
            self._queue = []

    def _save_queue(self) -> None:
        """Save queue to persistent storage."""
        self._ensure_queue_dir()
        try:
            data = [item.to_dict() for item in self._queue]
            self.QUEUE_FILE.write_text(json.dumps(data, indent=2))
        except Exception as e:
            console.print(f"[red]Failed to save queue: {e}[/red]")

    def add(
        self,
        url: str,
        quality: str = "h",
        audio_only: bool = False,
        output_path: Optional[Path] = None,
        include_metadata: bool = True,
        playlist_items: Optional[str] = None,
        no_playlist: bool = False,
    ) -> Optional[QueueItem]:
        """Add a new item to the queue. Returns None if already in queue."""
        # Check if URL already exists in queue (prevent duplicates only if downloading)
        with self._lock:
            for existing in self._queue:
                if existing.url == url and existing.status == "downloading":
                    console.print(
                        f"[yellow]URL is currently downloading: {existing.status}[/yellow]"
                    )
                    return None

        item = QueueItem(
            url=url,
            quality=quality,
            audio_only=audio_only,
            output_path=output_path,
            include_metadata=include_metadata,
            playlist_items=playlist_items,
            no_playlist=no_playlist,
        )
        with self._lock:
            self._queue.append(item)
            self._save_queue()
        console.print(f"[dim]Added to queue:[/dim] {url}")
        return item

    def remove(self, item_id: str) -> bool:
        """Remove an item from the queue by ID."""
        with self._lock:
            for i, item in enumerate(self._queue):
                if item.id == item_id:
                    self._queue.pop(i)
                    self._save_queue()
                    return True
        return False

    def clear(self) -> int:
        """Clear all pending items from the queue."""
        with self._lock:
            count = len(self._queue)
            self._queue = []
            self._save_queue()
        return count

    def get_all(self) -> List[QueueItem]:
        """Get all queue items."""
        with self._lock:
            return list(self._queue)

    def get_pending(self) -> List[QueueItem]:
        """Get all pending items."""
        with self._lock:
            return [item for item in self._queue if item.status == "pending"]

    def get_by_id(self, item_id: str) -> Optional[QueueItem]:
        """Get a specific item by ID."""
        with self._lock:
            for item in self._queue:
                if item.id == item_id:
                    return item
        return None

    def update_item(self, item: QueueItem) -> None:
        """Update an item in the queue."""
        with self._lock:
            for i, q_item in enumerate(self._queue):
                if q_item.id == item.id:
                    self._queue[i] = item
                    self._save_queue()
                    break

    def start(self) -> None:
        """Start the background queue processor."""
        if self._running:
            return
        self._running = True
        # Use daemon thread - queue will be processed when CLI runs again
        # Or when max grab queue is called
        self._worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self._worker_thread.start()
        console.print("[dim]Queue processor started in background.[/dim]")

    def process_now(self) -> int:
        """Process all pending items synchronously. Returns count of processed items."""
        processed = 0
        while True:
            pending = self.get_pending()
            if not pending:
                break

            item = pending[0]
            try:
                self._download_item(item)
                processed += 1
            except Exception:
                break

        return processed

    def stop(self) -> None:
        """Stop the background queue processor."""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=2)
        console.print("[dim]Queue processor stopped.[/dim]")

    def _process_queue(self) -> None:
        """Background worker that processes queue items."""
        while self._running:
            pending = self.get_pending()
            if not pending:
                time.sleep(1)
                continue

            # Only process one item at a time with a small delay
            time.sleep(0.5)
            item = pending[0]
            console.print(f"[dim]Processing: {item.url}[/dim]")
            try:
                self._download_item(item)
            except Exception as e:
                console.print(f"[red]Download failed: {e}[/red]")

    @retry(max_attempts=3, delay=2.0, backoff=2.0, exceptions=(Exception,))
    def _download_item(self, item: QueueItem) -> None:
        """Download a single queue item with retry logic."""
        item.status = "downloading"
        item.retry_count += 1
        self.update_item(item)

        output_path = item.output_path
        if not output_path.exists():
            output_path.mkdir(parents=True, exist_ok=True)

        final_filename = ""

        def progress_hook(d: Dict[str, Any]) -> None:
            nonlocal final_filename
            if d["status"] == "downloading":
                item.progress = (
                    d.get("downloaded_bytes", 0)
                    / (d.get("total_bytes") or d.get("total_bytes_estimate", 1))
                ) * 100
                item.speed = d.get("speed", "")
                # Get title from info dict if available
                info = d.get("info", {})
                if info and "title" in info:
                    item.title = info["title"][:50]
                elif "filename" in d:
                    # Extract just filename without path
                    fname = d["filename"].split("/")[-1].split("\\")[-1]
                    # Remove extension
                    fname = fname.rsplit(".", 1)[0]
                    item.title = fname[:50]
                self.update_item(item)
            elif d["status"] == "finished":
                item.progress = 100
                item.status = "completed"
                item.completed_at = datetime.now().isoformat()

                # Get final info
                info = d.get("info", {})
                if info:
                    if "title" in info:
                        item.title = info["title"][:50]
                    if "duration" in info:
                        item.duration = info["duration"]

                # Get final filename
                if "filename" in d:
                    final_filename = d["filename"]

                self.update_item(item)
            elif d["status"] == "finished":
                item.progress = 100
                item.status = "completed"
                item.completed_at = datetime.now().isoformat()

                # Get final info
                info = d.get("info", {})
                if info:
                    if "title" in info:
                        item.title = info["title"][:50]
                    if "duration" in info:
                        item.duration = info["duration"]

                self.update_item(item)

        try:
            self._engine.download_media(
                url=item.url,
                output_path=output_path,
                quality=item.quality,
                audio_only=item.audio_only,
                include_metadata=item.include_metadata,
                playlist_items=item.playlist_items,
                no_playlist=item.no_playlist,
                progress_hook=progress_hook,
            )
            item.status = "completed"
            item.completed_at = datetime.now().isoformat()

            # Find the downloaded file and get its info
            if final_filename:
                # Use the final filename from yt-dlp
                fpath = Path(final_filename)
                if fpath.exists():
                    item.file_path = str(fpath)
                    item.file_size = fpath.stat().st_size
            elif item.title:
                # Fallback: look for downloaded files matching the title
                for f in output_path.iterdir():
                    if f.is_file() and f.stem in item.title:
                        item.file_path = str(f)
                        item.file_size = f.stat().st_size
                        break

            # Add to history
            self.add_to_history(item)

        except Exception as e:
            item.status = "failed"
            item.error = str(e)
            raise

        self.update_item(item)

    def get_stats(self) -> Dict[str, int]:
        """Get queue statistics."""
        with self._lock:
            stats = {
                "total": len(self._queue),
                "pending": sum(1 for i in self._queue if i.status == "pending"),
                "downloading": sum(1 for i in self._queue if i.status == "downloading"),
                "completed": sum(1 for i in self._queue if i.status == "completed"),
                "failed": sum(1 for i in self._queue if i.status == "failed"),
            }
        return stats


_queue_manager: Optional[QueueManager] = None


def get_queue_manager() -> QueueManager:
    """Get the global queue manager instance."""
    global _queue_manager
    if _queue_manager is None:
        _queue_manager = QueueManager()
    return _queue_manager
