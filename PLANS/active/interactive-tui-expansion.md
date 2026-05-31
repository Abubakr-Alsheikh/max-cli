# Plan: Interactive TUI Dashboard Expansion

> Status: Completed
> Priority: P1
> Related: User Experience & Laziness (Feature 2C Phase 2)

## Overview

The current TUI dashboard (`max dashboard`) provides 4 read-only monitoring tabs (Queue, History, Config, System). This plan expands it into a fully interactive command center with 8 tabs, enabling users to execute commands, download media, browse files, chat with AI, and view a unified activity history — all without leaving the terminal.

## Problem Analysis

1. **Fragmented UX**: Users must exit the dashboard to run any command. The dashboard is a "view-only" dashboard, not a "command center."
2. **No Download UI**: `max grab download` requires CLI arguments or interactive prompt mode. No visual form exists in the TUI.
3. **Fragmented History**: Task history, download history, transaction logs, and daemon logs are stored in separate files with no unified view.
4. **No File Browser**: Users cannot browse, preview, or operate on files from within the dashboard.
5. **No AI Chat**: `max ai chat` runs as a separate CLI session. No persistent chat UI exists in the TUI.
6. **60+ Commands Inaccessible**: The full CLI command inventory is not exposed through the TUI at all.

## Goals

1. **Interactive Command Execution**: Every major CLI command accessible through dynamic forms in the TUI.
2. **Unified Activity History**: Single timeline showing downloads, tasks, file operations, commands, and AI interactions.
3. **Download Panel**: Full form-based download UI with URL input, quality selection, output path, and queue integration.
4. **File Browser**: Directory tree + file list with quick-action buttons for common operations.
5. **AI Chat Tab**: Persistent chat interface with message history, suggestions, and export/import.
6. **Home Dashboard**: Card grid of common operations + quick stats + recent activity feed.
7. **System Cleanup Actions**: Cache/backup/transaction cleanup buttons on the System panel.

## Architecture

### New File Structure

```
src/max_cli/interface/tui/
├── app.py                          # Updated: 8-tab layout, new CSS
├── dashboard.py                    # Unchanged (entry point)
├── command_registry.py             # NEW: Command schema definitions
├── command_executor.py             # NEW: Engine method dispatcher
├── activity_log.py                 # NEW: Unified activity logger
└── widgets/
    ├── __init__.py
    ├── queue_panel.py              # Existing (no changes)
    ├── history_panel.py            # Enhanced: unified activity data
    ├── config_panel.py             # Existing (no changes)
    ├── system_panel.py             # Enhanced: cleanup actions
    ├── home_panel.py               # NEW: card grid + quick stats
    ├── download_panel.py           # NEW: grab download form
    ├── files_panel.py              # NEW: file browser + actions
    ├── tools_panel.py              # NEW: command launcher with forms
    └── chat_panel.py               # NEW: AI chat interface
```

### Data Flow

```
User Input (TUI Widget)
    → CommandExecutor.execute(category, command, params)
        → Engine method call (direct, not subprocess)
            → ActivityLog.record(category, action, status, details)
                → UI update (toast, status bar, history refresh)
```

### Key Design Principles

- **No subprocess calls**: Commands execute via direct engine method calls for speed and error handling.
- **Event-driven progress**: Reuses existing `EventEmitter`/`EventSubscriber` pattern for progress display.
- **Graceful degradation**: If an engine fails to initialize (e.g., no FFmpeg), show a friendly error, don't crash.
- **Lazy loading**: Heavy imports deferred until the tab is first activated.
- **Thread safety**: Long-running commands execute in worker threads to keep the TUI responsive.

## Implementation Details

### Phase 1: Command Registry Framework

**Files**: `src/max_cli/interface/tui/command_registry.py`

The command registry maps command names to form schemas. Each command defines its engine, method, and input fields.

```python
"""Command registry for TUI dynamic form generation."""

from typing import Any, Optional


class CommandField:
    """Defines a single input field for a command form."""

    def __init__(
        self,
        name: str,
        field_type: str,
        label: str,
        required: bool = False,
        default: Any = None,
        options: Optional[list[str]] = None,
        help_text: str = "",
        placeholder: str = "",
    ):
        self.name = name
        self.field_type = field_type  # str, int, bool, select, path, file, path_dir
        self.label = label
        self.required = required
        self.default = default
        self.options = options or []
        self.help_text = help_text
        self.placeholder = placeholder

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.field_type,
            "label": self.label,
            "required": self.required,
            "default": self.default,
            "options": self.options,
            "help": self.help_text,
            "placeholder": self.placeholder,
        }


class CommandSchema:
    """Defines a complete command with its fields."""

    def __init__(
        self,
        category: str,
        name: str,
        label: str,
        icon: str,
        engine: str,
        method: str,
        fields: list[CommandField],
        description: str = "",
        requires_binary: Optional[str] = None,
    ):
        self.category = category
        self.name = name
        self.label = label
        self.icon = icon
        self.engine = engine
        self.method = method
        self.fields = fields
        self.description = description
        self.requires_binary = requires_binary

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "name": self.name,
            "label": self.label,
            "icon": self.icon,
            "engine": self.engine,
            "method": self.method,
            "fields": [f.to_dict() for f in self.fields],
            "description": self.description,
            "requires_binary": self.requires_binary,
        }


# ─── Command Registry ────────────────────────────────────────────────────────

COMMANDS: dict[str, dict[str, CommandSchema]] = {
    "grab": {
        "download": CommandSchema(
            category="grab",
            name="download",
            label="Download Media",
            icon="⬇",
            engine="NetworkEngine",
            method="download_media",
            description="Download video or audio from a URL",
            fields=[
                CommandField(
                    "url", "str", "URL", required=True,
                    placeholder="https://youtube.com/watch?v=...",
                ),
                CommandField(
                    "audio_only", "bool", "Audio Only", default=False,
                ),
                CommandField(
                    "quality", "select", "Quality", default="h",
                    options=["ss (360p)", "s (480p)", "m (720p)", "h (1080p)", "x (4K)"],
                ),
                CommandField(
                    "custom_height", "int", "Custom Resolution",
                    placeholder="e.g. 1440",
                ),
                CommandField(
                    "subtitles", "bool", "Download Subtitles", default=False,
                ),
                CommandField(
                    "include_metadata", "bool", "Include Metadata", default=True,
                ),
                CommandField(
                    "no_playlist", "bool", "No Playlist", default=False,
                ),
                CommandField(
                    "output_path", "path_dir", "Output Directory",
                    default="~/Max Downloads",
                ),
            ],
        ),
    },
    "video": {
        "compress": CommandSchema(
            category="video",
            name="compress",
            label="Compress Video",
            icon="📦",
            engine="MediaEngine",
            method="compress_video",
            description="Compress video using H.264",
            requires_binary="ffmpeg",
            fields=[
                CommandField(
                    "input_path", "file", "Input Video", required=True,
                    placeholder="/path/to/video.mp4",
                ),
                CommandField(
                    "output_path", "path", "Output Video",
                    placeholder="/path/to/output.mp4",
                ),
                CommandField(
                    "crf", "int", "CRF (quality)", default=28,
                    help_text="0-51, lower=better quality, 28=compressed",
                ),
                CommandField(
                    "preset", "select", "Preset", default="medium",
                    options=["ultrafast", "superfast", "veryfast", "fast", "medium", "slow"],
                ),
            ],
        ),
        "to_audio": CommandSchema(
            category="video",
            name="to_audio",
            label="Extract Audio",
            icon="🎵",
            engine="MediaEngine",
            method="extract_audio",
            description="Extract audio track from video",
            requires_binary="ffmpeg",
            fields=[
                CommandField(
                    "input_path", "file", "Input Video", required=True,
                ),
                CommandField(
                    "output_path", "path", "Output Audio",
                    placeholder="/path/to/output.mp3",
                ),
                CommandField(
                    "bitrate", "select", "Audio Bitrate", default="192k",
                    options=["64k", "96k", "128k", "192k", "256k", "320k"],
                ),
            ],
        ),
        "convert": CommandSchema(
            category="video",
            name="convert",
            label="Convert Format",
            icon="🔄",
            engine="MediaEngine",
            method="convert_format",
            description="Convert video format (e.g. MKV → MP4)",
            requires_binary="ffmpeg",
            fields=[
                CommandField(
                    "input_path", "file", "Input Video", required=True,
                ),
                CommandField(
                    "output_path", "path", "Output Video", required=True,
                ),
            ],
        ),
        "gif": CommandSchema(
            category="video",
            name="gif",
            label="Video to GIF",
            icon="🎞",
            engine="MediaEngine",
            method="video_to_gif",
            description="Create animated GIF from video",
            requires_binary="ffmpeg",
            fields=[
                CommandField(
                    "input_path", "file", "Input Video", required=True,
                ),
                CommandField(
                    "output_path", "path", "Output GIF",
                    placeholder="/path/to/output.gif",
                ),
                CommandField(
                    "fps", "int", "FPS", default=15,
                ),
                CommandField(
                    "scale", "int", "Width (px)", default=480,
                ),
            ],
        ),
        "cut": CommandSchema(
            category="video",
            name="cut",
            label="Trim Video",
            icon="✂",
            engine="MediaEngine",
            method="trim_video",
            description="Cut a video clip by time range",
            requires_binary="ffmpeg",
            fields=[
                CommandField(
                    "input_path", "file", "Input Video", required=True,
                ),
                CommandField(
                    "output_path", "path", "Output Video", required=True,
                ),
                CommandField(
                    "start", "str", "Start Time", required=True,
                    placeholder="00:01:30 or 90",
                ),
                CommandField(
                    "end", "str", "End Time",
                    placeholder="00:02:00 (optional)",
                ),
                CommandField(
                    "duration", "str", "Duration",
                    placeholder="30 (seconds, optional)",
                ),
            ],
        ),
    },
    "images": {
        "compress": CommandSchema(
            category="images",
            name="compress",
            label="Compress Image",
            icon="🖼",
            engine="ImageEngine",
            method="process_single_image",
            description="Compress, resize, or convert an image",
            fields=[
                CommandField(
                    "input_path", "file", "Input Image", required=True,
                ),
                CommandField(
                    "output_path", "path", "Output Image",
                    placeholder="/path/to/output.jpg",
                ),
                CommandField(
                    "quality", "int", "Quality (JPEG/WebP)", default=85,
                ),
                CommandField(
                    "max_dim", "int", "Max Dimension (px)",
                    placeholder="e.g. 1920",
                ),
                CommandField(
                    "force_format", "select", "Output Format",
                    options=["", "jpg", "png", "webp", "gif"],
                ),
                CommandField(
                    "strip_exif", "bool", "Strip EXIF Metadata", default=False,
                ),
            ],
        ),
        "resize": CommandSchema(
            category="images",
            name="resize",
            label="Resize Image",
            icon="📐",
            engine="ImageEngine",
            method="process_single_image",
            description="Resize image by width, height, or scale",
            fields=[
                CommandField(
                    "input_path", "file", "Input Image", required=True,
                ),
                CommandField(
                    "output_path", "path", "Output Image", required=True,
                ),
                CommandField(
                    "width", "int", "Width (px)",
                    placeholder="e.g. 1920",
                ),
                CommandField(
                    "height", "int", "Height (px)",
                    placeholder="e.g. 1080",
                ),
                CommandField(
                    "scale", "int", "Scale (%)",
                    placeholder="e.g. 50",
                ),
            ],
        ),
        "convert": CommandSchema(
            category="images",
            name="convert",
            label="Convert Format",
            icon="🔄",
            engine="ImageEngine",
            method="process_single_image",
            description="Convert image to different format",
            fields=[
                CommandField(
                    "input_path", "file", "Input Image", required=True,
                ),
                CommandField(
                    "output_path", "path", "Output Image", required=True,
                ),
                CommandField(
                    "force_format", "select", "Output Format", required=True,
                    options=["jpg", "png", "webp", "gif", "bmp", "tiff"],
                ),
            ],
        ),
    },
    "files": {
        "smart_sort": CommandSchema(
            category="files",
            name="smart_sort",
            label="Smart Sort Files",
            icon="📁",
            engine="FileOrganizer",
            method="smart_sort",
            description="Organize files into categorized folders",
            fields=[
                CommandField(
                    "path", "path_dir", "Target Directory", required=True,
                ),
                CommandField(
                    "dry_run", "bool", "Dry Run (Preview)", default=True,
                ),
            ],
        ),
        "duplicates": CommandSchema(
            category="files",
            name="duplicates",
            label="Find Duplicates",
            icon="🔍",
            engine="FileOrganizer",
            method="find_duplicates",
            description="Find duplicate files by content hash",
            fields=[
                CommandField(
                    "folder", "path_dir", "Target Directory", required=True,
                ),
                CommandField(
                    "recursive", "bool", "Search Subdirectories", default=False,
                ),
            ],
        ),
        "order": CommandSchema(
            category="files",
            name="order",
            label="Order Files",
            icon="🔢",
            engine="FileOrganizer",
            method="order_files",
            description="Rename files with sequential numbers",
            fields=[
                CommandField(
                    "folder", "path_dir", "Target Directory", required=True,
                ),
                CommandField(
                    "start_index", "int", "Start Number", default=1,
                ),
                CommandField(
                    "dry_run", "bool", "Dry Run (Preview)", default=True,
                ),
            ],
        ),
    },
    "pdf": {
        "merge": CommandSchema(
            category="pdf",
            name="merge",
            label="Merge PDFs",
            icon="📄",
            engine="PDFEngine",
            method="merge_pdfs",
            description="Combine multiple PDFs into one",
            fields=[
                CommandField(
                    "input_paths", "file_multi", "Input PDFs", required=True,
                    placeholder="Select multiple PDF files",
                ),
                CommandField(
                    "output_path", "path", "Output PDF", required=True,
                    placeholder="/path/to/merged.pdf",
                ),
            ],
        ),
        "compress": CommandSchema(
            category="pdf",
            name="compress",
            label="Compress PDF",
            icon="📦",
            engine="PDFEngine",
            method="compress_pdf",
            description="Compress PDF by rasterizing pages",
            fields=[
                CommandField(
                    "input_path", "file", "Input PDF", required=True,
                ),
                CommandField(
                    "output_path", "path", "Output PDF", required=True,
                ),
                CommandField(
                    "dpi", "int", "DPI", default=150,
                ),
                CommandField(
                    "quality", "int", "JPEG Quality", default=80,
                ),
            ],
        ),
        "split": CommandSchema(
            category="pdf",
            name="split",
            label="Split PDF",
            icon="✂",
            engine="PDFEngine",
            method="split_pdf",
            description="Extract specific pages from a PDF",
            fields=[
                CommandField(
                    "input_path", "file", "Input PDF", required=True,
                ),
                CommandField(
                    "output_path", "path", "Output PDF", required=True,
                ),
                CommandField(
                    "page_ranges", "str", "Page Ranges", required=True,
                    placeholder="1-5,8,11-15",
                ),
            ],
        ),
    },
    "audio": {
        "set_metadata": CommandSchema(
            category="audio",
            name="set_metadata",
            label="Set Audio Metadata",
            icon="🏷",
            engine="AudioMetadataEngine",
            method="set_metadata",
            description="Set ID3/metadata tags on audio files",
            fields=[
                CommandField(
                    "file_path", "file", "Audio File", required=True,
                ),
                CommandField(
                    "title", "str", "Title",
                ),
                CommandField(
                    "artist", "str", "Artist",
                ),
                CommandField(
                    "album", "str", "Album",
                ),
                CommandField(
                    "genre", "str", "Genre",
                ),
                CommandField(
                    "date", "str", "Year",
                    placeholder="e.g. 2024",
                ),
                CommandField(
                    "tracknumber", "str", "Track Number",
                    placeholder="e.g. 01",
                ),
            ],
        ),
        "compress": CommandSchema(
            category="audio",
            name="compress",
            label="Compress Audio",
            icon="📦",
            engine="MediaEngine",
            method="compress_audio",
            description="Compress audio to lower bitrate",
            requires_binary="ffmpeg",
            fields=[
                CommandField(
                    "input_path", "file", "Input Audio", required=True,
                ),
                CommandField(
                    "output_path", "path", "Output Audio", required=True,
                ),
                CommandField(
                    "bitrate", "select", "Bitrate", default="128k",
                    options=["32k", "64k", "96k", "128k", "192k", "256k", "320k"],
                ),
            ],
        ),
    },
    "ai": {
        "ask": CommandSchema(
            category="ai",
            name="ask",
            label="Ask AI",
            icon="🤖",
            engine="AIEngine",
            method="interpret_intent",
            description="Ask AI to generate a Max CLI command",
            fields=[
                CommandField(
                    "prompt", "str", "Question", required=True,
                    placeholder="e.g. Compress all videos in my Downloads folder",
                ),
            ],
        ),
    },
}

# ─── Category Metadata ───────────────────────────────────────────────────────

CATEGORIES: dict[str, dict[str, str]] = {
    "grab": {"label": "Download", "icon": "⬇", "color": "green"},
    "video": {"label": "Video", "icon": "🎬", "color": "blue"},
    "images": {"label": "Images", "icon": "🖼", "color": "cyan"},
    "files": {"label": "Files", "icon": "📁", "color": "yellow"},
    "pdf": {"label": "PDF", "icon": "📄", "color": "red"},
    "audio": {"label": "Audio", "icon": "🎵", "color": "magenta"},
    "ai": {"label": "AI", "icon": "🤖", "color": "purple"},
}


# ─── Registry API ────────────────────────────────────────────────────────────

def get_command(category: str, name: str) -> Optional[CommandSchema]:
    """Get a command schema by category and name."""
    return COMMANDS.get(category, {}).get(name)


def get_category_commands(category: str) -> dict[str, CommandSchema]:
    """Get all commands in a category."""
    return COMMANDS.get(category, {})


def get_all_commands() -> dict[str, dict[str, CommandSchema]]:
    """Get the full command registry."""
    return COMMANDS


def get_categories() -> dict[str, dict[str, str]]:
    """Get category metadata."""
    return CATEGORIES


def get_quick_actions() -> list[dict[str, str]]:
    """Get commands for the Home dashboard card grid."""
    return [
        {"category": "grab", "name": "download", "label": "Download Media", "icon": "⬇"},
        {"category": "video", "name": "compress", "label": "Compress Video", "icon": "📦"},
        {"category": "video", "name": "to_audio", "label": "Extract Audio", "icon": "🎵"},
        {"category": "images", "name": "compress", "label": "Compress Images", "icon": "🖼"},
        {"category": "images", "name": "convert", "label": "Convert Images", "icon": "🔄"},
        {"category": "pdf", "name": "merge", "label": "Merge PDFs", "icon": "📄"},
        {"category": "files", "name": "smart_sort", "label": "Organize Files", "icon": "📁"},
        {"category": "ai", "name": "ask", "label": "Ask AI", "icon": "🤖"},
    ]
```

### Phase 2: Command Executor

**Files**: `src/max_cli/interface/tui/command_executor.py`

The command executor dispatches commands to engine methods, handles parameter conversion, logs activity, and returns structured results.

```python
"""Command executor for TUI — dispatches to engine methods directly."""

import time
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from max_cli.interface.tui.activity_log import ActivityLog, ActivityEntry
from max_cli.interface.tui.command_registry import CommandSchema, get_command


class ExecutionResult:
    """Structured result from a command execution."""

    def __init__(
        self,
        success: bool,
        message: str = "",
        output_files: Optional[list[str]] = None,
        duration_ms: int = 0,
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
    """Executes commands via direct engine method calls."""

    def __init__(self):
        self._engines: dict[str, Any] = {}
        self._activity_log = ActivityLog()

    def _get_engine(self, engine_name: str) -> Any:
        """Lazily instantiate an engine by class name."""
        if engine_name not in self._engines:
            engine_map = {
                "NetworkEngine": "max_cli.core.engines.network_engine",
                "MediaEngine": "max_cli.core.engines.media_engine",
                "ImageEngine": "max_cli.core.engines.image_processor",
                "FileOrganizer": "max_cli.core.engines.file_organizer",
                "PDFEngine": "max_cli.core.engines.pdf_engine",
                "AudioMetadataEngine": "max_cli.core.engines.audio_metadata_engine",
                "AIEngine": "max_cli.core.engines.ai_engine",
            }
            module_path = engine_map.get(engine_name)
            if not module_path:
                raise ValueError(f"Unknown engine: {engine_name}")

            import importlib

            module = importlib.import_module(module_path)
            engine_class = getattr(module, engine_name)
            self._engines[engine_name] = engine_class()

        return self._engines[engine_name]

    def _resolve_params(
        self, schema: CommandSchema, form_values: dict[str, Any]
    ) -> dict[str, Any]:
        """Convert form values to engine method parameters."""
        params = {}
        for field in schema.fields:
            value = form_values.get(field.name)
            if value is None or (isinstance(value, str) and not value.strip()):
                if field.default is not None:
                    value = field.default
                elif field.required:
                    raise ValueError(f"Required field '{field.label}' is empty")
                else:
                    continue

            # Type conversion
            if field.field_type == "int":
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    if field.default is not None:
                        value = field.default
                    else:
                        continue
            elif field.field_type == "bool":
                value = bool(value)
            elif field.field_type in ("path", "file", "path_dir"):
                value = Path(str(value).replace("~", str(Path.home())))
            elif field.field_type == "file_multi":
                # Multiple file paths separated by newlines
                if isinstance(value, str):
                    value = [
                        Path(p.strip().replace("~", str(Path.home())))
                        for p in value.split("\n")
                        if p.strip()
                    ]

            # Special handling for quality field (strip the label suffix)
            if field.name == "quality" and isinstance(value, str):
                value = value.split(" ")[0]  # "h (1080p)" → "h"

            params[field.name] = value

        return params

    def execute(
        self,
        category: str,
        name: str,
        form_values: dict[str, Any],
        callback: Optional[Callable[[ExecutionResult], None]] = None,
    ) -> None:
        """Execute a command asynchronously. Calls callback with result."""
        schema = get_command(category, name)
        if not schema:
            result = ExecutionResult(
                success=False, error=f"Unknown command: {category}.{name}"
            )
            if callback:
                callback(result)
            return

        def _run():
            start = time.monotonic()
            entry = self._activity_log.start_entry(
                category=category,
                action=name,
                details={"params": {k: str(v) for k, v in form_values.items()}},
            )

            try:
                engine = self._get_engine(schema.engine)
                params = self._resolve_params(schema, form_values)
                method = getattr(engine, schema.method)

                # Special case: AIEngine.interpret_intent needs app_instance
                if schema.method == "interpret_intent":
                    params["app_instance"] = None
                    params["explain"] = False

                result_data = method(**params)

                duration_ms = int((time.monotonic() - start) * 1000)
                output_files = []
                message = "Command completed successfully"

                # Extract output files from result
                if isinstance(result_data, dict):
                    output_files = [
                        str(p) for p in result_data.get("output_files", [])
                    ]
                    message = result_data.get("message", message)
                    if "out_path" in result_data:
                        output_files.append(str(result_data["out_path"]))
                    if "output_path" in result_data:
                        output_files.append(str(result_data["output_path"]))
                    if "renamed" in result_data:
                        message = (
                            f"Renamed {result_data['renamed']} files, "
                            f"skipped {result_data.get('skipped', 0)}"
                        )
                    if "moved" in result_data:
                        message = (
                            f"Moved {result_data['moved']} files, "
                            f"errors: {result_data.get('errors', 0)}"
                        )
                    if isinstance(result_data.get("total_pages"), int):
                        message = f"Merged {result_data['total_pages']} pages"
                elif isinstance(result_data, int):
                    message = f"Processed {result_data} items"
                elif isinstance(result_data, list):
                    message = f"Processed {len(result_data)} items"
                    output_files = [str(p) for p in result_data if isinstance(p, Path)]

                result = ExecutionResult(
                    success=True,
                    message=message,
                    output_files=output_files,
                    duration_ms=duration_ms,
                )
                self._activity_log.complete_entry(entry, "success", result.to_dict())

            except Exception as e:
                duration_ms = int((time.monotonic() - start) * 1000)
                result = ExecutionResult(
                    success=False,
                    error=str(e),
                    duration_ms=duration_ms,
                )
                self._activity_log.complete_entry(entry, "failed", {"error": str(e)})

            if callback:
                callback(result)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    def execute_sync(
        self,
        category: str,
        name: str,
        form_values: dict[str, Any],
    ) -> ExecutionResult:
        """Execute a command synchronously (for testing)."""
        result_holder: list[ExecutionResult] = []
        self.execute(category, name, form_values, lambda r: result_holder.append(r))
        # Wait for completion (simple polling for sync mode)
        import time as _time

        while not result_holder:
            _time.sleep(0.05)
        return result_holder[0]
```

### Phase 3: Unified Activity Log

**Files**: `src/max_cli/interface/tui/activity_log.py`

Merges data from all history sources into a single timeline.

```python
"""Unified activity log for the TUI dashboard."""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class ActivityEntry:
    """A single activity log entry."""

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
        self.category = category  # download, task, file_op, command, ai
        self.action = action
        self.status = status  # pending, success, failed, cancelled
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
    """Unified activity logger with persistence."""

    LOG_FILE = Path.home() / ".max_cli" / "activity_log.json"
    MAX_ENTRIES = 500

    def __init__(self):
        self._entries: list[ActivityEntry] = []
        self._load()

    def _ensure_dir(self) -> None:
        self.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        if not self.LOG_FILE.exists():
            return
        try:
            data = json.loads(self.LOG_FILE.read_text(encoding="utf-8"))
            self._entries = [ActivityEntry.from_dict(e) for e in data]
        except Exception:
            self._entries = []

    def _save(self) -> None:
        self._ensure_dir()
        data = [e.to_dict() for e in self._entries[: self.MAX_ENTRIES]]
        self.LOG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def start_entry(
        self,
        category: str,
        action: str,
        details: Optional[dict[str, Any]] = None,
    ) -> ActivityEntry:
        """Create a pending entry. Returns entry for later completion."""
        entry = ActivityEntry(category=category, action=action, details=details)
        self._entries.insert(0, entry)
        self._save()
        return entry

    def complete_entry(
        self,
        entry: ActivityEntry,
        status: str,
        result: Optional[dict[str, Any]] = None,
    ) -> None:
        """Mark an entry as complete."""
        entry.status = status
        if result:
            entry.details.update(result)
        self._save()

    def add_entry(
        self,
        category: str,
        action: str,
        status: str,
        details: Optional[dict[str, Any]] = None,
        duration_ms: int = 0,
    ) -> ActivityEntry:
        """Add a completed entry in one call."""
        entry = ActivityEntry(
            category=category,
            action=action,
            status=status,
            details=details,
            duration_ms=duration_ms,
        )
        self._entries.insert(0, entry)
        self._save()
        return entry

    def get_entries(
        self,
        limit: int = 100,
        category_filter: Optional[str] = None,
        status_filter: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> list[ActivityEntry]:
        """Get filtered activity entries."""
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
        """Get aggregate statistics."""
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
        """Clear all entries."""
        count = len(self._entries)
        self._entries = []
        self._save()
        return count

    # ─── Importers for legacy history sources ────────────────────────────────

    def import_daemon_history(self) -> int:
        """Import task history from DaemonManager."""
        try:
            from max_cli.core.engines.daemon_manager import DaemonManager

            daemon = DaemonManager()
            history = daemon.get_history(limit=100)
            count = 0
            for task in history:
                entry = ActivityEntry(
                    category="task",
                    action=task.type.value if task.type else "unknown",
                    status=task.status.value if task.status else "unknown",
                    details={
                        "title": task.title or "",
                        "description": task.description or "",
                        "progress": task.progress,
                        "error": task.error or "",
                        "output_path": str(task.output_path) if task.output_path else "",
                    },
                    entry_id=task.id,
                )
                if task.completed_at:
                    entry.timestamp = task.completed_at
                elif task.created_at:
                    entry.timestamp = task.created_at
                self._entries.append(entry)
                count += 1
            self._save()
            return count
        except Exception:
            return 0

    def import_grab_history(self) -> int:
        """Import download history from QueueManager."""
        try:
            from max_cli.core.engines.queue_manager import get_queue_manager

            qm = get_queue_manager()
            history = qm.get_history()
            count = 0
            for item in history:
                entry = ActivityEntry(
                    category="download",
                    action="download_media",
                    status=item.status,
                    details={
                        "url": item.url,
                        "title": item.title or "",
                        "audio_only": item.audio_only,
                        "quality": item.quality,
                        "file_size": item.file_size,
                        "error": item.error or "",
                    },
                    entry_id=item.id,
                )
                if item.completed_at:
                    entry.timestamp = item.completed_at
                else:
                    entry.timestamp = item.added_at
                self._entries.append(entry)
                count += 1
            self._save()
            return count
        except Exception:
            return 0

    def import_transaction_log(self) -> int:
        """Import transaction history."""
        try:
            from max_cli.common.transaction_log import TransactionLog

            groups = TransactionLog.list_groups()
            count = 0
            for group in groups:
                entry = ActivityEntry(
                    category="file_op",
                    action=group["command"],
                    status=group.get("undo_status", group["status"]),
                    details={
                        "group_id": group["group_id"],
                        "operation_count": group["operation_count"],
                    },
                    entry_id=group["group_id"],
                )
                entry.timestamp = group["timestamp"]
                self._entries.append(entry)
                count += 1
            self._save()
            return count
        except Exception:
            return 0

    def import_all(self) -> dict[str, int]:
        """Import from all legacy sources."""
        return {
            "daemon": self.import_daemon_history(),
            "grab": self.import_grab_history(),
            "transactions": self.import_transaction_log(),
        }
```

### Phase 4: Interactive Download Panel

**Files**: `src/max_cli/interface/tui/widgets/download_panel.py`

Full download form with URL input, quality selection, output path, and progress display.

```python
"""Interactive download panel for the TUI dashboard."""

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    Select,
    Static,
    ProgressBar,
)

from max_cli.core.engines.queue_manager import get_queue_manager
from max_cli.interface.tui.activity_log import ActivityLog


class DownloadPanel(Vertical):
    """Interactive download form with progress tracking."""

    def compose(self) -> ComposeResult:
        yield Static("[bold cyan]⬇ Download Media[/bold cyan]", id="download-title")

        with Vertical(id="download-form"):
            yield Input(
                placeholder="Paste URL here (YouTube, Vimeo, etc.)",
                id="download-url",
            )

            with Horizontal(id="download-type-row"):
                yield Label("Type:", id="download-type-label")
                yield Select(
                    [("Video", "video"), ("Audio Only", "audio")],
                    value="video",
                    id="download-type",
                    allow_blank=False,
                )

            with Horizontal(id="download-quality-row"):
                yield Label("Quality:", id="download-quality-label")
                yield Select(
                    [
                        ("360p (Small)", "ss"),
                        ("480p", "s"),
                        ("720p (Medium)", "m"),
                        ("1080p (High)", "h"),
                        ("4K (Best)", "x"),
                    ],
                    value="h",
                    id="download-quality",
                    allow_blank=False,
                )

            yield Input(
                placeholder="Custom resolution (optional, e.g. 1440)",
                id="download-resolution",
                type="integer",
            )

            yield Input(
                placeholder="Output directory (~/Max Downloads)",
                id="download-output",
            )

            with Horizontal(id="download-options"):
                yield Checkbox("Subtitles", value=False, id="download-subs")
                yield Checkbox("Metadata", value=True, id="download-meta")
                yield Checkbox("No Playlist", value=False, id="download-noplaylist")

        with Horizontal(id="download-actions"):
            yield Button("⬇ Download Now", id="btn-download-now", variant="success")
            yield Button("📥 Add to Queue", id="btn-download-queue", variant="primary")

        yield Static("", id="download-progress-label")
        yield ProgressBar(total=100, show_eta=True, id="download-progress")
        yield Static("", id="download-status")

        yield Static("[bold]Recent Downloads[/bold]", id="recent-title")
        yield ScrollableContainer(Static("", id="recent-downloads"), id="recent-scroll")

    def on_mount(self) -> None:
        self._load_recent()

    def _get_output_path(self) -> Path:
        output = self.query_one("#download-output", Input).value.strip()
        if not output:
            output = "~/Max Downloads"
        path = Path(output.replace("~", str(Path.home())))
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _get_params(self) -> dict:
        return {
            "url": self.query_one("#download-url", Input).value.strip(),
            "audio_only": self.query_one("#download-type", Select).value == "audio",
            "quality": self.query_one("#download-quality", Select).value or "h",
            "output_path": self._get_output_path(),
            "subtitles": self.query_one("#download-subs", Checkbox).value,
            "include_metadata": self.query_one("#download-meta", Checkbox).value,
            "no_playlist": self.query_one("#download-noplaylist", Checkbox).value,
        }

    @on(Button.Pressed, "#btn-download-now")
    def _on_download_now(self) -> None:
        url = self.query_one("#download-url", Input).value.strip()
        if not url:
            self.query_one("#download-status", Static).update(
                "[red]Please enter a URL[/red]"
            )
            return

        params = self._get_params()
        self.query_one("#download-status", Static).update(
            "[cyan]Starting download...[/cyan]"
        )

        from max_cli.core.engines.network_engine import NetworkEngine
        from max_cli.common.events import get_emitter
        from max_cli.interface.tui.activity_log import ActivityLog

        activity_log = ActivityLog()
        entry = activity_log.start_entry(
            category="download", action="download_media",
            details={"url": url},
        )

        def _download():
            try:
                engine = NetworkEngine()
                engine.download_media(**params)
                activity_log.complete_entry(entry, "success")
                self.call_from_thread(
                    self.query_one("#download-status", Static).update,
                    "[green]Download complete![/green]",
                )
                self.call_from_thread(self._load_recent)
            except Exception as e:
                activity_log.complete_entry(entry, "failed", {"error": str(e)})
                self.call_from_thread(
                    self.query_one("#download-status", Static).update,
                    f"[red]Download failed: {e}[/red]",
                )

        import threading
        threading.Thread(target=_download, daemon=True).start()

    @on(Button.Pressed, "#btn-download-queue")
    def _on_download_queue(self) -> None:
        url = self.query_one("#download-url", Input).value.strip()
        if not url:
            self.query_one("#download-status", Static).update(
                "[red]Please enter a URL[/red]"
            )
            return

        params = self._get_params()
        qm = get_queue_manager()
        qm.add(
            url=url,
            quality=params["quality"],
            audio_only=params["audio_only"],
            output_path=params["output_path"],
            include_metadata=params["include_metadata"],
            subtitles=params["subtitles"],
            no_playlist=params["no_playlist"],
        )

        activity_log = ActivityLog()
        activity_log.add_entry(
            category="download",
            action="queue_download",
            status="success",
            details={"url": url},
        )

        self.query_one("#download-status", Static).update(
            "[green]Added to queue![/green]"
        )
        self.query_one("#download-url", Input).value = ""

    def _load_recent(self) -> None:
        try:
            qm = get_queue_manager()
            history = qm.get_history()[:10]
            lines = []
            for item in history:
                status_icon = {"completed": "✅", "failed": "❌", "pending": "⏳"}.get(
                    item.status, "•"
                )
                title = item.title or item.url[:40]
                lines.append(f"{status_icon} {title}")
            if not lines:
                lines = ["[dim]No recent downloads[/dim]"]
            self.query_one("#recent-downloads", Static).update("\n".join(lines))
        except Exception:
            pass
```

### Phase 5: File Browser Panel

**Files**: `src/max_cli/interface/tui/widgets/files_panel.py`

Directory tree + file list with action bar.

```python
"""File browser panel for the TUI dashboard."""

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Button,
    DataTable,
    DirectoryTree,
    Input,
    Label,
    Select,
    Static,
)


# File type icons and color mapping
FILE_ICONS = {
    ".mp4": "🎬", ".mkv": "🎬", ".avi": "🎬", ".mov": "🎬", ".webm": "🎬",
    ".mp3": "🎵", ".wav": "🎵", ".flac": "🎵", ".aac": "🎵", ".ogg": "🎵",
    ".jpg": "🖼", ".jpeg": "🖼", ".png": "🖼", ".gif": "🖼", ".webp": "🖼",
    ".pdf": "📄", ".doc": "📝", ".docx": "📝",
    ".py": "🐍", ".js": "📜", ".ts": "📜",
}

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm"}
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".aac", ".ogg"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}
PDF_EXTS = {".pdf"}


def _format_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _get_file_icon(path: Path) -> str:
    ext = path.suffix.lower()
    return FILE_ICONS.get(ext, "📄")


class FilesPanel(Vertical):
    """File browser with directory tree and action bar."""

    def compose(self) -> ComposeResult:
        yield Static("[bold cyan]📁 File Browser[/bold cyan]", id="files-title")

        with Horizontal(id="files-toolbar"):
            yield Input(placeholder="🔍 Filter files...", id="files-filter")
            yield Select(
                [("Name", "name"), ("Size", "size"), ("Type", "type"), ("Date", "date")],
                value="name",
                id="files-sort",
                allow_blank=False,
            )
            yield Button("🔄 Refresh", id="btn-files-refresh", variant="default")

        with Horizontal(id="files-layout"):
            with Vertical(id="files-tree-container"):
                yield DirectoryTree(Path.home(), id="files-tree")
            with Vertical(id="files-list-container"):
                yield DataTable(id="files-table")

        with Horizontal(id="files-actions"):
            yield Button("🖼 Compress", id="btn-file-compress", variant="primary")
            yield Button("📁 Organize", id="btn-file-organize", variant="warning")
            yield Button("🔍 Duplicates", id="btn-file-dupes", variant="default")
            yield Button("💾 Backup", id="btn-file-backup", variant="success")

        yield Static("", id="files-status")

    def on_mount(self) -> None:
        table = self.query_one("#files-table", DataTable)
        table.add_column("", width=4)
        table.add_column("Name", width=40)
        table.add_column("Size", width=12)
        table.add_column("Type", width=10)
        table.add_column("Modified", width=20)
        self._load_files(Path.home())

    @on(DirectoryTree.FileSelected)
    def _on_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        self._load_files(event.path.parent)

    @on(DirectoryTree.DirectorySelected)
    def _on_dir_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        self._load_files(event.path)

    def _load_files(self, directory: Path) -> None:
        table = self.query_one("#files-table", DataTable)
        table.clear()

        try:
            items = list(directory.iterdir())
        except PermissionError:
            table.add_row("", "[red]Permission denied[/red]", "", "", "")
            return

        # Sort
        sort_key = self.query_one("#files-sort", Select).value or "name"
        if sort_key == "name":
            items.sort(key=lambda p: p.name.lower())
        elif sort_key == "size":
            items.sort(key=lambda p: p.stat().st_size if p.is_file() else 0, reverse=True)
        elif sort_key == "date":
            items.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        elif sort_key == "type":
            items.sort(key=lambda p: p.suffix.lower())

        # Directories first
        dirs = [p for p in items if p.is_dir()]
        files = [p for p in items if p.is_file()]

        # Apply filter
        filter_text = self.query_one("#files-filter", Input).value.strip().lower()
        if filter_text:
            dirs = [d for d in dirs if filter_text in d.name.lower()]
            files = [f for f in files if filter_text in f.name.lower()]

        for d in dirs[:50]:
            table.add_row("📁", f"[bold blue]{d.name}/[/bold blue]", "—", "Folder", "")

        for f in files[:200]:
            stat = f.stat()
            icon = _get_file_icon(f)
            size = _format_size(stat.st_size)
            ext = f.suffix.upper().lstrip(".") or "File"
            from datetime import datetime
            modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            table.add_row(icon, f.name, size, ext, modified, key=str(f))

    @on(Input.Changed, "#files-filter")
    def _on_filter(self) -> None:
        tree = self.query_one("#files-tree", DirectoryTree)
        if tree.cursor_node:
            self._load_files(tree.cursor_node.data.path)

    @on(Select.Changed, "#files-sort")
    def _on_sort_changed(self) -> None:
        tree = self.query_one("#files-tree", DirectoryTree)
        if tree.cursor_node:
            self._load_files(tree.cursor_node.data.path)

    @on(Button.Pressed, "#btn-files-refresh")
    def _on_refresh(self) -> None:
        tree = self.query_one("#files-tree", DirectoryTree)
        if tree.cursor_node:
            self._load_files(tree.cursor_node.data.path)

    @on(Button.Pressed, "#btn-file-compress")
    def _on_compress(self) -> None:
        table = self.query_one("#files-table", DataTable)
        if table.cursor_coordinate:
            row = table.get_row_at(table.cursor_coordinate.row)
            file_path = row[4] if len(row) > 4 else None  # key is the path
            self.query_one("#files-status", Static).update(
                f"[cyan]Compress queued for: {file_path}[/cyan]"
            )
```

### Phase 6: Tools Panel (Command Launcher)

**Files**: `src/max_cli/interface/tui/widgets/tools_panel.py`

Dynamic form generator based on the command registry.

```python
"""Command launcher panel with dynamic form generation."""

from pathlib import Path
from typing import Any, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    Select,
    Static,
    Tree,
)

from max_cli.interface.tui.command_executor import CommandExecutor, ExecutionResult
from max_cli.interface.tui.command_registry import (
    CATEGORIES,
    COMMANDS,
    CommandSchema,
    get_all_commands,
    get_categories,
)


class ToolsPanel(Vertical):
    """Command launcher with category tree and dynamic forms."""

    def __init__(self) -> None:
        super().__init__()
        self._executor = CommandExecutor()
        self._current_schema: Optional[CommandSchema] = None
        self._form_values: dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        yield Static("[bold cyan]🛠 Command Launcher[/bold cyan]", id="tools-title")

        with Horizontal(id="tools-layout"):
            with Vertical(id="tools-tree-container"):
                yield Static("[bold]Categories[/bold]", id="tools-cat-label")
                yield Tree("Commands", id="tools-tree")

            with ScrollableContainer(id="tools-form-container"):
                yield Static(
                    "[dim]Select a command from the tree to configure[/dim]",
                    id="tools-form-placeholder",
                )

        yield Static("", id="tools-status")

    def on_mount(self) -> None:
        self._build_tree()

    def _build_tree(self) -> None:
        tree = self.query_one("#tools-tree", Tree)
        tree.clear()

        for cat_key, cat_meta in get_categories().items():
            cat_node = tree.root.add(
                f"{cat_meta['icon']} {cat_meta['label']}", data={"type": "category", "key": cat_key}
            )
            commands = COMMANDS.get(cat_key, {})
            for cmd_key, cmd_schema in commands.items():
                cat_node.add(
                    f"{cmd_schema.icon} {cmd_schema.label}",
                    data={"type": "command", "category": cat_key, "name": cmd_key},
                )
        tree.root.expand()

    @on(Tree.NodeSelected)
    def _on_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if not data or data.get("type") != "command":
            return

        schema = COMMANDS.get(data["category"], {}).get(data["name"])
        if not schema:
            return

        self._current_schema = schema
        self._build_form(schema)

    def _build_form(self, schema: CommandSchema) -> None:
        container = self.query_one("#tools-form-container", ScrollableContainer)
        container.remove_children()

        form = Vertical(id=f"form-{schema.category}-{schema.name}")
        form.mount(
            Static(
                f"[bold]{schema.icon} {schema.label}[/bold]\n[dim]{schema.description}[/dim]",
                id="form-header",
            )
        )

        for field in schema.fields:
            row = Vertical(classes="form-field")
            label = Label(f"{field.label}{' *' if field.required else ''}", classes="field-label")
            row.mount(label)

            if field.help_text:
                row.mount(Label(f"[dim]{field.help_text}[/dim]", classes="field-help"))

            if field.field_type == "bool":
                widget = Checkbox("", value=bool(field.default), id=f"field-{field.name}")
            elif field.field_type == "select":
                options = [(opt, opt.split(" ")[0] if " (" in opt else opt) for opt in field.options]
                default_val = field.default
                if field.default and field.options:
                    for opt in field.options:
                        clean = opt.split(" ")[0]
                        if clean == field.default:
                            default_val = opt
                            break
                widget = Select(options, value=default_val, id=f"field-{field.name}", allow_blank=not field.required)
            elif field.field_type == "int":
                widget = Input(
                    value=str(field.default) if field.default is not None else "",
                    id=f"field-{field.name}",
                    type="integer",
                    placeholder=field.placeholder,
                )
            else:
                widget = Input(
                    value=str(field.default) if field.default is not None else "",
                    id=f"field-{field.name}",
                    placeholder=field.placeholder,
                )

            row.mount(widget)
            form.mount(row)

        with Horizontal(classes="form-actions"):
            form.mount(Button("▶ Execute", id="btn-execute", variant="success"))
            form.mount(Button("📥 Queue", id="btn-queue", variant="primary", id="btn-queue-cmd"))

        container.mount(form)
        self.query_one("#tools-status", Static).update("")

    def _collect_form_values(self) -> dict[str, Any]:
        if not self._current_schema:
            return {}
        values = {}
        for field in self._current_schema.fields:
            widget_id = f"#field-{field.name}"
            widget = self.query_one(widget_id)
            if widget is None:
                continue
            if isinstance(widget, Checkbox):
                values[field.name] = widget.value
            elif isinstance(widget, Select):
                val = widget.value
                if val is not Select.BLANK:
                    values[field.name] = val
            elif isinstance(widget, Input):
                values[field.name] = widget.value
        return values

    @on(Button.Pressed, "#btn-execute")
    def _on_execute(self) -> None:
        if not self._current_schema:
            return

        status = self.query_one("#tools-status", Static)
        status.update("[cyan]Executing...[/cyan]")

        values = self._collect_form_values()

        def on_result(result: ExecutionResult) -> None:
            if result.success:
                self.call_from_thread(
                    status.update,
                    f"[green]{result.message}[/green] ({result.duration_ms}ms)",
                )
            else:
                self.call_from_thread(
                    status.update,
                    f"[red]Error: {result.error}[/red]",
                )

        self._executor.execute(
            self._current_schema.category,
            self._current_schema.name,
            values,
            callback=on_result,
        )
```

### Phase 7: Home Dashboard

**Files**: `src/max_cli/interface/tui/widgets/home_panel.py`

Card grid of common operations + quick stats + recent activity.

```python
"""Home dashboard panel with quick actions and stats."""

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import Button, Label, Static

from max_cli.interface.tui.activity_log import ActivityLog
from max_cli.interface.tui.command_registry import get_quick_actions


class HomePanel(Vertical):
    """Home dashboard with card grid and quick stats."""

    CSS = """
    .home-card {
        width: 24;
        height: 5;
        border: tall $primary-background;
        padding: 1 2;
        margin: 0 1;
    }
    .home-card:hover {
        border: tall $accent;
    }
    .home-card-icon {
        text-align: center;
        text-size: 2;
    }
    .home-card-label {
        text-align: center;
        text-style: bold;
    }
    .stat-box {
        width: 20;
        padding: 0 1;
        border: tall $border;
    }
    .stat-value {
        text-align: center;
        text-style: bold;
        text-size: 1;
    }
    .stat-label {
        text-align: center;
        text-style: dim;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("[bold cyan]⚡ Max Dashboard[/bold cyan]", id="home-title")
        yield Static(
            "[dim]Press [/dim][bold]q[/bold][dim] to quit, [/dim][bold]r[/bold][dim] to refresh[/dim]",
            id="home-hints",
        )

        yield Static("[bold]Quick Actions[/bold]", id="home-actions-title")
        with Horizontal(id="home-cards"):
            for action in get_quick_actions():
                card = Button(
                    f"{action['icon']}\n{action['label']}",
                    id=f"home-card-{action['category']}-{action['name']}",
                    variant="default",
                    classes="home-card",
                )
                yield card

        yield Static("[bold]Quick Stats[/bold]", id="home-stats-title")
        with Horizontal(id="home-stats"):
            yield Static("—", id="stat-queue", classes="stat-box")
            yield Static("—", id="stat-disk", classes="stat-box")
            yield Static("—", id="stat-downloads", classes="stat-box")
            yield Static("—", id="stat-commands", classes="stat-box")

        yield Static("[bold]Recent Activity[/bold]", id="home-recent-title")
        yield ScrollableContainer(Static("", id="home-recent-list"), id="home-recent-scroll")

    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        self._update_stats()
        self._update_recent()

    def _update_stats(self) -> None:
        # Queue count
        try:
            from max_cli.core.engines.queue_manager import get_queue_manager
            qm = get_queue_manager()
            stats = qm.get_stats()
            pending = stats["pending"] + stats["downloading"]
            self.query_one("#stat-queue", Static).update(
                f"[bold]{pending}[/bold]\n[dim]Queue[/dim]"
            )
        except Exception:
            self.query_one("#stat-queue", Static).update("[dim]—[/dim]\n[dim]Queue[/dim]")

        # Disk usage
        max_dir = Path.home() / ".max_cli"
        if max_dir.exists():
            import shutil
            usage = shutil.disk_usage(max_dir)
            gb_used = usage.used / (1024 ** 3)
            self.query_one("#stat-disk", Static).update(
                f"[bold]{gb_used:.1f}GB[/bold]\n[dim]Used[/dim]"
            )
        else:
            self.query_one("#stat-disk", Static).update("[dim]—[/dim]\n[dim]Disk[/dim]")

        # Downloads today
        try:
            activity_log = ActivityLog()
            entries = activity_log.get_entries(limit=50, category_filter="download")
            today_count = sum(1 for e in entries if e.timestamp[:10] == __import__("datetime").datetime.now().isoformat()[:10])
            self.query_one("#stat-downloads", Static).update(
                f"[bold]{today_count}[/bold]\n[dim]Downloads[/dim]"
            )
        except Exception:
            self.query_one("#stat-downloads", Static).update("[dim]—[/dim]\n[dim]Downloads[/dim]")

        # Commands today
        try:
            activity_log = ActivityLog()
            entries = activity_log.get_entries(limit=50, category_filter="command")
            self.query_one("#stat-commands", Static).update(
                f"[bold]{len(entries)}[/bold]\n[dim]Commands[/dim]"
            )
        except Exception:
            self.query_one("#stat-commands", Static).update("[dim]—[/dim]\n[dim]Commands[/dim]")

    def _update_recent(self) -> None:
        try:
            activity_log = ActivityLog()
            entries = activity_log.get_entries(limit=10)
            lines = []
            for entry in entries:
                status_icon = {"success": "✅", "failed": "❌", "pending": "⏳"}.get(
                    entry.status, "•"
                )
                time_str = entry.timestamp[11:19] if len(entry.timestamp) > 19 else ""
                lines.append(f"{status_icon} [{time_str}] {entry.action}")
            if not lines:
                lines = ["[dim]No recent activity[/dim]"]
            self.query_one("#home-recent-list", Static).update("\n".join(lines))
        except Exception:
            pass

    @on(Button.Pressed)
    def _on_card_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("home-card-"):
            parts = button_id.replace("home-card-", "").split("-", 1)
            if len(parts) == 2:
                category, name = parts
                # Navigate to tools panel and select the command
                self.app.post_message(
                    type("NavigateToCommand", (), {"category": category, "name": name})
                )
```

### Phase 8: AI Chat Panel

**Files**: `src/max_cli/interface/tui/widgets/chat_panel.py`

Full chat interface with message history and suggestions.

```python
"""AI chat panel for the TUI dashboard."""

import json
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Button,
    Input,
    Label,
    Static,
)


class ChatPanel(Vertical):
    """AI chat interface with message history."""

    CSS = """
    #chat-messages {
        height: 1fr;
        border: tall $border;
        padding: 1 2;
    }
    .chat-user {
        text-align: right;
        padding: 1 2;
        margin: 1 0;
        background: $primary-darken-3;
    }
    .chat-assistant {
        text-align: left;
        padding: 1 2;
        margin: 1 0;
        background: $surface-darken-1;
    }
    #chat-suggestions {
        height: auto;
        dock: bottom;
    }
    #chat-input-row {
        height: auto;
        dock: bottom;
    }
    #chat-input {
        width: 1fr;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._history: list[dict[str, str]] = []

    def compose(self) -> ComposeResult:
        yield Static("[bold cyan]🤖 Max AI Chat[/bold cyan]", id="chat-title")

        yield ScrollableContainer(
            Static("", id="chat-messages"),
            id="chat-scroll",
        )

        with Horizontal(id="chat-suggestions"):
            yield Button("Organize files", id="sug-1", variant="default")
            yield Button("Compress media", id="sug-2", variant="default")
            yield Button("What can you do?", id="sug-3", variant="default")

        with Horizontal(id="chat-input-row"):
            yield Input(placeholder="Ask Max anything...", id="chat-input")
            yield Button("Send", id="btn-chat-send", variant="success")

        with Horizontal(id="chat-actions"):
            yield Button("🗑 Clear", id="btn-chat-clear", variant="error")
            yield Button("📤 Export", id="btn-chat-export", variant="default")
            yield Button("📥 Import", id="btn-chat-import", variant="default")

    def on_mount(self) -> None:
        self._load_history()

    def _load_history(self) -> None:
        history_file = Path.home() / ".max_cli" / "chat_history.json"
        if history_file.exists():
            try:
                data = json.loads(history_file.read_text(encoding="utf-8"))
                self._history = data.get("history", [])
            except Exception:
                self._history = []
        self._render_messages()

    def _render_messages(self) -> None:
        lines = []
        for msg in self._history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "user":
                lines.append(f"[bold green]You:[/bold green] {content}")
            elif role == "assistant":
                lines.append(f"[bold cyan]Max:[/bold cyan] {content}")
        if not lines:
            lines = ["[dim]Start a conversation with Max AI...[/dim]"]
        self.query_one("#chat-messages", Static).update("\n\n".join(lines))
        # Auto-scroll to bottom
        scroll = self.query_one("#chat-scroll", ScrollableContainer)
        scroll.scroll_end()

    def _send_message(self, text: str) -> None:
        if not text.strip():
            return

        self._history.append({"role": "user", "content": text})
        self._render_messages()

        # Call AI engine
        def _get_response():
            try:
                from max_cli.core.engines.ai_engine import AIEngine
                engine = AIEngine()
                result = engine.interpret_intent(text, None)

                thought = result.get("thought", "")
                command = result.get("command", "")

                response = thought
                if command:
                    response += f"\n\n[dim]Suggested command: {command}[/dim]"

                self._history.append({"role": "assistant", "content": response})
                self.call_from_thread(self._render_messages)
                self.call_from_thread(self._save_history)
            except Exception as e:
                self._history.append(
                    {"role": "assistant", "content": f"[red]Error: {e}[/red]"}
                )
                self.call_from_thread(self._render_messages)

        import threading
        threading.Thread(target=_get_response, daemon=True).start()

    def _save_history(self) -> None:
        history_file = Path.home() / ".max_cli" / "chat_history.json"
        history_file.parent.mkdir(parents=True, exist_ok=True)
        history_file.write_text(
            json.dumps({"history": self._history}, indent=2),
            encoding="utf-8",
        )

    @on(Input.Submitted, "#chat-input")
    def _on_input_submitted(self) -> None:
        inp = self.query_one("#chat-input", Input)
        self._send_message(inp.value)
        inp.value = ""

    @on(Button.Pressed, "#btn-chat-send")
    def _on_send(self) -> None:
        inp = self.query_one("#chat-input", Input)
        self._send_message(inp.value)
        inp.value = ""

    @on(Button.Pressed, "#btn-chat-clear")
    def _on_clear(self) -> None:
        self._history = []
        history_file = Path.home() / ".max_cli" / "chat_history.json"
        if history_file.exists():
            history_file.unlink()
        self._render_messages()

    @on(Button.Pressed, "#btn-chat-export")
    def _on_export(self) -> None:
        export_path = Path.home() / ".max_cli" / f"chat_export_{Path.home().name}.json"
        export_path.write_text(
            json.dumps({"history": self._history}, indent=2),
            encoding="utf-8",
        )
        self.query_one("#chat-status", Static).update(
            f"[green]Exported to {export_path}[/green]"
        )

    @on(Button.Pressed)
    def _on_suggestion(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("sug-"):
            label = event.button.label
            if isinstance(label, str):
                self._send_message(label)
```

### Phase 9: Enhanced System Panel

Add cleanup actions to the existing `system_panel.py`:

```python
# Add to the Horizontal(id="system-actions") block in compose():
yield Button("🧹 Clear Cache", id="btn-clear-cache", variant="warning")
yield Button("🗑 Cleanup Backups", id="btn-cleanup-backups", variant="error")
yield Button("📋 Cleanup Transactions", id="btn-cleanup-txn", variant="default")

# Add new handlers:
@on(Button.Pressed, "#btn-clear-cache")
def _on_clear_cache(self) -> None:
    from max_cli.common.cache import get_default_cache
    cache = get_default_cache()
    count = cache.clear()
    status = self.query_one("#system-status", Static)
    status.update(f"[green]Cleared {count} cache entries[/green]")

@on(Button.Pressed, "#btn-cleanup-backups")
def _on_cleanup_backups(self) -> None:
    from max_cli.core.engines.file_organizer import FileOrganizer
    organizer = FileOrganizer()
    count = organizer.cleanup_old_backups(days=30)
    status = self.query_one("#system-status", Static)
    status.update(f"[green]Removed {count} old backups[/green]")

@on(Button.Pressed, "#btn-cleanup-txn")
def _on_cleanup_txn(self) -> None:
    from max_cli.common.transaction_log import TransactionLog
    groups = TransactionLog.list_groups()
    count = 0
    for group in groups:
        if group.get("undo_status") == "undone":
            path = TransactionLog._storage_dir / f"{group['group_id']}.json"
            if path.exists():
                path.unlink()
                count += 1
    status = self.query_one("#system-status", Static)
    status.update(f"[green]Cleaned {count} resolved transactions[/green]")
```

### Phase 10: Updated App Layout

**Files**: `src/max_cli/interface/tui/app.py`

Update the main app with 8 tabs and new CSS.

```python
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, TabbedContent, TabPane

from max_cli.interface.tui.widgets.config_panel import ConfigPanel
from max_cli.interface.tui.widgets.history_panel import HistoryPanel
from max_cli.interface.tui.widgets.queue_panel import QueuePanel
from max_cli.interface.tui.widgets.system_panel import SystemPanel
from max_cli.interface.tui.widgets.home_panel import HomePanel
from max_cli.interface.tui.widgets.download_panel import DownloadPanel
from max_cli.interface.tui.widgets.files_panel import FilesPanel
from max_cli.interface.tui.widgets.tools_panel import ToolsPanel
from max_cli.interface.tui.widgets.chat_panel import ChatPanel


class MaxDashboardApp(App):
    """Interactive dashboard for Max CLI."""

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("1", "switch_home", "Home"),
        ("2", "switch_download", "Download"),
        ("3", "switch_queue", "Queue"),
        ("4", "switch_history", "History"),
        ("5", "switch_files", "Files"),
        ("6", "switch_tools", "Tools"),
        ("7", "switch_chat", "Chat"),
        ("8", "switch_config", "Config"),
        ("9", "switch_system", "System"),
    ]

    CSS = """
    /* ... existing CSS ... */

    /* New tab-specific styles */
    HomePanel, DownloadPanel, FilesPanel, ToolsPanel, ChatPanel {
        padding: 1 2;
    }

    #tools-layout {
        height: 1fr;
    }

    #tools-tree-container {
        width: 30;
        border: tall $border;
        padding: 1;
    }

    #tools-form-container {
        width: 1fr;
        padding: 1 2;
    }

    .form-field {
        margin: 1 0;
    }

    .field-label {
        text-style: bold;
    }

    .field-help {
        text-style: dim;
    }

    .form-actions {
        margin-top: 2;
    }

    #files-layout {
        height: 1fr;
    }

    #files-tree-container {
        width: 30;
        border: tall $border;
    }

    #files-list-container {
        width: 1fr;
    }

    #files-toolbar {
        height: auto;
        margin-bottom: 1;
    }

    #files-actions {
        dock: bottom;
        height: auto;
        margin-top: 1;
    }

    #download-form {
        padding: 1 2;
        border: tall $border;
    }

    #download-type-row, #download-quality-row, #download-options {
        height: auto;
        margin: 1 0;
    }

    #download-actions {
        dock: bottom;
        height: auto;
        margin-top: 1;
    }

    #recent-scroll {
        height: 10;
        border: solid $border;
    }

    #chat-scroll {
        height: 1fr;
    }

    #chat-input-row {
        height: auto;
        dock: bottom;
    }

    #chat-suggestions {
        height: auto;
        dock: bottom;
    }

    #chat-actions {
        height: auto;
        dock: bottom;
    }

    #home-cards {
        height: auto;
    }

    #home-stats {
        height: auto;
    }

    #home-recent-scroll {
        height: 12;
        border: solid $border;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="home"):
            with TabPane("Home", id="home"):
                yield HomePanel(id="home-panel")
            with TabPane("Download", id="download"):
                yield DownloadPanel(id="download-panel")
            with TabPane("Queue", id="queue"):
                yield QueuePanel(id="queue-panel")
            with TabPane("History", id="history"):
                yield HistoryPanel(id="history-panel")
            with TabPane("Files", id="files"):
                yield FilesPanel(id="files-panel")
            with TabPane("Tools", id="tools"):
                yield ToolsPanel(id="tools-panel")
            with TabPane("Chat", id="chat"):
                yield ChatPanel(id="chat-panel")
            with TabPane("Config", id="config"):
                yield ConfigPanel(id="config-panel")
            with TabPane("System", id="system"):
                yield SystemPanel(id="system-panel")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(2.0, self._refresh_active_panel)
        # Import legacy history on first mount
        self._import_legacy_history()

    def _import_legacy_history(self) -> None:
        """Import from legacy history sources on startup."""
        import threading

        def _import():
            try:
                from max_cli.interface.tui.activity_log import ActivityLog
                log = ActivityLog()
                log.import_all()
            except Exception:
                pass

        threading.Thread(target=_import, daemon=True).start()

    def _refresh_active_panel(self) -> None:
        active = self.query_one(TabbedContent).active
        panel_map = {
            "queue": "#queue-panel",
            "history": "#history-panel",
            "system": "#system-panel",
            "home": "#home-panel",
        }
        if active in panel_map:
            panel = self.query_one(panel_map[active])
            if hasattr(panel, "refresh_data"):
                panel.refresh_data()

    def action_refresh(self) -> None:
        for panel_id in [
            "#queue-panel", "#history-panel", "#system-panel",
            "#home-panel", "#download-panel", "#files-panel",
        ]:
            panel = self.query_one(panel_id)
            if hasattr(panel, "refresh_data"):
                panel.refresh_data()

    # ─── Keyboard shortcuts for tab switching ────────────────────────────────

    def action_switch_home(self) -> None:
        self.query_one(TabbedContent).active = "home"

    def action_switch_download(self) -> None:
        self.query_one(TabbedContent).active = "download"

    def action_switch_queue(self) -> None:
        self.query_one(TabbedContent).active = "queue"

    def action_switch_history(self) -> None:
        self.query_one(TabbedContent).active = "history"

    def action_switch_files(self) -> None:
        self.query_one(TabbedContent).active = "files"

    def action_switch_tools(self) -> None:
        self.query_one(TabbedContent).active = "tools"

    def action_switch_chat(self) -> None:
        self.query_one(TabbedContent).active = "chat"

    def action_switch_config(self) -> None:
        self.query_one(TabbedContent).active = "config"

    def action_switch_system(self) -> None:
        self.query_one(TabbedContent).active = "system"
```

### Phase 11: Enhanced History Panel

Update `history_panel.py` to use the unified activity log:

```python
# Replace the existing refresh_data method in HistoryPanel:

CATEGORY_FILTERS = [
    ("All", "all"),
    ("Downloads", "download"),
    ("Tasks", "task"),
    ("File Ops", "file_op"),
    ("Commands", "command"),
    ("AI", "ai"),
]

def refresh_data(self) -> None:
    from max_cli.interface.tui.activity_log import ActivityLog

    filter_input = self.query_one("#history-filter", Input)
    filter_text = filter_input.value.strip().lower()

    # Get category filter from dropdown (add Select widget if not present)
    category = "all"
    try:
        cat_select = self.query_one("#history-category", Select)
        val = cat_select.value
        if val and val is not Select.BLANK:
            category = val
    except Exception:
        pass

    activity_log = ActivityLog()
    entries = activity_log.get_entries(limit=200, category_filter=category)

    if filter_text:
        entries = [
            e for e in entries
            if filter_text in e.category
            or filter_text in e.action.lower()
            or filter_text in e.id.lower()
            or filter_text in str(e.details).lower()
        ]

    table = self.query_one("#history-table", DataTable)
    table.clear()
    if not table.columns:
        table.add_column("Time", width=20)
        table.add_column("Category", width=12)
        table.add_column("Action", width=24)
        table.add_column("Status", width=12)
        table.add_column("Details", width=40)
        table.add_column("Duration", width=10)

    if not entries:
        table.add_row("", "", "[dim]No activity entries[/dim]", "", "", "")
        return

    for entry in entries:
        time_str = entry.timestamp[:19].replace("T", " ")
        status_color = {
            "success": "green",
            "failed": "red",
            "pending": "yellow",
            "cancelled": "dim",
        }.get(entry.status, "white")

        details_str = ""
        if entry.details:
            if "url" in entry.details:
                details_str = entry.details["url"][:38]
            elif "title" in entry.details:
                details_str = entry.details["title"][:38]
            elif "params" in entry.details:
                details_str = str(entry.details["params"])[:38]

        duration_str = f"{entry.duration_ms}ms" if entry.duration_ms > 0 else ""

        table.add_row(
            time_str,
            entry.category,
            entry.action,
            f"[{status_color}]{entry.status}[/{status_color}]",
            details_str,
            duration_str,
            key=entry.id,
        )

    count_label = self.query_one("#history-count", Label)
    count_label.update(f"[dim]{len(entries)} items[/dim]")
```

## Testing Strategy

### Unit Tests

```python
# tests/interface/tui/test_command_registry.py

from max_cli.interface.tui.command_registry import (
    COMMANDS,
    CATEGORIES,
    CommandField,
    CommandSchema,
    get_command,
    get_all_commands,
    get_categories,
    get_quick_actions,
)


def test_command_registry_has_categories():
    assert "grab" in COMMANDS
    assert "video" in COMMANDS
    assert "images" in COMMANDS
    assert "files" in COMMANDS
    assert "pdf" in COMMANDS
    assert "audio" in COMMANDS
    assert "ai" in COMMANDS


def test_grab_download_schema():
    cmd = get_command("grab", "download")
    assert cmd is not None
    assert cmd.engine == "NetworkEngine"
    assert cmd.method == "download_media"
    assert len(cmd.fields) >= 6
    url_field = next(f for f in cmd.fields if f.name == "url")
    assert url_field.required is True


def test_video_compress_schema():
    cmd = get_command("video", "compress")
    assert cmd is not None
    assert cmd.requires_binary == "ffmpeg"
    crf_field = next(f for f in cmd.fields if f.name == "crf")
    assert crf_field.default == 28


def test_quick_actions():
    actions = get_quick_actions()
    assert len(actions) == 8
    assert all("category" in a and "name" in a for a in actions)


def test_category_metadata():
    cats = get_categories()
    assert "grab" in cats
    assert cats["grab"]["icon"] == "⬇"
    assert cats["grab"]["color"] == "green"
```

```python
# tests/interface/tui/test_activity_log.py

import json
from pathlib import Path
from unittest.mock import patch

from max_cli.interface.tui.activity_log import ActivityEntry, ActivityLog


def test_activity_entry_to_dict():
    entry = ActivityEntry(category="download", action="test", status="success")
    d = entry.to_dict()
    assert d["category"] == "download"
    assert d["status"] == "success"
    assert "id" in d
    assert "timestamp" in d


def test_activity_log_add_and_get(tmp_path):
    log_file = tmp_path / "activity_log.json"
    with patch.object(ActivityLog, "LOG_FILE", log_file):
        log = ActivityLog()
        log.add_entry("download", "test_url", "success", {"url": "http://example.com"})
        log.add_entry("task", "compress", "failed", {"error": "test"})

        entries = log.get_entries(limit=10)
        assert len(entries) == 2
        assert entries[0].action == "compress"  # Most recent first


def test_activity_log_filtering(tmp_path):
    log_file = tmp_path / "activity_log.json"
    with patch.object(ActivityLog, "LOG_FILE", log_file):
        log = ActivityLog()
        log.add_entry("download", "dl1", "success")
        log.add_entry("task", "task1", "success")
        log.add_entry("download", "dl2", "failed")

        downloads = log.get_entries(category_filter="download")
        assert len(downloads) == 2

        failed = log.get_entries(status_filter="failed")
        assert len(failed) == 1


def test_activity_log_stats(tmp_path):
    log_file = tmp_path / "activity_log.json"
    with patch.object(ActivityLog, "LOG_FILE", log_file):
        log = ActivityLog()
        log.add_entry("download", "dl1", "success")
        log.add_entry("task", "task1", "failed")
        log.add_entry("command", "cmd1", "success")

        stats = log.get_stats()
        assert stats["total"] == 3
        assert stats["success"] == 2
        assert stats["failed"] == 1
        assert stats["download"] == 1
```

```python
# tests/interface/tui/test_command_executor.py

from pathlib import Path
from unittest.mock import MagicMock, patch

from max_cli.interface.tui.command_executor import CommandExecutor, ExecutionResult
from max_cli.interface.tui.command_registry import CommandField, CommandSchema


def test_executor_resolve_params():
    executor = CommandExecutor()
    schema = CommandSchema(
        category="test", name="test", label="Test", icon="T",
        engine="TestEngine", method="test_method",
        fields=[
            CommandField("name", "str", "Name", required=True),
            CommandField("count", "int", "Count", default=5),
            CommandField("active", "bool", "Active", default=False),
            CommandField("path", "path", "Path", default="/tmp"),
        ],
    )
    params = executor._resolve_params(schema, {
        "name": "test",
        "count": "10",
        "active": True,
        "path": "/tmp/test",
    })
    assert params["name"] == "test"
    assert params["count"] == 10
    assert params["active"] is True
    assert isinstance(params["path"], Path)


def test_executor_quality_field_parsing():
    executor = CommandExecutor()
    schema = CommandSchema(
        category="grab", name="download", label="Download", icon="⬇",
        engine="NetworkEngine", method="download_media",
        fields=[
            CommandField("url", "str", "URL", required=True),
            CommandField("quality", "select", "Quality", default="h"),
        ],
    )
    params = executor._resolve_params(schema, {
        "url": "http://example.com",
        "quality": "h (1080p)",
    })
    assert params["quality"] == "h"  # Stripped label suffix


@patch("max_cli.interface.tui.command_executor.CommandExecutor._get_engine")
def test_executor_execute_success(mock_get_engine):
    mock_engine = MagicMock()
    mock_engine.process_single_image.return_value = {
        "out_path": Path("/tmp/out.jpg"),
        "reduction_pct": 50.0,
    }
    mock_get_engine.return_value = mock_engine

    executor = CommandExecutor()
    result_holder = []

    executor.execute(
        "images", "compress",
        {"input_path": "/tmp/in.jpg", "output_path": "/tmp/out.jpg"},
        callback=lambda r: result_holder.append(r),
    )

    import time
    time.sleep(0.2)
    assert len(result_holder) == 1
    assert result_holder[0].success is True
```

### TUI Integration Tests

```python
# tests/interface/tui/test_dashboard.py

import pytest

try:
    from textual.testing import run_test
    from max_cli.interface.tui.app import MaxDashboardApp
    HAS_TEXTUAL = True
except ImportError:
    HAS_TEXTUAL = False


@pytest.mark.skipif(not HAS_TEXTUAL, reason="textual not installed")
def test_dashboard_renders():
    """Test that the dashboard app composes without errors."""
    async def test():
        async with MaxDashboardApp().run_test() as pilot:
            # Verify tabs exist
            tabbed = pilot.app.query_one("TabbedContent")
            tabs = [pane.id for pane in tabbed.query("TabPane")]
            assert "home" in tabs
            assert "download" in tabs
            assert "queue" in tabs
            assert "history" in tabs
            assert "files" in tabs
            assert "tools" in tabs
            assert "chat" in tabs
            assert "config" in tabs
            assert "system" in tabs

    run_test(test())


@pytest.mark.skipif(not HAS_TEXTUAL, reason="textual not installed")
def test_tab_switching_keyboard():
    """Test keyboard shortcuts switch tabs."""
    async def test():
        async with MaxDashboardApp().run_test() as pilot:
            # Press '2' to switch to Download tab
            await pilot.press("2")
            tabbed = pilot.app.query_one("TabbedContent")
            assert tabbed.active == "download"

            # Press '6' to switch to Tools tab
            await pilot.press("6")
            assert tabbed.active == "tools"

    run_test(test())


@pytest.mark.skipif(not HAS_TEXTUAL, reason="textual not installed")
def test_download_panel_form():
    """Test download panel renders with all form fields."""
    async def test():
        async with MaxDashboardApp().run_test() as pilot:
            await pilot.press("2")  # Switch to Download tab
            # Verify URL input exists
            url_input = pilot.app.query_one("#download-url")
            assert url_input is not None
            # Verify download buttons exist
            btn_now = pilot.app.query_one("#btn-download-now")
            btn_queue = pilot.app.query_one("#btn-download-queue")
            assert btn_now is not None
            assert btn_queue is not None

    run_test(test())
```

## Migration Path

### Step 1: Create New Files (Week 1)
1. Create `command_registry.py` with full command schemas
2. Create `command_executor.py` with engine dispatcher
3. Create `activity_log.py` with unified logger
4. Run unit tests for all three modules

### Step 2: Create Widget Panels (Week 2)
1. Create `home_panel.py` — card grid + stats
2. Create `download_panel.py` — download form
3. Create `files_panel.py` — file browser
4. Create `tools_panel.py` — command launcher
5. Create `chat_panel.py` — AI chat

### Step 3: Update Existing Files (Week 3)
1. Update `app.py` — new tab layout, CSS, keyboard shortcuts
2. Update `history_panel.py` — unified activity data source
3. Update `system_panel.py` — cleanup action buttons
4. Update `dashboard.py` — ensure graceful fallback if textual is missing

### Step 4: Integration Testing (Week 4)
1. Run full TUI test suite
2. Test each panel individually
3. Test tab switching via keyboard shortcuts
4. Test command execution with mocked engines
5. Test activity log import from legacy sources

### Step 5: Polish & Documentation (Week 5)
1. Add loading spinners for long operations
2. Add error toast notifications
3. Update `README.md` with new `max dashboard` features
4. Update `docs/commands/dashboard.md` with screenshots

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Textual dependency not installed | Dashboard crashes on startup | Graceful fallback in `dashboard.py`: print "Install with `pip install max-cli[tui]`" and exit |
| Engine initialization fails (no FFmpeg) | Command execution crashes | Check `requires_binary` before showing command; show friendly error message |
| Activity log grows too large | Slow loading, high memory | Cap at `MAX_ENTRIES=500`; auto-trim on save |
| Thread safety issues in TUI | UI freezes or crashes | Use `call_from_thread()` for all UI updates from worker threads |
| Command parameter mismatch | Engine method fails | Thorough `_resolve_params()` with type conversion and default fallbacks |
| Legacy history import fails on startup | Slow dashboard launch | Run import in background daemon thread; don't block UI |
| AI chat without API key | Chat panel errors | Catch exception in `_send_message()` and show "Configure AI in Settings" message |

## Success Criteria

1. **All 8 tabs render** without errors when running `max dashboard`
2. **Download panel** can add items to the grab queue and download immediately
3. **Tools panel** can execute at least 5 different commands via the dynamic form
4. **History panel** shows unified activity from all sources (daemon, grab, transactions)
5. **File browser** displays directory contents and allows navigation
6. **Chat panel** can send messages to the AI engine and display responses
7. **Home dashboard** shows accurate quick stats and recent activity
8. **System panel** has working cache/backup/transaction cleanup buttons
9. **Keyboard shortcuts** (1-9) switch between all tabs
10. **All unit tests pass** (`pytest tests/interface/tui/`)
11. **Graceful degradation** when optional dependencies (textual, FFmpeg, AI keys) are missing
12. **No blocking operations** — all long-running commands execute in background threads
