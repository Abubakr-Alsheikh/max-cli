import time
from pathlib import Path
from typing import Any, Callable

from max_cli.common.exceptions import MaxError
from max_cli.interface.tui.activity_log import ActivityLog
from max_cli.interface.tui.command_registry import CommandRegistry, CommandSchema

LEVEL_TO_CRF: dict[str, tuple[int, str]] = {
    "high": (23, "fast"),
    "balanced": (28, "medium"),
    "max": (32, "slow"),
}

QUALITY_TO_BITRATE: dict[str, str] = {
    "s": "128k",
    "m": "192k",
    "h": "256k",
    "x": "320k",
}

ENGINE_MODULE_MAP: dict[str, str] = {
    "NetworkEngine": "max_cli.core.engines.network_engine",
    "MediaEngine": "max_cli.core.engines.media_engine",
    "ImageEngine": "max_cli.core.engines.image_processor",
    "FileOrganizer": "max_cli.core.engines.file_organizer",
    "PDFEngine": "max_cli.core.engines.pdf_engine",
    "AudioMetadataEngine": "max_cli.core.engines.audio_metadata_engine",
    "AIEngine": "max_cli.core.engines.ai_engine",
}

PARAM_NAME_MAPS: dict[tuple[str, str], dict[str, str]] = {
    ("video", "compress"): {"target": "input_path", "output": "output_path"},
    ("video", "to_audio"): {"target": "input_path", "output": "output_path"},
    ("video", "convert"): {"target": "input_path"},
    ("video", "gif"): {
        "target": "input_path",
        "output": "output_path",
        "width": "scale",
    },
    ("video", "cut"): {"target": "input_path", "output": "output_path"},
    ("pdf", "compress"): {"target": "input_path"},
    ("pdf", "split"): {"target": "input_path", "output": "output_path"},
    ("pdf", "merge"): {"inputs": "input_paths", "output": "output_path"},
    ("audio", "set"): {"target": "file_path"},
    ("audio", "organize"): {"targets": "source_paths", "output": "target_dir"},
    ("files", "order"): {"start": "start_index"},
    ("grab", "download"): {"resolution": "custom_height"},
    ("images", "compress"): {"target": "input_path", "output": "output_path"},
    ("images", "resize"): {"target": "input_path", "output": "output_path"},
    ("images", "convert"): {"target": "input_path", "output": "output_path"},
}


class ExecutionResult:
    def __init__(
        self,
        success: bool,
        message: str = "",
        output_files: list[str] | None = None,
        duration_ms: float = 0.0,
        error: str | None = None,
    ):
        self.success = success
        self.message = message
        self.output_files = output_files or []
        self.duration_ms = duration_ms
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "output_files": self.output_files,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


class CommandExecutor:
    def __init__(self):
        self._engines: dict[str, Any] = {}
        self._activity_log = ActivityLog()

    def _get_engine(self, engine_name: str) -> Any:
        if engine_name not in self._engines:
            module_path = ENGINE_MODULE_MAP.get(engine_name)
            if not module_path:
                raise MaxError(f"Unknown engine: {engine_name}")
            import importlib

            module = importlib.import_module(module_path)
            engine_class = getattr(module, engine_name)
            self._engines[engine_name] = engine_class()
        return self._engines[engine_name]

    def _resolve_params(
        self,
        category: str,
        command: str,
        schema: CommandSchema,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        raw_params: dict[str, Any] = {}
        for field in schema["fields"]:
            field_name = field["name"]
            value = values.get(field_name)
            if value is None or (isinstance(value, str) and not value.strip()):
                if field["default"] is not None:
                    value = field["default"]
                elif field["required"]:
                    raise MaxError(f"Required field '{field['label']}' is empty")
                else:
                    continue
            field_type = field["type"]
            if field_type == "int":
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    if field["default"] is not None:
                        value = field["default"]
                    else:
                        continue
            elif field_type == "float":
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    continue
            elif field_type == "bool":
                value = bool(value)
            elif field_type in ("path", "path_output", "path_folder"):
                value = Path(str(value).replace("~", str(Path.home())))
            raw_params[field_name] = value
        return self._map_engine_params(category, command, raw_params, schema)

    def _map_engine_params(
        self,
        category: str,
        command: str,
        params: dict[str, Any],
        schema: CommandSchema,
    ) -> dict[str, Any]:
        mapped: dict[str, Any] = {}
        name_map = PARAM_NAME_MAPS.get((category, command), {})
        skip_keys: set[str] = set()

        for key, value in params.items():
            if key in skip_keys:
                continue
            engine_key = name_map.get(key, key)

            if category == "video" and command == "compress" and key == "level":
                crf, preset = LEVEL_TO_CRF.get(value, (28, "medium"))
                mapped["crf"] = crf
                mapped["preset"] = preset
                continue

            if category == "video" and command == "to_audio" and key == "quality":
                mapped["bitrate"] = QUALITY_TO_BITRATE.get(value, "192k")
                continue

            if category == "audio" and command == "set" and key == "track":
                mapped["tracknumber"] = str(value)
                continue

            if category == "pdf" and command == "split":
                if key in ("start", "end"):
                    continue

            if category == "pdf" and command == "merge" and key == "inputs":
                if isinstance(value, Path) and value.is_dir():
                    mapped["input_paths"] = sorted(
                        p
                        for p in value.iterdir()
                        if p.suffix.lower() == ".pdf" and p.is_file()
                    )
                elif isinstance(value, list):
                    mapped["input_paths"] = [
                        Path(p) if isinstance(p, str) else p for p in value
                    ]
                else:
                    mapped["input_paths"] = [value] if isinstance(value, Path) else []
                continue

            if category == "files" and command == "smart_sort" and key == "path":
                mapped["path"] = value
                if "categories" not in params:
                    files = [f.name for f in value.iterdir() if f.is_file()][:20]
                    ai_engine = self._get_engine("AIEngine")
                    mapped["categories"] = ai_engine.categorize_files(files)
                continue

            if category == "images" and command == "convert" and key == "to_format":
                mapped["force_format"] = value
                continue

            if category == "images" and command == "compress" and key == "force_jpeg":
                if value:
                    mapped["force_format"] = "jpg"
                continue

            if category == "images" and key == "strip":
                mapped["strip_exif"] = value
                continue

            if category == "images" and key == "quantize":
                mapped["quantize_png"] = value
                continue

            if category == "audio" and command == "organize" and key == "source_paths":
                if isinstance(value, Path) and value.is_dir():
                    from max_cli.core.engines.audio_metadata_engine import (
                        SUPPORTED_EXTENSIONS,
                    )

                    mapped["source_paths"] = sorted(
                        p
                        for p in value.iterdir()
                        if p.suffix.lower() in SUPPORTED_EXTENSIONS and p.is_file()
                    )
                elif isinstance(value, list):
                    mapped["source_paths"] = [
                        Path(p) if isinstance(p, str) else p for p in value
                    ]
                else:
                    mapped["source_paths"] = [value] if isinstance(value, Path) else []
                continue

            if key == "queue":
                continue

            mapped[engine_key] = value

        if category == "pdf" and command == "split":
            start = params.get("start")
            end = params.get("end")
            if start is not None and end is not None:
                mapped["page_ranges"] = f"{start}-{end}"
            elif start is not None:
                mapped["page_ranges"] = str(start)
            elif end is not None:
                mapped["page_ranges"] = f"1-{end}"

        if category in ("video", "pdf") and command in (
            "compress",
            "to_audio",
            "convert",
            "gif",
            "cut",
        ):
            if "input_path" in mapped and "output_path" not in mapped:
                input_path = mapped["input_path"]
                if command == "compress":
                    mapped["output_path"] = (
                        input_path.parent / f"{input_path.stem}_compressed.mp4"
                    )
                elif command == "to_audio":
                    fmt = params.get("format", "mp3")
                    mapped["output_path"] = (
                        input_path.parent / f"{input_path.stem}.{fmt}"
                    )
                elif command == "convert":
                    fmt = params.get("format", "mp4")
                    mapped["output_path"] = (
                        input_path.parent / f"{input_path.stem}.{fmt}"
                    )
                elif command == "gif":
                    mapped["output_path"] = input_path.parent / f"{input_path.stem}.gif"
                elif command == "cut":
                    mapped["output_path"] = (
                        input_path.parent / f"{input_path.stem}_cut{input_path.suffix}"
                    )

        if category == "pdf" and command == "compress":
            if "input_path" in mapped and "output_path" not in mapped:
                input_path = mapped["input_path"]
                mapped["output_path"] = (
                    input_path.parent / f"{input_path.stem}_compressed.pdf"
                )

        if category == "images" and command in ("compress", "resize", "convert"):
            if "input_path" in mapped and "output_path" not in mapped:
                input_path = mapped["input_path"]
                if command == "compress":
                    mapped["output_path"] = (
                        input_path.parent / f"{input_path.stem}_compressed.jpg"
                    )
                elif command == "resize":
                    mapped["output_path"] = (
                        input_path.parent
                        / f"{input_path.stem}_resized{input_path.suffix}"
                    )
                elif command == "convert":
                    fmt = params.get("to_format", "webp")
                    ext = "jpg" if fmt == "jpg" else fmt
                    mapped["output_path"] = (
                        input_path.parent / f"{input_path.stem}.{ext}"
                    )

        if category == "grab" and command == "download":
            if "output_path" not in mapped:
                mapped["output_path"] = Path.home() / "Max Downloads"
            if isinstance(mapped.get("output_path"), str):
                mapped["output_path"] = Path(
                    mapped["output_path"].replace("~", str(Path.home()))
                )

        return mapped

    def execute(
        self,
        category: str,
        command: str,
        values: dict[str, Any],
        queue: bool = False,
    ) -> ExecutionResult:
        schema = CommandRegistry.get_command(category, command)
        if not schema:
            return ExecutionResult(
                success=False,
                error=f"Unknown command: {category}.{command}",
            )
        if queue:
            return self._execute_queued(category, command, schema, values)
        return self._execute_sync(category, command, schema, values)

    def _execute_sync(
        self,
        category: str,
        command: str,
        schema: CommandSchema,
        values: dict[str, Any],
    ) -> ExecutionResult:
        start = time.monotonic()
        entry = self._activity_log.start_entry(
            category=category,
            action=command,
            details={"params": {k: str(v) for k, v in values.items()}},
        )
        try:
            engine = self._get_engine(schema["engine"])
            params = self._resolve_params(category, command, schema, values)
            method = getattr(engine, schema["method"])

            if category == "ai" and command == "ask":
                params["app_instance"] = None

            result_data = method(**params)
            duration_ms = (time.monotonic() - start) * 1000
            output_files = self._extract_output_files(result_data, values)
            message = self._format_result_message(result_data, output_files, values)
            result = ExecutionResult(
                success=True,
                message=message,
                output_files=output_files,
                duration_ms=duration_ms,
            )
            self._activity_log.complete_entry(entry, "success", result.to_dict())
            return result
        except FileNotFoundError as e:
            duration_ms = (time.monotonic() - start) * 1000
            result = ExecutionResult(
                success=False, error=str(e), duration_ms=duration_ms
            )
            self._activity_log.complete_entry(entry, "failed", {"error": str(e)})
            return result
        except RuntimeError as e:
            duration_ms = (time.monotonic() - start) * 1000
            result = ExecutionResult(
                success=False, error=str(e), duration_ms=duration_ms
            )
            self._activity_log.complete_entry(entry, "failed", {"error": str(e)})
            return result
        except MaxError as e:
            duration_ms = (time.monotonic() - start) * 1000
            result = ExecutionResult(
                success=False, error=str(e), duration_ms=duration_ms
            )
            self._activity_log.complete_entry(entry, "failed", {"error": str(e)})
            return result
        except AttributeError as e:
            duration_ms = (time.monotonic() - start) * 1000
            result = ExecutionResult(
                success=False, error=str(e), duration_ms=duration_ms
            )
            self._activity_log.complete_entry(entry, "failed", {"error": str(e)})
            return result
        except ValueError as e:
            duration_ms = (time.monotonic() - start) * 1000
            result = ExecutionResult(
                success=False, error=str(e), duration_ms=duration_ms
            )
            self._activity_log.complete_entry(entry, "failed", {"error": str(e)})
            return result
        except OSError as e:
            duration_ms = (time.monotonic() - start) * 1000
            result = ExecutionResult(
                success=False, error=str(e), duration_ms=duration_ms
            )
            self._activity_log.complete_entry(entry, "failed", {"error": str(e)})
            return result

    def _execute_queued(
        self,
        category: str,
        command: str,
        schema: CommandSchema,
        values: dict[str, Any],
    ) -> ExecutionResult:
        from max_cli.core.engines.daemon_manager import DaemonManager
        from max_cli.core.engines.task_queue import TaskItem

        entry = self._activity_log.start_entry(
            category=category,
            action=command,
            details={"params": {k: str(v) for k, v in values.items()}, "queued": True},
        )
        try:
            daemon = DaemonManager()
            task_type = self._get_task_type(category, command)
            params = self._resolve_params(category, command, schema, values)
            serializable_params = {}
            for k, v in params.items():
                if isinstance(v, Path):
                    serializable_params[k] = str(v)
                elif isinstance(v, list):
                    serializable_params[k] = [
                        str(i) if isinstance(i, Path) else i for i in v
                    ]
                else:
                    serializable_params[k] = v
            task = TaskItem(
                type=task_type,
                title=f"{category}.{command}",
                description=schema.get("description", ""),
                payload=serializable_params,
            )
            daemon.add(task)
            self._activity_log.complete_entry(
                entry, "success", {"queued": True, "task_id": task.id}
            )
            return ExecutionResult(
                success=True,
                message=f"Added to queue (task {task.id})",
                duration_ms=0.0,
            )
        except MaxError as e:
            self._activity_log.complete_entry(entry, "failed", {"error": str(e)})
            return ExecutionResult(success=False, error=str(e))
        except RuntimeError as e:
            self._activity_log.complete_entry(entry, "failed", {"error": str(e)})
            return ExecutionResult(success=False, error=str(e))
        except OSError as e:
            self._activity_log.complete_entry(entry, "failed", {"error": str(e)})
            return ExecutionResult(success=False, error=str(e))

    def _get_task_type(self, category: str, command: str) -> Any:
        from max_cli.core.engines.task_queue import TaskType

        type_map: dict[tuple[str, str], TaskType] = {
            ("grab", "download"): TaskType.DOWNLOAD,
            ("video", "compress"): TaskType.VIDEO_COMPRESS,
            ("video", "convert"): TaskType.VIDEO_CONVERT,
            ("video", "to_audio"): TaskType.VIDEO_TO_AUDIO,
            ("pdf", "merge"): TaskType.PDF_MERGE,
            ("pdf", "compress"): TaskType.PDF_COMPRESS,
            ("files", "smart_sort"): TaskType.FILE_ORGANIZE,
            ("files", "duplicates"): TaskType.FILE_DUPLICATES,
        }
        return type_map.get((category, command), TaskType.CUSTOM)

    def execute_with_progress(
        self,
        category: str,
        command: str,
        values: dict[str, Any],
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> ExecutionResult:
        schema = CommandRegistry.get_command(category, command)
        if not schema:
            return ExecutionResult(
                success=False,
                error=f"Unknown command: {category}.{command}",
            )
        start = time.monotonic()
        entry = self._activity_log.start_entry(
            category=category,
            action=command,
            details={"params": {k: str(v) for k, v in values.items()}},
        )
        try:
            engine = self._get_engine(schema["engine"])
            params = self._resolve_params(category, command, schema, values)
            method = getattr(engine, schema["method"])

            if category == "ai" and command == "ask":
                params["app_instance"] = None

            if progress_callback:
                progress_callback(0.0, "Starting...")

            result_data = method(**params)

            if progress_callback:
                progress_callback(1.0, "Complete")

            duration_ms = (time.monotonic() - start) * 1000
            output_files = self._extract_output_files(result_data, values)
            message = self._format_result_message(result_data, output_files, values)
            result = ExecutionResult(
                success=True,
                message=message,
                output_files=output_files,
                duration_ms=duration_ms,
            )
            self._activity_log.complete_entry(entry, "success", result.to_dict())
            return result
        except FileNotFoundError as e:
            duration_ms = (time.monotonic() - start) * 1000
            result = ExecutionResult(
                success=False, error=str(e), duration_ms=duration_ms
            )
            self._activity_log.complete_entry(entry, "failed", {"error": str(e)})
            if progress_callback:
                progress_callback(1.0, f"Failed: {e}")
            return result
        except RuntimeError as e:
            duration_ms = (time.monotonic() - start) * 1000
            result = ExecutionResult(
                success=False, error=str(e), duration_ms=duration_ms
            )
            self._activity_log.complete_entry(entry, "failed", {"error": str(e)})
            if progress_callback:
                progress_callback(1.0, f"Failed: {e}")
            return result
        except MaxError as e:
            duration_ms = (time.monotonic() - start) * 1000
            result = ExecutionResult(
                success=False, error=str(e), duration_ms=duration_ms
            )
            self._activity_log.complete_entry(entry, "failed", {"error": str(e)})
            if progress_callback:
                progress_callback(1.0, f"Failed: {e}")
            return result
        except AttributeError as e:
            duration_ms = (time.monotonic() - start) * 1000
            result = ExecutionResult(
                success=False, error=str(e), duration_ms=duration_ms
            )
            self._activity_log.complete_entry(entry, "failed", {"error": str(e)})
            if progress_callback:
                progress_callback(1.0, f"Failed: {e}")
            return result
        except ValueError as e:
            duration_ms = (time.monotonic() - start) * 1000
            result = ExecutionResult(
                success=False, error=str(e), duration_ms=duration_ms
            )
            self._activity_log.complete_entry(entry, "failed", {"error": str(e)})
            if progress_callback:
                progress_callback(1.0, f"Failed: {e}")
            return result
        except OSError as e:
            duration_ms = (time.monotonic() - start) * 1000
            result = ExecutionResult(
                success=False, error=str(e), duration_ms=duration_ms
            )
            self._activity_log.complete_entry(entry, "failed", {"error": str(e)})
            if progress_callback:
                progress_callback(1.0, f"Failed: {e}")
            return result

    def _extract_output_files(self, result: Any, values: dict) -> list[str]:
        if result is None:
            output = values.get("output") or values.get("output_path")
            if output:
                return [str(output)]
            target = values.get("target") or values.get("url", "")
            if target and Path(target).suffix:
                return [str(target)]
            return []
        if isinstance(result, int):
            return []
        if isinstance(result, Path):
            return [str(result)]
        if isinstance(result, dict):
            files = result.get("output_files", [])
            if files:
                return [str(f) for f in files]
            output = result.get("output_path")
            if output:
                return [str(output)]
        return []

    def _format_result_message(
        self, result: Any, output_files: list[str], values: dict
    ) -> str:
        if result is None:
            if output_files:
                return f"Output: {', '.join(output_files)}"
            return "Command completed successfully"
        if isinstance(result, int):
            return f"Processed {result} items"
        if isinstance(result, Path):
            return f"Output: {result}"
        if isinstance(result, dict):
            msg = result.get("message", "")
            if msg:
                return msg
        return "Command completed successfully"
