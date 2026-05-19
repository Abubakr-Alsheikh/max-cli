from enum import Enum
from typing import Any, Optional, Callable
from collections.abc import Generator
from datetime import datetime
from pydantic import BaseModel, Field
import threading
import queue


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


class BaseEvent(BaseModel):
    type: EventType
    timestamp: datetime = Field(default_factory=datetime.now)
    source: str = ""


class ProgressEvent(BaseEvent):
    type: EventType = EventType.PROGRESS
    file: str = ""
    current: int = 0
    total: int = 100
    percentage: float = 0.0
    speed: str = ""
    eta: str = ""
    extra: dict[str, Any] = {}


class BatchProgressEvent(BaseEvent):
    type: EventType = EventType.BATCH_PROGRESS
    current: int = 0
    total: int = 0
    percentage: float = 0.0
    description: str = ""


class FileStartEvent(BaseEvent):
    type: EventType = EventType.FILE_START
    file: str = ""
    action: str = ""


class FileCompleteEvent(BaseEvent):
    type: EventType = EventType.FILE_COMPLETE
    file: str = ""
    result: dict[str, Any] = {}


class FileErrorEvent(BaseEvent):
    type: EventType = EventType.FILE_ERROR
    file: str = ""
    error: str = ""
    level: EventLevel = EventLevel.ERROR


class StatusEvent(BaseEvent):
    type: EventType = EventType.STATUS
    message: str = ""
    level: EventLevel = EventLevel.INFO


class LogEvent(BaseEvent):
    type: EventType = EventType.LOG
    message: str = ""
    level: EventLevel = EventLevel.INFO


class CompleteEvent(BaseEvent):
    type: EventType = EventType.COMPLETE
    summary: dict[str, Any] = {}


class DownloadProgressEvent(BaseEvent):
    type: EventType = EventType.DOWNLOAD_PROGRESS
    url: str = ""
    filename: str = ""
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed: float = 0.0
    eta: int = 0
    percentage: float = 0.0


class DownloadCompleteEvent(BaseEvent):
    type: EventType = EventType.DOWNLOAD_COMPLETE
    url: str = ""
    filename: str = ""
    total_bytes: int = 0


MaxEvent = (
    ProgressEvent
    | BatchProgressEvent
    | FileStartEvent
    | FileCompleteEvent
    | FileErrorEvent
    | StatusEvent
    | LogEvent
    | CompleteEvent
    | DownloadProgressEvent
    | DownloadCompleteEvent
)


class EventEmitter:
    def __init__(self):
        self._subscribers: list[Callable[[MaxEvent], None]] = []
        self._lock = threading.Lock()
        self._queue: queue.Queue[MaxEvent] = queue.Queue()

    def subscribe(self, callback: Callable[[MaxEvent], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[MaxEvent], None]) -> None:
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def emit(self, event: MaxEvent) -> None:
        with self._lock:
            for cb in self._subscribers:
                try:
                    cb(event)
                except Exception:
                    pass
        self._queue.put(event)

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
