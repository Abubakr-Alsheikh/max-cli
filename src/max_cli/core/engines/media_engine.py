"""MediaEngine: one facade over the video, audio and stream engines.

New code can import VideoEngine, AudioEngine or StreamEngine directly.
MediaEngine stays until every caller has moved.
"""

from pathlib import Path
from typing import Any

from max_cli.core.engines.audio_engine import AudioEngine
from max_cli.core.engines.stream_engine import StreamEngine
from max_cli.core.engines.task_queue import TaskItem, TaskType, register_executor
from max_cli.core.engines.video_engine import VideoEngine


class MediaEngine(VideoEngine, AudioEngine, StreamEngine):
    """
    Wrapper around FFmpeg for video and audio manipulation.
    Requires FFmpeg to be installed in the system PATH.
    """


def _video_compress_executor(task: TaskItem) -> dict[str, Any]:
    engine = MediaEngine()
    payload = task.payload
    input_path = Path(payload["input_path"])
    output_path = Path(
        payload.get(
            "output_path", input_path.parent / f"{input_path.stem}_compressed.mp4"
        )
    )
    engine.compress_video(
        input_path=input_path,
        output_path=output_path,
        crf=payload.get("crf", 28),
        preset=payload.get("preset", "medium"),
    )
    return {
        "output_path": str(output_path),
        "output_files": [str(output_path)],
    }


def _video_convert_executor(task: TaskItem) -> dict[str, Any]:
    engine = MediaEngine()
    payload = task.payload
    input_path = Path(payload["input_path"])
    output_path = Path(
        payload.get("output_path", input_path.parent / f"{input_path.stem}.mp4")
    )
    engine.convert_format(input_path=input_path, output_path=output_path)
    return {
        "output_path": str(output_path),
        "output_files": [str(output_path)],
    }


def _video_to_audio_executor(task: TaskItem) -> dict[str, Any]:
    engine = MediaEngine()
    payload = task.payload
    input_path = Path(payload["input_path"])
    ext = payload.get("format", "mp3")
    output_path = Path(
        payload.get("output_path", input_path.parent / f"{input_path.stem}.{ext}")
    )
    engine.extract_audio(
        input_path=input_path,
        output_path=output_path,
        bitrate=payload.get("bitrate", "192k"),
    )
    return {
        "output_path": str(output_path),
        "output_files": [str(output_path)],
    }


register_executor(TaskType.VIDEO_COMPRESS, _video_compress_executor)
register_executor(TaskType.VIDEO_CONVERT, _video_convert_executor)
register_executor(TaskType.VIDEO_TO_AUDIO, _video_to_audio_executor)


def _video_denoise_executor(task: TaskItem) -> dict[str, Any]:
    engine = MediaEngine()
    payload = task.payload
    input_path = Path(payload["input_path"])
    output_path = Path(
        payload.get(
            "output_path",
            input_path.parent / f"{input_path.stem}_denoised{input_path.suffix}",
        )
    )
    engine.denoise_audio(
        input_path=input_path,
        output_path=output_path,
        mode=payload.get("mode", "auto"),
        strength=payload.get("strength", "medium"),
        hum_cutoff=payload.get("hum_cutoff", 80),
    )
    return {
        "output_path": str(output_path),
        "output_files": [str(output_path)],
    }


register_executor(TaskType.VIDEO_DENOISE, _video_denoise_executor)
register_executor(TaskType.AUDIO_DENOISE, _video_denoise_executor)
