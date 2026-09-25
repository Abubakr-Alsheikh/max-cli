from enum import Enum
from typing import Any, Optional, Callable, Union
from collections.abc import Generator
from datetime import datetime
from dataclasses import dataclass, field
import logging
import threading
import queue

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    PROGRESS = "progress"
    BATCH_PROGRESS = "batch_progress"
    FILE_START = "file_start"
    FILE_COMPLETE = "file_complete"
    FILE_ERROR = "file_error"
    STATUS = "status"
    LOG = "log"
    COMPLETE = "complete"
    DOWNLOAD_PROGRESS = "download_progress"
    DOWNLOAD_COMPLETE = "download_complete"


class EventLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"


@dataclass
class BaseEvent:
    type: EventType
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""


@dataclass
class ProgressEvent(BaseEvent):
    type: EventType = EventType.PROGRESS
    file: str = ""
    current: int = 0
    total: int = 100
    percentage: float = 0.0
    speed: str = ""
    eta: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchProgressEvent(BaseEvent):
    type: EventType = EventType.BATCH_PROGRESS
    current: int = 0
    total: int = 0
    percentage: float = 0.0
    description: str = ""


@dataclass
class FileStartEvent(BaseEvent):
    type: EventType = EventType.FILE_START
    file: str = ""
    action: str = ""


@dataclass
class FileCompleteEvent(BaseEvent):
    type: EventType = EventType.FILE_COMPLETE
    file: str = ""
    result: dict[str, Any] = field(default_factory=dict)


@dataclass
class FileErrorEvent(BaseEvent):
    type: EventType = EventType.FILE_ERROR
    file: str = ""
    error: str = ""
    level: EventLevel = EventLevel.ERROR


@dataclass
class StatusEvent(BaseEvent):
    type: EventType = EventType.STATUS
    message: str = ""
    level: EventLevel = EventLevel.INFO


@dataclass
class LogEvent(BaseEvent):
    type: EventType = EventType.LOG
    message: str = ""
    level: EventLevel = EventLevel.INFO


@dataclass
class CompleteEvent(BaseEvent):
    type: EventType = EventType.COMPLETE
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class DownloadProgressEvent(BaseEvent):
    type: EventType = EventType.DOWNLOAD_PROGRESS
    url: str = ""
    filename: str = ""
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed: float = 0.0
    eta: int = 0
    percentage: float = 0.0


@dataclass
class DownloadCompleteEvent(BaseEvent):
    type: EventType = EventType.DOWNLOAD_COMPLETE
    url: str = ""
    filename: str = ""
    total_bytes: int = 0


MaxEvent = Union[
    ProgressEvent,
    BatchProgressEvent,
    FileStartEvent,
    FileCompleteEvent,
    FileErrorEvent,
    StatusEvent,
    LogEvent,
    CompleteEvent,
    DownloadProgressEvent,
    DownloadCompleteEvent,
]


EVENT_QUEUE_LIMIT = 1000  # oldest events drop once nobody drains the queue


class EventEmitter:
    def __init__(self):
        self._subscribers: list[Callable[[MaxEvent], None]] = []
        self._lock = threading.Lock()
        self._queue: queue.Queue[MaxEvent] = queue.Queue(maxsize=EVENT_QUEUE_LIMIT)

    def subscribe(self, callback: Callable[[MaxEvent], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[MaxEvent], None]) -> None:
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def emit(self, event: MaxEvent) -> None:
        # Call subscribers outside the lock so a callback can emit or (un)subscribe.
        with self._lock:
            subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                callback(event)
            except Exception:  # noqa: BLE001 - one bad subscriber must not stop others
                logger.exception("Event subscriber %r failed", callback)
        self._enqueue(event)

    def _enqueue(self, event: MaxEvent) -> None:
        """Keep the newest EVENT_QUEUE_LIMIT events when nobody drains the queue."""
        while True:
            try:
                self._queue.put_nowait(event)
                return
            except queue.Full:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    continue

    def get_queue(self) -> queue.Queue[MaxEvent]:
        return self._queue

    def event_generator(self) -> Generator[MaxEvent, None, None]:
        while True:
            event = self._queue.get()
            if event.type == EventType.COMPLETE:
                yield event
                break
            yield event

    def clear(self) -> None:
        with self._lock:
            self._subscribers.clear()
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break


_default_emitter: Optional[EventEmitter] = None
_emitter_lock = threading.Lock()


def get_emitter() -> EventEmitter:
    global _default_emitter
    with _emitter_lock:
        if _default_emitter is None:
            _default_emitter = EventEmitter()
        return _default_emitter


def reset_emitter() -> None:
    global _default_emitter
    with _emitter_lock:
        if _default_emitter is not None:
            _default_emitter.clear()
            _default_emitter = None
