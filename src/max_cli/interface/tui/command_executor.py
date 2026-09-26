import time
from pathlib import Path
from typing import Any, Callable, Optional

from max_cli.common.exceptions import MaxError
from max_cli.core import presets
from max_cli.interface.tui.activity_log import ActivityLog
from max_cli.interface.tui.command_registry import CommandRegistry, CommandSchema

ENGINE_MODULE_MAP: dict[str, str] = {
    "ImageEngine": "max_cli.core.engines.image_processor",
    "FileOrganizer": "max_cli.core.engines.file_organizer",
    "PDFEngine": "max_cli.core.engines.pdf_engine",
    "AudioMetadataEngine": "max_cli.core.engines.audio_metadata_engine",
    "AIEngine": "max_cli.core.engines.ai_engine",
}

PARAM_NAME_MAPS: dict[tuple[str, str], dict[str, str]] = {
    ("pdf", "compress"): {"target": "input_path"},
    ("pdf", "split"): {"target": "input_path", "output": "output_path"},
    ("pdf", "merge"): {"inputs": "input_paths", "output": "output_path"},
    ("audio", "set"): {"target": "file_path"},
    ("audio", "organize"): {"targets": "source_paths", "output": "target_dir"},
    ("files", "order"): {"start": "start_index"},
    ("files", "shred"): {"target": "path"},
    ("images", "compress"): {"target": "input_path", "output": "output_path"},
    ("images", "resize"): {"target": "input_path", "output": "output_path"},
    ("images", "convert"): {"target": "input_path", "output": "output_path"},
}


class ExecutionResult:
    def __init__(
        self,
        success: bool,
        message: str = "",
        output_files: Optional[list[str]] = None,
        duration_ms: float = 0.0,
        error: Optional[str] = None,
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
        """Rename TUI fields to engine arguments and fill in derived values.

        Defaults and file discovery come from core (presets, engine helpers),
        so this only maps names.
        """
        mapped: dict[str, Any] = {}
        name_map = PARAM_NAME_MAPS.get((category, command), {})
        converters = _VALUE_CONVERTERS.get((category, command), {})

        for key, value in params.items():
            if key == "queue":
                continue
            if key in converters:
                mapped.update(converters[key](value))
                continue
            if category == "pdf" and command == "split" and key in ("start", "end"):
                continue
            if category == "files" and command == "smart_sort" and key == "path":
                mapped["path"] = value
                if "categories" not in params:
                    files = [f.name for f in value.iterdir() if f.is_file()][:20]
                    ai_engine = self._get_engine("AIEngine")
                    mapped["categories"] = ai_engine.categorize_files(files)
                continue
            if category == "images" and key in _IMAGE_FLAG_NAMES:
                mapped[_IMAGE_FLAG_NAMES[key]] = value
                continue
            mapped[name_map.get(key, key)] = value

        if category == "pdf" and command == "split":
            page_range = _page_range(params.get("start"), params.get("end"))
            if page_range:
                mapped["page_ranges"] = page_range

        input_path = mapped.get("input_path")
        if isinstance(input_path, Path) and "output_path" not in mapped:
            output_path = _default_output_path(category, command, input_path, params)
            if output_path is not None:
                mapped["output_path"] = output_path

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
                explain = values.get("explain", False)
                params["app_instance"] = None
                params["explain"] = bool(explain)

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
        from max_cli.core.engines.task_manager import get_task_manager
        from max_cli.core.engines.task_queue import TaskItem

        entry = self._activity_log.start_entry(
            category=category,
            action=command,
            details={"params": {k: str(v) for k, v in values.items()}, "queued": True},
        )
        try:
            manager = get_task_manager()
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
            manager.add(task)
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
        progress_callback: Optional[Callable[[float, str], None]] = None,
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
                explain = values.get("explain", False)
                params["app_instance"] = None
                params["explain"] = bool(explain)

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
            if any(isinstance(v, list) and len(v) > 1 for v in result.values()):
                total_dupes = sum(
                    len(v) - 1 for v in result.values() if isinstance(v, list)
                )
                return (
                    f"Found {len(result)} groups of duplicates "
                    f"({total_dupes} duplicate files)"
                )
            msg = result.get("message", "")
            if msg:
                return msg
        return "Command completed successfully"


def _paths_from(value: Any, find_in_folder: Callable[[Path], list[Path]]) -> list[Path]:
    """A folder becomes its matching files; a list or single path is kept."""
    if isinstance(value, Path) and value.is_dir():
        return find_in_folder(value)
    if isinstance(value, list):
        return [Path(p) if isinstance(p, str) else p for p in value]
    return [value] if isinstance(value, Path) else []


def _pdf_inputs(value: Any) -> dict[str, Any]:
    from max_cli.core.engines.pdf_engine import find_pdfs

    return {"input_paths": _paths_from(value, find_pdfs)}


def _audio_inputs(value: Any) -> dict[str, Any]:
    from max_cli.core.engines.audio_metadata_engine import find_audio_files

    return {"source_paths": _paths_from(value, find_audio_files)}


_VALUE_CONVERTERS: dict[tuple[str, str], dict[str, Callable[[Any], dict[str, Any]]]] = {
    ("audio", "set"): {"track": lambda track: {"tracknumber": str(track)}},
    ("pdf", "merge"): {"inputs": _pdf_inputs},
    ("audio", "organize"): {"targets": _audio_inputs},
    ("images", "convert"): {"to_format": lambda fmt: {"force_format": fmt}},
    ("images", "compress"): {
        "force_jpeg": lambda force: {"force_format": "jpg"} if force else {}
    },
}

_IMAGE_FLAG_NAMES = {"strip": "strip_exif", "quantize": "quantize_png"}


def _page_range(start: Optional[int], end: Optional[int]) -> Optional[str]:
    if start is not None and end is not None:
        return f"{start}-{end}"
    if start is not None:
        return str(start)
    if end is not None:
        return f"1-{end}"
    return None


def _default_output_path(
    category: str, command: str, input_path: Path, params: dict[str, Any]
) -> Optional[Path]:
    """Output next to the input, named the way the matching CLI command names it."""
    sibling = presets.sibling_path
    if category == "pdf" and command == "compress":
        return sibling(input_path, "_compressed", "pdf")
    if category == "images":
        if command == "compress":
            return sibling(input_path, "_compressed", "jpg")
        if command == "resize":
            return sibling(input_path, "_resized")
        if command == "convert":
            return sibling(input_path, extension=params.get("to_format", "webp"))
    return None
