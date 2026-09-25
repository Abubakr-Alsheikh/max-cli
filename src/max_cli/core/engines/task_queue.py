import importlib
import threading
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class TaskType(str, Enum):
    DOWNLOAD = "download"
    VIDEO_COMPRESS = "video_compress"
    VIDEO_CONVERT = "video_convert"
    VIDEO_TO_AUDIO = "video_to_audio"
    VIDEO_DENOISE = "video_denoise"
    AUDIO_DENOISE = "audio_denoise"
    AUDIO_CONVERT = "audio_convert"
    AI_BATCH = "ai_batch"
    PDF_MERGE = "pdf_merge"
    PDF_COMPRESS = "pdf_compress"
    FILE_ORGANIZE = "file_organize"
    FILE_DUPLICATES = "file_duplicates"
    FILE_BACKUP = "file_backup"
    CUSTOM = "custom"


class TaskItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    title: str = ""
    description: str = ""
    payload: Dict[str, Any] = {}
    progress: float = 0.0
    speed: str = ""
    eta: str = ""
    error: str = ""
    result: Dict[str, Any] = {}
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    output_path: Optional[str] = None
    output_files: List[str] = []

    @property
    def is_active(self) -> bool:
        return self.status in (TaskStatus.PENDING, TaskStatus.RUNNING)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskItem":
        return cls(**data)


TaskExecutor = Callable[[TaskItem], Dict[str, Any]]

_executor_registry: Dict[TaskType, TaskExecutor] = {}
_executor_lock = threading.Lock()


# Module that registers each task type's executor when imported. get_executor
# imports it on first use, so engines load only when a task of their type runs.
EXECUTOR_MODULES: Dict[TaskType, str] = {
    TaskType.DOWNLOAD: "max_cli.core.engines.network_engine",
    TaskType.VIDEO_COMPRESS: "max_cli.core.engines.media_engine",
    TaskType.VIDEO_CONVERT: "max_cli.core.engines.media_engine",
    TaskType.VIDEO_TO_AUDIO: "max_cli.core.engines.media_engine",
    TaskType.VIDEO_DENOISE: "max_cli.core.engines.media_engine",
    TaskType.AUDIO_DENOISE: "max_cli.core.engines.media_engine",
    TaskType.PDF_MERGE: "max_cli.core.engines.pdf_engine",
    TaskType.PDF_COMPRESS: "max_cli.core.engines.pdf_engine",
    TaskType.FILE_ORGANIZE: "max_cli.core.engines.file_organizer",
    TaskType.FILE_DUPLICATES: "max_cli.core.engines.file_organizer",
}


def register_executor(task_type: TaskType, executor: TaskExecutor) -> None:
    with _executor_lock:
        _executor_registry[task_type] = executor


def get_executor(task_type: TaskType) -> Optional[TaskExecutor]:
    with _executor_lock:
        executor = _executor_registry.get(task_type)
    if executor is None and task_type in EXECUTOR_MODULES:
        importlib.import_module(EXECUTOR_MODULES[task_type])
        with _executor_lock:
            executor = _executor_registry.get(task_type)
    return executor


def list_registered_executors() -> Dict[str, bool]:
    with _executor_lock:
        registered = set(_executor_registry)
    return {t.value: t in registered or t in EXECUTOR_MODULES for t in TaskType}
