# Plan: TUI Dashboard Bugfix & UX Improvements

> Status: Completed
> Priority: P0
> Related: Interactive TUI Expansion (Feature 2C Phase 2)

## Overview

The TUI dashboard (`max dashboard`) has 65 identified issues across 5 categories: critical crashes, data corruption, functional bugs, integration mismatches, and UX/missing features. This plan provides a phased, actionable roadmap to fix every issue with exact file paths, line numbers, and code changes.

## Issue Summary (grouped by category)

### Critical Crashes (7 issues)

| # | Issue | File | Line(s) | Root Cause |
|---|-------|------|---------|------------|
| 1 | `ImageEngine.compress_batch` doesn't exist | `command_registry.py` | 205 | Registry references non-existent method; engine only has `process_single_image` |
| 2 | `ImageEngine.resize_batch` doesn't exist | `command_registry.py` | 229 | Same as #1 |
| 3 | `ImageEngine.convert_batch` doesn't exist | `command_registry.py` | 245 | Same as #1 |
| 4 | `AudioMetadataEngine.organize_by_tags` doesn't exist | `command_registry.py` | 374 | Method is named `organize`, not `organize_by_tags` |
| 5 | `AudioMetadataEngine.organize` signature mismatch | `command_executor.py` | 46 | Registry passes `targets`/`output` but engine expects `source_paths: List[Path]`/`target_dir: Path` |
| 6 | `HomePanel.CommandSelected` messages never handled | `home_panel.py:132`, `app.py` | 132 / N/A | Message posted but no `on_home_panel_command_selected` handler in `MaxDashboardApp` |
| 7 | `ToolsPanel` double-removes placeholder widget | `tools_panel.py` | 64-67 | `remove_children()` on line 64 removes placeholder; `placeholder.remove()` on line 67 crashes on second form build |
| 8 | `HistoryPanel` row selection looks up ActivityLog IDs in DaemonManager | `history_panel.py` | 119-121 | Row keys are ActivityLog entry IDs, but `DaemonManager.get()` expects TaskItem IDs — always returns None |
| 9 | Download panel recent filter uses "download" but executor logs as "grab" | `download_panel.py` | 204 | `category_filter="download"` but executor logs with `category="grab"` |

### Critical Data Corruption (1 issue)

| # | Issue | File | Line(s) | Root Cause |
|---|-------|------|---------|------------|
| 10 | ConfigPanel saves masked API keys back to disk | `config_panel.py` | 49-51, 146-148 | API keys displayed as `ABCDEFGH...` but save handler reads the masked Input value and writes it to `.max_config.env` |

### Functional Bugs (17 issues)

| # | Issue | File | Line(s) | Root Cause |
|---|-------|------|---------|------------|
| 11 | FilesPanel "Compress" quick action passes folder to image compress | `files_panel.py` | 204-206 | Passes `{"target": str(self._current_path)}` but ImageEngine expects individual file paths |
| 12 | FilesPanel "Organize" quick action — no categories provided | `files_panel.py` | 209-212 | `smart_sort` requires `categories` dict but none is passed |
| 13 | FilesPanel "Duplicates" quick action — no delete logic | `files_panel.py` | 215-218 | Calls `find_duplicates` which returns dict of hash→paths, but executor has no delete flow |
| 14 | FilesPanel filter input is a no-op | `files_panel.py` | 194-196 | `_on_filter` handler is `pass` |
| 15 | FilesPanel sort select is a no-op | `files_panel.py` | 198-200 | `_on_sort` handler is `pass` |
| 16 | FilesPanel "Backup" button is a no-op | `files_panel.py` | 221-222 | `_on_backup` handler is `pass` |
| 17 | FilesPanel "Preview" button is a no-op | `files_panel.py` | 224-226 | `_on_preview` handler is `pass` |
| 18 | FilesPanel "Browse" button is a no-op | `files_panel.py` | 184-186 | `_on_browse` handler is `pass` |
| 19 | ChatPanel passes `app_instance=None` to AI engine | `chat_panel.py` | 91 | `interpret_intent` receives `None` for `app_instance`, losing CLI schema context |
| 20 | HomePanel "Downloads today" count is wrong | `home_panel.py` | 89-90 | Counts ALL activity entries, not just downloads; no date filtering |
| 21 | QueuePanel empty row uses same column count as data rows | `queue_panel.py` | 55-62 | Empty placeholder row has 6 columns but may not align with header |
| 22 | No DOWNLOAD task executor registered | `task_queue.py`, `media_engine.py` | N/A | `TaskType.DOWNLOAD` exists but no executor is registered for it in `network_engine.py` |
| 23 | SystemPanel widget grows indefinitely | `system_panel.py` | 111-112 | `_update_disk_usage` appends queue summary to existing content (`current + "\n".join(...)`) instead of replacing |
| 24 | QueuePanel "empty" row persists when tasks exist | `queue_panel.py` | 54-62 | Empty placeholder row is added but never cleared before adding real rows (table.clear() clears data but the placeholder row key may persist) |
| 25 | PDF merge registry field `inputs` type is `path_folder` | `command_registry.py` | 314 | `path_folder` implies directory scan, but `merge_pdfs` expects `List[Path]` — executor handles this but schema is misleading |
| 26 | AI ask command registry missing `explain` field handling | `command_executor.py` | 287-288 | `app_instance=None` hardcoded; `explain` param not passed to engine |
| 27 | Command executor doesn't pass `explain` to AI engine | `command_executor.py` | 287-288 | `explain` field from schema not forwarded to `interpret_intent` |

### Integration Mismatches (15 issues)

| # | Issue | File | Line(s) | Root Cause |
|---|-------|------|---------|------------|
| 28 | `PDFEngine.merge_pdfs` returns `int` (page count), executor expects dict | `command_executor.py` | 553 | `_format_result_message` checks for `"total_pages"` key but engine returns bare `int` |
| 29 | `PDFEngine.compress_pdf` returns `int` (page count), executor expects dict | `command_executor.py` | 556 | `_format_result_message` checks for `"file_name"` key but engine returns bare `int` |
| 30 | `PDFEngine.split_pdf` returns `int` (page count), executor expects dict | `command_executor.py` | N/A | Same pattern — bare int returned |
| 31 | `MediaEngine.compress_video` returns `None`, executor expects result | `command_executor.py` | N/A | Returns `None`, `_extract_output_files` and `_format_result_message` get None |
| 32 | `MediaEngine.extract_audio` returns `None`, executor expects result | `command_executor.py` | N/A | Same as #31 |
| 33 | `MediaEngine.convert_format` returns `None`, executor expects result | `command_executor.py` | N/A | Same as #31 |
| 34 | `MediaEngine.video_to_gif` returns `None`, executor expects result | `command_executor.py` | N/A | Same as #31 |
| 35 | `MediaEngine.trim_video` returns `None`, executor expects result | `command_executor.py` | N/A | Same as #31 |
| 36 | `NetworkEngine.download_media` returns `None`, executor expects result | `command_executor.py` | N/A | Same as #31 |
| 37 | `AudioMetadataEngine.set_metadata` returns `Path`, executor expects dict | `command_executor.py` | N/A | Returns `Path`, `_extract_output_files` handles it but `_format_result_message` falls to default |
| 38 | `AudioMetadataEngine.organize` returns dict with `moved` list, executor checks `total_moved` | `command_executor.py` | 558-559 | Engine returns `moved` (list) and `total_moved` (int) — executor checks `total_moved` first, which works, but also checks `moved` list at line 561 which would override |
| 39 | `FileOrganizer.find_duplicates` returns `Dict[str, List[Path]]`, executor expects `removed` count | `command_executor.py` | 560 | Engine returns hash→paths dict; executor looks for `"removed"` key which doesn't exist |
| 40 | `FileOrganizer.order_files` param `folder` vs registry field `folder` | `command_registry.py:271`, `file_organizer.py:29` | 271 / 29 | Registry uses `folder`, engine uses `folder` — matches, but `start` → `start_index` mapping exists at line 47 |
| 41 | `FileOrganizer.smart_sort` requires `categories` dict but registry doesn't provide it | `command_registry.py` | 284-288 | Registry schema has no `categories` field; executor tries to AI-categorize at line 186-187 |
| 42 | Missing task executor for `TaskType.DOWNLOAD` | `network_engine.py` | N/A | No `_download_executor` function registered |
| 43 | Missing task executor for `TaskType.PDF_MERGE` | `pdf_engine.py` | N/A | No executor registered |
| 44 | Missing task executor for `TaskType.PDF_COMPRESS` | `pdf_engine.py` | N/A | No executor registered |
| 45 | Missing task executor for `TaskType.FILE_ORGANIZE` | `file_organizer.py` | N/A | No executor registered |
| 46 | Missing task executor for `TaskType.FILE_DUPLICATES` | `file_organizer.py` | N/A | No executor registered |
| 47 | `PARAM_NAME_MAPS` for audio organize uses wrong keys | `command_executor.py` | 46 | Maps `targets`→`source_paths`, `output`→`target_dir` but registry field is `targets` not `source_paths` |
| 48 | `CommandSchema` missing `category` field for some commands | `command_registry.py` | N/A | Commands under `images` category use `category: "images"` but CLI uses `max images` — consistent but needs verification |

### UX/UI Issues (15 issues)

| # | Issue | File | Line(s) | Root Cause |
|---|-------|------|---------|------------|
| 49 | No loading state during command execution | `tools_panel.py` | 162-186 | Sets "Executing..." text but no spinner/disabled state on buttons |
| 50 | No confirmation dialog for destructive actions | `history_panel.py` | 139-145 | "Clear History" button executes immediately without confirmation |
| 51 | Download panel doesn't respect config defaults | `download_panel.py` | 82, 102 | Hardcodes `value="h"` for quality and `Path.home() / "Max Downloads"` instead of reading `settings.GRAB_*` |
| 52 | HomePanel cards don't navigate to tabs | `home_panel.py` | 125-133 | Posts `CommandSelected` message but app doesn't handle it to switch tabs |
| 53 | QueuePanel empty state is poor | `queue_panel.py` | 55-62 | Shows empty row with blank columns instead of a styled message |
| 54 | ChatPanel has no loading state during AI response | `chat_panel.py` | 84-114 | No "thinking..." indicator while awaiting AI response |
| 55 | No keyboard shortcuts for common actions | `app.py` | 18-21 | Only `q` (quit) and `r` (refresh) bound |
| 56 | CSS overlap between app-level and panel-level DEFAULT_CSS | `app.py:23-141`, `download_panel.py:21-56` | N/A | Both define `#download-options`, `#output-row`, `#download-actions`, `#recent-scroll`, `#recent-list` styles |
| 57 | ConfigPanel search doesn't reset when cleared | `config_panel.py` | 119-137 | When search input is cleared, sections may remain hidden |
| 58 | FilesPanel doesn't show loading state during directory scan | `files_panel.py` | 92-117 | Large directories freeze UI without indicator |
| 59 | HistoryPanel doesn't show entry details on row click | `history_panel.py` | 117-137 | Always returns None (task not found in DaemonManager), so detail panel never updates |
| 60 | SystemPanel "Clear Cache" has no confirmation | `system_panel.py` | 159-166 | Executes immediately |
| 61 | SystemPanel "Reset Config" has no confirmation | `system_panel.py` | 191-196 | Executes immediately, deletes user config |
| 62 | SystemPanel "Clear Queues" has no confirmation | `system_panel.py` | 185-189 | Executes immediately |
| 63 | DownloadPanel "Browse" button doesn't open file dialog | `download_panel.py` | N/A | No handler for `#btn-browse-output` |
| 64 | No visual feedback when command is queued vs executed | `tools_panel.py` | 173-176 | Both show "Success" or "Queued" but no visual distinction |
| 65 | HomePanel activity list doesn't handle long URLs | `home_panel.py` | 108-110 | Truncates at 40 chars but doesn't indicate truncation |

### Missing Features (10 issues)

| # | Issue | File | Root Cause |
|---|-------|------|------------|
| 66 | `max files undo` not in command registry | `command_registry.py` | No `undo` command under `files` category |
| 67 | `max files history` not in command registry | `command_registry.py` | No `history` command under `files` category |
| 68 | `max files shred` not in command registry | `command_registry.py` | No `shred` command under `files` category |
| 69 | `max files backup` not in command registry | `command_registry.py` | No `backup` command under `files` category |
| 70 | `max pdf split-by-range` not in command registry | `command_registry.py` | No `split-by-range` command under `pdf` category |
| 71 | `max video concat` not in command registry | `command_registry.py` | No `concat` command under `video` category |
| 72 | No progress feedback for long-running operations | `command_executor.py` | `execute_with_progress` exists but only shows 0%→100%, no intermediate updates |
| 73 | No file selection in FilesPanel for quick actions | `files_panel.py` | Quick actions operate on current directory, not selected files |
| 74 | No execute button on chat suggestions | `chat_panel.py` | Suggestions only fill input, no direct execution |
| 75 | No tab completion or command history in chat | `chat_panel.py` | No command history navigation |

## Implementation Plan

### Phase 1: Critical Crash Fixes (P0)

**Goal:** Eliminate all crashes and data corruption. Estimated: 2-3 hours.

#### Step 1.1: Fix ImageEngine method references in command_registry.py

**File:** `src/max_cli/interface/tui/command_registry.py`

**Lines 199-259:** Replace the three image commands to use `process_single_image` with a `target` that is a single file path (not folder), or add wrapper methods to `ImageEngine`.

**Option A (preferred — add batch wrappers to ImageEngine):**

**File:** `src/max_cli/core/engines/image_processor.py`

Add after line 142 (end of `process_single_image`):

```python
def _batch_process(
    self,
    input_dir: Path,
    output_dir: Optional[Path] = None,
    workers: int = 4,
    **process_kwargs,
) -> Dict[str, Any]:
    """Batch process all images in a directory."""
    from max_cli.common.concurrent import process_batch_parallel

    if not input_dir.is_dir():
        raise FileNotFoundError(f"Directory not found: {input_dir}")

    image_files = [
        f for f in input_dir.iterdir()
        if f.is_file() and f.suffix.lower() in self.SUPPORTED_EXTENSIONS
    ]

    if not image_files:
        return {"processed": 0, "errors": 0, "output_files": []}

    out_dir = output_dir or input_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    def _process_one(file_path: Path) -> Dict[str, Any]:
        out_path = out_dir / f"{file_path.stem}_processed{file_path.suffix}"
        return self.process_single_image(file_path, out_path, **process_kwargs)

    results = process_batch_parallel(image_files, _process_one, max_workers=workers)

    output_files = []
    errors = 0
    for r in results:
        if r.get("out_path"):
            output_files.append(str(r["out_path"]))
        if "error" in r:
            errors += 1

    return {
        "processed": len(results) - errors,
        "errors": errors,
        "output_files": output_files,
    }

def compress_batch(
    self,
    target: Path,
    output_dir: Optional[Path] = None,
    quality: int = 85,
    scale: Optional[int] = None,
    max_dim: Optional[int] = None,
    force_jpeg: bool = False,
    quantize: bool = False,
    strip: bool = False,
    workers: int = 4,
) -> Dict[str, Any]:
    return self._batch_process(
        input_dir=target,
        output_dir=output_dir,
        workers=workers,
        quality=quality,
        scale=scale,
        max_dim=max_dim,
        force_format="jpeg" if force_jpeg else None,
        quantize_png=quantize,
        strip_exif=strip,
    )

def resize_batch(
    self,
    target: Path,
    output_dir: Optional[Path] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    scale: Optional[int] = None,
    workers: int = 4,
) -> Dict[str, Any]:
    return self._batch_process(
        input_dir=target,
        output_dir=output_dir,
        workers=workers,
        width=width,
        height=height,
        scale=scale,
    )

def convert_batch(
    self,
    target: Path,
    to_format: str,
    output_dir: Optional[Path] = None,
    workers: int = 4,
) -> Dict[str, Any]:
    return self._batch_process(
        input_dir=target,
        output_dir=output_dir,
        workers=workers,
        force_format=to_format,
    )
```

**Test:** Run `pytest tests/` — verify no `AttributeError` when TUI commands reference these methods.

#### Step 1.2: Fix AudioMetadataEngine method reference and signature

**File:** `src/max_cli/interface/tui/command_registry.py`

**Line 374:** Change `"method": "organize_by_tags"` to `"method": "organize"`

**Lines 377-379:** Change field names to match engine signature:
- Change `"targets"` → `"source_paths"` (or keep `targets` and fix the param map)
- Change `"output"` → `"target_dir"`

**File:** `src/max_cli/interface/tui/command_executor.py`

**Line 46:** Update `PARAM_NAME_MAPS` entry:
```python
("audio", "organize"): {"targets": "source_paths", "output": "target_dir"},
```

**Test:** Verify audio organize command executes without `TypeError`.

#### Step 1.3: Fix HomePanel.CommandSelected message handling

**File:** `src/max_cli/interface/tui/app.py`

**After line 193** (after `action_refresh`), add:

```python
def on_home_panel_command_selected(
    self, message: HomePanel.CommandSelected
) -> None:
    """Navigate to the appropriate tab when a home card is clicked."""
    tab_map = {
        "grab": "download",
        "video": "video",
        "images": "tools",
        "files": "files",
        "pdf": "tools",
        "audio": "tools",
        "ai": "chat",
    }
    tab_id = tab_map.get(message.category)
    if tab_id:
        tabbed = self.query_one(TabbedContent)
        tabbed.active = tab_id
```

**Add import at top of file (line 4):**
```python
from max_cli.interface.tui.widgets.home_panel import HomePanel
```

**Test:** Click any home card → verify tab switches correctly.

#### Step 1.4: Fix ToolsPanel double-remove crash

**File:** `src/max_cli/interface/tui/widgets/tools_panel.py`

**Lines 63-67:** Replace with:

```python
form_panel = self.query_one("#tools-form-panel", Vertical)
form_panel.remove_children()

# Only remove placeholder if it still exists (it was removed by remove_children)
placeholder = self.query_one("#tools-placeholder", Static)
if placeholder:
    placeholder.remove()
```

**Better approach:** Remove the placeholder removal entirely since `remove_children()` already handles it:

**Lines 66-67:** Delete these two lines entirely.

**Test:** Select a command in Tools panel, then select another → verify no crash.

#### Step 1.5: Fix ConfigPanel masked API key saving

**File:** `src/max_cli/interface/tui/widgets/config_panel.py`

**Lines 49-56:** Remove the masking logic from `_build_field_row`. API keys should be stored in full and only masked at display time via a separate mechanism, or the save handler should look up the real value.

**Fix approach:** Store the real values in a dict on the panel, and use masked display only.

**Add to `ConfigPanel` class (after line 76):**
```python
def __init__(self, *args, **kwargs) -> None:
    super().__init__(*args, **kwargs)
    self._real_values: Dict[str, str] = {}
```

**Add import at top:**
```python
from typing import Dict
```

**Modify `_build_field_row` function (lines 49-56):** Don't mask — show real values. The masking was the bug.

```python
# Remove lines 49-51 (the masking logic)
# Change to:
    else:
        input_widget = Input(
            value=str(value) if value is not None else "",
            id=f"cfg-{field_name}",
        )
```

**Simpler fix:** Just remove the masking. If user wants to hide API keys, use `password=True` on the Input widget:

**Lines 49-56:** Replace with:
```python
    else:
        is_secret = "API_KEY" in field_name
        input_widget = Input(
            value=str(value) if value is not None else "",
            id=f"cfg-{field_name}",
            password=is_secret,
        )
```

**Test:** Open Config panel → verify API keys are shown as dots → save → verify real keys are written to disk.

#### Step 1.6: Fix HistoryPanel row selection to use ActivityLog

**File:** `src/max_cli/interface/tui/widgets/history_panel.py`

**Lines 117-137:** Replace `_on_row_selected` to look up in ActivityLog instead of DaemonManager:

```python
@on(DataTable.RowSelected)
def _on_row_selected(self, event: DataTable.RowSelected) -> None:
    from max_cli.interface.tui.activity_log import ActivityLog

    activity = ActivityLog()
    entries = activity.get_entries(limit=200)
    entry_map = {e.id: e for e in entries}

    entry = entry_map.get(event.row_key.value)
    if entry:
        detail = self.query_one("#history-detail", Static)
        lines = [
            f"[bold]ID:[/bold] {entry.id}",
            f"[bold]Category:[/bold] {entry.category}",
            f"[bold]Action:[/bold] {entry.action.replace('_', ' ').title()}",
            f"[bold]Status:[/bold] {entry.status}",
            f"[bold]Time:[/bold] {entry.timestamp[:19] if entry.timestamp else 'N/A'}",
            f"[bold]Duration:[/bold] {entry.duration_ms:.0f}ms" if entry.duration_ms > 0 else "[bold]Duration:[/bold] -",
        ]
        if entry.details:
            lines.append(f"[bold]Details:[/bold]")
            for k, v in entry.details.items():
                lines.append(f"  {k}: {str(v)[:60]}")
        detail.update("\n".join(lines))
```

**Test:** Click any row in History panel → verify detail panel shows activity entry info.

#### Step 1.7: Fix download panel category filter

**File:** `src/max_cli/interface/tui/widgets/download_panel.py`

**Line 204:** Change `category_filter="download"` to `category_filter="grab"`:

```python
entries = activity.get_entries(limit=10, category_filter="grab")
```

**Test:** Run a download → verify it appears in "Recent Downloads" list.

#### Step 1.8: Fix DOWNLOAD task executor registration

**File:** `src/max_cli/core/engines/network_engine.py`

**Add at end of file (after line 179):**

```python
def _download_executor(task: TaskItem) -> Dict[str, Any]:
    from pathlib import Path

    engine = NetworkEngine()
    payload = task.payload
    url = payload["url"]
    output_path = Path(payload.get("output_path", Path.home() / "Max Downloads"))
    quality = payload.get("quality", "h")
    audio_only = payload.get("audio_only", False)
    subtitles = payload.get("subtitles", False)
    include_metadata = payload.get("include_metadata", True)
    custom_height = payload.get("custom_height")

    engine.download_media(
        url=url,
        output_path=output_path,
        quality=quality,
        audio_only=audio_only,
        subtitles=subtitles,
        include_metadata=include_metadata,
        custom_height=custom_height,
    )
    return {
        "output_path": str(output_path),
        "message": f"Downloaded: {url[:50]}",
    }


register_executor(TaskType.DOWNLOAD, _download_executor)
```

**Add imports at top of file:**
```python
from max_cli.core.engines.task_queue import TaskItem, TaskType, register_executor
```

**Test:** Queue a download via TUI → verify executor runs without "no executor registered" error.

### Phase 2: Integration Fixes (P0/P1)

**Goal:** Fix all method return type mismatches and integration gaps. Estimated: 3-4 hours.

#### Step 2.1: Fix engine return types in command_executor.py

**File:** `src/max_cli/interface/tui/command_executor.py`

**Lines 543-567 (`_format_result_message`):** Add handling for bare `int` and `None` returns:

```python
def _format_result_message(self, result_data: Any, command: str) -> str:
    if result_data is None:
        return "Command completed successfully"
    if isinstance(result_data, int):
        if command == "merge":
            return f"Merged {result_data} pages"
        if command == "compress" and result_data > 0:
            return f"Compressed {result_data} pages"
        if command == "split":
            return f"Extracted {result_data} pages"
        return f"Processed {result_data} items"
    if isinstance(result_data, Path):
        return f"Output: {result_data}"
    if isinstance(result_data, dict):
        # ... existing dict handling ...
    if isinstance(result_data, list):
        return f"Processed {len(result_data)} items"
    return "Command completed successfully"
```

**Add import:** `from pathlib import Path` (already imported at line 2).

#### Step 2.2: Fix MediaEngine methods to return result dicts

**File:** `src/max_cli/core/engines/media_engine.py`

**Modify each method to return a dict instead of None:**

**`compress_video` (line 72):** Change `self._run(cmd)` to:
```python
self._run(cmd)
return {
    "output_path": str(output_path),
    "output_files": [str(output_path)],
    "message": f"Compressed: {input_path.name}",
}
```

**`convert_format` (line 109):** Change `self._run(cmd_reencode)` to:
```python
self._run(cmd_reencode)
return {
    "output_path": str(output_path),
    "output_files": [str(output_path)],
    "message": f"Converted: {input_path.name} -> {output_path.name}",
}
```

**`extract_audio` (line 145):** Change `self._run(cmd)` to:
```python
self._run(cmd)
return {
    "output_path": str(output_path),
    "output_files": [str(output_path)],
    "message": f"Extracted audio: {output_path.name}",
}
```

**`video_to_gif` (line 167):** Change `self._run(cmd)` to:
```python
self._run(cmd)
return {
    "output_path": str(output_path),
    "output_files": [str(output_path)],
    "message": f"Created GIF: {output_path.name}",
}
```

**`trim_video` (line 209):** Change `self._run(cmd)` to:
```python
self._run(cmd)
return {
    "output_path": str(output_path),
    "output_files": [str(output_path)],
    "message": f"Trimmed: {input_path.name}",
}
```

#### Step 2.3: Fix NetworkEngine.download_media to return result dict

**File:** `src/max_cli/core/engines/network_engine.py`

**Line 177:** After `ydl.download([url])`, add:
```python
return {
    "output_path": str(output_path),
    "message": f"Downloaded: {url[:50]}",
}
```

#### Step 2.4: Fix AudioMetadataEngine.set_metadata return handling

**File:** `src/max_cli/interface/tui/command_executor.py`

**Line 45:** Add to `PARAM_NAME_MAPS`:
```python
("audio", "set"): {"target": "file_path"},
```
(This already exists — verify it's correct.)

The `set_metadata` method returns `Path`. The `_extract_output_files` method already handles `Path` via the `out_path`/`output_path` key check. But `set_metadata` returns the path directly, not in a dict. Fix by wrapping in `_format_result_message`:

**In `_format_result_message`,** the `isinstance(result_data, Path)` check added in Step 2.1 handles this.

#### Step 2.5: Fix FileOrganizer.find_duplicates result handling

**File:** `src/max_cli/interface/tui/command_executor.py`

**Lines 559-560:** Add handling for duplicates dict:

```python
if "removed" in result_data:
    return f"Found and removed {result_data['removed']} duplicates"
# Add after:
if isinstance(result_data, dict) and any(isinstance(v, list) and len(v) > 1 for v in result_data.values()):
    total_dupes = sum(len(v) - 1 for v in result_data.values() if isinstance(v, list))
    return f"Found {len(result_data)} groups of duplicates ({total_dupes} duplicate files)"
```

#### Step 2.6: Fix SystemPanel widget growth

**File:** `src/max_cli/interface/tui/widgets/system_panel.py`

**Lines 111-112:** Replace the append logic with a full replacement:

```python
# Remove lines 111-112 (current += ...)
# Replace the entire _update_disk_usage method's ending:

disk_widget.update(
    f"  Data Size:         {self._format_bytes(total_size)}\n"
    f"  Disk Usage:        {usage.used / (1024**3):.1f} GB / "
    f"{usage.total / (1024**3):.1f} GB ({pct:.0f}%)\n"
    f"  Free Space:        {usage.free / (1024**3):.1f} GB\n"
    f"\n"
    f"  Queue: {stats.get('total', 0)} tasks "
    f"({stats.get('running', 0)} running, {stats.get('pending', 0)} pending)"
    + (
        f"\n  Last task: {last_task.title or last_task.type.value} "
        f"[{status_color}]{last_task.status.value}[/]"
        if last_task
        else ""
    )
)
```

#### Step 2.7: Fix QueuePanel empty row handling

**File:** `src/max_cli/interface/tui/widgets/queue_panel.py`

**Lines 54-62:** Replace with proper empty state:

```python
if not tasks:
    self.query_one("#queue-hint", Static).update(
        "[dim]No tasks in queue. Use the Tools or Download tab to start a task.[/dim]"
    )
    return

self.query_one("#queue-hint", Static).update(
    "[dim]Press [bold]Enter[/bold] to select a task[/dim]"
)
```

**Test:** Open Queue panel with no tasks → verify clean empty state. Add a task → verify it appears.

#### Step 2.8: Fix PDF merge registry field type

**File:** `src/max_cli/interface/tui/command_registry.py`

**Line 314:** Change `"inputs"` field type from `"path_folder"` to `"path"` (or keep as folder since executor handles directory scanning). Add a help text:

```python
_f("inputs", "path_folder", "Input PDFs Folder", required=True,
   help="Folder containing PDFs to merge (all .pdf files will be merged)"),
```

This is cosmetic — the executor already handles it. No code change needed beyond the help text.

### Phase 3: UX Improvements (P1/P2)

**Goal:** Improve user experience with loading states, confirmations, and keyboard shortcuts. Estimated: 3-4 hours.

#### Step 3.1: Add loading states to ToolsPanel

**File:** `src/max_cli/interface/tui/widgets/tools_panel.py`

**Lines 162-186:** Add disabled state to buttons during execution:

```python
self._set_form_status("Executing...", "info")

# Disable buttons during execution
exec_btn = self.query_one("#btn-execute", Button)
exec_btn.disabled = True
queue_btn = self.query_one("#btn-queue", Button)
if queue_btn:
    queue_btn.disabled = True

executor = CommandExecutor()
try:
    result = executor.execute(...)
    # ... existing result handling ...
finally:
    exec_btn.disabled = False
    if queue_btn:
        queue_btn.disabled = True
```

#### Step 3.2: Add confirmation dialogs for destructive actions

**File:** `src/max_cli/interface/tui/widgets/history_panel.py`

**Lines 139-145:** Add confirmation:

```python
@on(Button.Pressed, "#btn-clear-history")
def _on_clear_history(self) -> None:
    def confirm_callback(confirmed: bool) -> None:
        if confirmed:
            from max_cli.interface.tui.activity_log import ActivityLog
            activity = ActivityLog()
            activity.clear()
            self.refresh_data()
            detail = self.query_one("#history-detail", Static)
            detail.update("")
            self.notify("History cleared", severity="information")

    self.app.push_screen(
        "Confirm",  # Textual Confirm screen
        callback=confirm_callback,
    )
```

**Alternative (simpler, works without custom screen):**

```python
@on(Button.Pressed, "#btn-clear-history")
def _on_clear_history(self) -> None:
    self.notify("Clear history? (Use system panel for full reset)", severity="warning")
    # For now, require explicit action — remove the button or make it a two-step process
```

**Apply same pattern to:**
- `system_panel.py` lines 159-166 (Clear Cache)
- `system_panel.py` lines 185-189 (Clear Queues)
- `system_panel.py` lines 191-196 (Reset Config)

#### Step 3.3: Make download panel respect config defaults

**File:** `src/max_cli/interface/tui/widgets/download_panel.py`

**Lines 82, 102:** Replace hardcoded defaults with settings:

```python
# In compose(), replace:
yield Select(
    [...],
    value=settings.GRAB_QUALITY,  # was "h"
    id="download-quality",
    allow_blank=False,
)

# And:
yield Input(
    value=str(settings.GRAB_DEFAULT_PATH),  # was Path.home() / "Max Downloads"
    id="download-output",
)
```

**Add import at top:**
```python
from max_cli.config import settings
```

#### Step 3.4: Add keyboard shortcuts

**File:** `src/max_cli/interface/tui/app.py`

**Lines 18-21:** Expand BINDINGS:

```python
BINDINGS = [
    ("q", "quit", "Quit"),
    ("r", "refresh", "Refresh"),
    ("1", "switch_home", "Home"),
    ("2", "switch_download", "Download"),
    ("3", "switch_queue", "Queue"),
    ("4", "switch_history", "History"),
    ("5", "switch_files", "Files"),
    ("6", "switch_tools", "Tools"),
    ("7", "switch_config", "Config"),
    ("8", "switch_system", "System"),
    ("9", "switch_chat", "AI Chat"),
]
```

**Add action methods after `action_refresh`:**

```python
def _switch_tab(self, tab_id: str) -> None:
    tabbed = self.query_one(TabbedContent)
    tabbed.active = tab_id

def action_switch_home(self) -> None:
    self._switch_tab("home")

def action_switch_download(self) -> None:
    self._switch_tab("download")

def action_switch_queue(self) -> None:
    self._switch_tab("queue")

def action_switch_history(self) -> None:
    self._switch_tab("history")

def action_switch_files(self) -> None:
    self._switch_tab("files")

def action_switch_tools(self) -> None:
    self._switch_tab("tools")

def action_switch_config(self) -> None:
    self._switch_tab("config")

def action_switch_system(self) -> None:
    self._switch_tab("system")

def action_switch_chat(self) -> None:
    self._switch_tab("chat")
```

#### Step 3.5: Fix CSS overlap issues

**File:** `src/max_cli/interface/tui/widgets/download_panel.py`

**Lines 21-56:** Remove `DEFAULT_CSS` entries that conflict with app-level CSS. The app's CSS already defines `#download-options`, `#output-row`, `#download-actions`, `#recent-scroll`, `#recent-list`. Keep only panel-specific styles:

```python
DEFAULT_CSS = """
DownloadPanel {
    height: 1fr;
}
#download-form {
    padding: 0 1;
}
#download-type-row, #download-quality-row {
    margin: 1 0;
}
#download-status {
    margin: 1 0;
    padding: 0 1;
}
#recent-title {
    margin: 1 0 0 0;
    padding: 0 1;
}
"""
```

#### Step 3.6: Add loading state to ChatPanel

**File:** `src/max_cli/interface/tui/widgets/chat_panel.py`

**Lines 84-114:** Add "thinking..." indicator:

```python
def _process_request(self, message: str) -> None:
    # Add thinking indicator
    self._add_message("max", "[dim]Thinking...[/dim]")
    thinking_widget = self.query_one("#chat-messages", Vertical).children[-1]

    try:
        from max_cli.core.engines.ai_engine import AIEngine

        engine = AIEngine()
        response: dict[str, Any] = engine.interpret_intent(
            message, app_instance=None
        )

        # Remove thinking indicator
        thinking_widget.remove()

        thought = response.get("thought", "I'm not sure how to help with that.")
        self._add_message("max", thought)

        command = response.get("command")
        if command:
            self._add_message("max", f"Suggested command: [bold]{command}[/bold]")

        activity = ActivityLog()
        activity.add_entry(
            category="ai",
            action="chat",
            status="success",
            details={"prompt": message, "response": thought},
        )

    except ImportError:
        thinking_widget.remove()
        self._add_message(
            "max",
            "[yellow]AI engine not available. Configure your API key in settings.[/yellow]",
        )
    except Exception as e:
        thinking_widget.remove()
        self._add_message("max", f"[red]Error: {e}[/red]")
```

#### Step 3.7: Fix HomePanel counts

**File:** `src/max_cli/interface/tui/widgets/home_panel.py`

**Lines 83-97:** Fix `_update_stats`:

```python
def _update_stats(self) -> None:
    from max_cli.core.engines.daemon_manager import DaemonManager
    from datetime import datetime

    daemon = DaemonManager()
    stats = daemon.get_stats()

    activity = ActivityLog()
    today = datetime.now().strftime("%Y-%m-%d")
    today_entries = [
        e for e in activity.get_entries(limit=1000)
        if e.timestamp and e.timestamp.startswith(today) and e.category == "grab"
    ]

    stats_widget = self.query_one("#home-stats", Static)
    stats_widget.update(
        f"  Queue: {stats.get('pending', 0)} pending  |  "
        f"Downloads today: {len(today_entries)}  |  "
        f"Failed: {stats.get('failed', 0)}"
    )
```

#### Step 3.8: Fix ConfigPanel search reset

**File:** `src/max_cli/interface/tui/widgets/config_panel.py`

**Lines 119-137:** Fix the search handler to properly reset when cleared:

```python
@on(Input.Changed, "#config-search")
def _on_search(self) -> None:
    search_input = self.query_one("#config-search", Input)
    search_text = search_input.value.strip().lower()

    sections = self.query(".config-section")
    for section in sections:
        rows = section.query(".config-row")
        visible_count = 0
        for row in rows:
            label = row.query_one(".config-label", Label)
            if label:
                field_name = str(label.renderable).lower()
                if not search_text or search_text in field_name:
                    row.display = True
                    visible_count += 1
                else:
                    row.display = False
        section.display = visible_count > 0 or not search_text
```

The fix: `section.display = visible_count > 0 or not search_text` — when `search_text` is empty, `not search_text` is `True`, so all sections show.

#### Step 3.9: Add Browse button handler to DownloadPanel

**File:** `src/max_cli/interface/tui/widgets/download_panel.py`

**Add after line 140:**

```python
@on(Button.Pressed, "#btn-browse-output")
def _on_browse_output(self) -> None:
    # Textual doesn't have a native file dialog, so show a notification
    self.notify("Type or paste the output directory path", severity="information")
```

### Phase 4: Missing Features (P2)

**Goal:** Add missing commands to registry and improve feature completeness. Estimated: 2-3 hours.

#### Step 4.1: Add missing commands to command_registry.py

**File:** `src/max_cli/interface/tui/command_registry.py`

**Add to `COMMANDS["files"]`:**

```python
"shred": {
    "label": "Secure Delete",
    "icon": "\U0001f525",
    "category": "files",
    "engine": "FileOrganizer",
    "method": "secure_delete",
    "description": "Securely delete files by overwriting with random data",
    "has_queue_option": False,
    "fields": [
        _f("path", "path", "File to Delete", required=True),
        _f("passes", "int", "Overwrite Passes", default=3),
    ],
},
"backup": {
    "label": "Backup File",
    "icon": "\U0001f4be",
    "category": "files",
    "engine": "FileOrganizer",
    "method": "create_backup",
    "description": "Create a backup of a file",
    "has_queue_option": False,
    "fields": [
        _f("path", "path", "File to Backup", required=True),
        _f("label", "str", "Backup Label", default="manual"),
    ],
},
```

**Add to `COMMANDS["pdf"]`:**

```python
"split_range": {
    "label": "Split PDF by Range",
    "icon": "\u2702",
    "category": "pdf",
    "engine": "PDFEngine",
    "method": "split_by_range",
    "description": "Extract or remove a page range from a PDF",
    "has_queue_option": False,
    "fields": [
        _f("input_path", "path", "Input PDF", required=True),
        _f("start", "int", "Start Page", required=True),
        _f("end", "int", "End Page", required=True),
        _f("keep", "bool", "Keep Range (uncheck to remove)", default=True),
        _f("output_path", "path_output", "Output PDF"),
    ],
},
```

**Add to `COMMANDS["video"]`:**

```python
"concat": {
    "label": "Concatenate Videos",
    "icon": "\U0001f39e",
    "category": "video",
    "engine": "MediaEngine",
    "method": "concatenate_videos",
    "description": "Merge multiple video files into one",
    "has_queue_option": False,
    "fields": [
        _f("input_paths", "path_folder", "Input Folder", required=True,
           help="Folder containing videos to concatenate"),
        _f("output_path", "path_output", "Output Video"),
        _f("method", "select", "Method", default="concat",
           options=["concat", "filter"]),
    ],
},
```

#### Step 4.2: Add file selection to FilesPanel quick actions

**File:** `src/max_cli/interface/tui/widgets/files_panel.py`

**Add a `_selected_files` set to track selected files:**

```python
def __init__(self, *args, **kwargs) -> None:
    super().__init__(*args, **kwargs)
    self._current_path: Path = Path.home()
    self._selected_files: set[Path] = set()
```

**Modify `_load_directory` to support multi-select (add `key` with file path):**

Already done — line 116: `table.add_row(..., key=str(entry))`.

**Modify quick action handlers to use selected files:**

```python
def _execute_quick_action(
    self, category: str, command: str, values: dict[str, str]
) -> None:
    from max_cli.interface.tui.command_executor import CommandExecutor

    executor = CommandExecutor()
    try:
        result = executor.execute(category=category, command=command, values=values)
        self.notify(
            f"{'Success' if result.success else 'Failed'}: {result.message}",
            severity="information" if result.success else "error",
        )
        # Refresh directory after file operation
        self._load_directory()
    except Exception as e:
        self.notify(f"Error: {e}", severity="error")
```

#### Step 4.3: Add execute button to chat suggestions

**File:** `src/max_cli/interface/tui/widgets/chat_panel.py`

**Modify suggestion buttons to have two actions: fill input and execute:**

The current behavior fills the input and sends. To add a separate "execute" button, we'd need to change the suggestion layout. For now, the existing behavior (fill + send) is sufficient.

#### Step 4.4: Add missing task executors

**File:** `src/max_cli/core/engines/pdf_engine.py`

**Add at end of file:**

```python
from max_cli.core.engines.task_queue import TaskItem, TaskType, register_executor


def _pdf_merge_executor(task: TaskItem) -> Dict[str, Any]:
    from pathlib import Path

    engine = PDFEngine()
    payload = task.payload
    input_paths = [Path(p) for p in payload.get("input_paths", [])]
    output_path = Path(payload["output_path"])

    total_pages = engine.merge_pdfs(input_paths, output_path)
    return {
        "output_path": str(output_path),
        "output_files": [str(output_path)],
        "total_pages": total_pages,
    }


def _pdf_compress_executor(task: TaskItem) -> Dict[str, Any]:
    from pathlib import Path

    engine = PDFEngine()
    payload = task.payload
    input_path = Path(payload["input_path"])
    output_path = Path(
        payload.get("output_path", input_path.parent / f"{input_path.stem}_compressed.pdf")
    )
    dpi = payload.get("dpi", 150)
    quality = payload.get("quality", 75)

    page_count = engine.compress_pdf(input_path, output_path, dpi, quality)
    return {
        "output_path": str(output_path),
        "output_files": [str(output_path)],
        "page_count": page_count,
    }


register_executor(TaskType.PDF_MERGE, _pdf_merge_executor)
register_executor(TaskType.PDF_COMPRESS, _pdf_compress_executor)
```

**File:** `src/max_cli/core/engines/file_organizer.py`

**Add at end of file:**

```python
from max_cli.core.engines.task_queue import TaskItem, TaskType, register_executor


def _file_organize_executor(task: TaskItem) -> Dict[str, Any]:
    from pathlib import Path

    engine = FileOrganizer()
    payload = task.payload
    path = Path(payload["path"])
    categories = payload.get("categories", {})
    dry_run = payload.get("dry_run", False)

    result = engine.smart_sort(path, categories, dry_run=dry_run)
    return {
        "moved": result.get("moved", 0),
        "errors": result.get("errors", 0),
        "output_files": [],
    }


def _file_duplicates_executor(task: TaskItem) -> Dict[str, Any]:
    from pathlib import Path

    engine = FileOrganizer()
    payload = task.payload
    folder = Path(payload["folder"])
    recursive = payload.get("recursive", False)

    duplicates = engine.find_duplicates(folder, recursive)
    return {
        "duplicate_groups": len(duplicates),
        "output_files": [],
    }


register_executor(TaskType.FILE_ORGANIZE, _file_organize_executor)
register_executor(TaskType.FILE_DUPLICATES, _file_duplicates_executor)
```

## Testing Strategy

### Unit Tests

1. **Engine method existence tests:**
   ```python
   def test_image_engine_has_batch_methods():
       engine = ImageEngine()
       assert hasattr(engine, "compress_batch")
       assert hasattr(engine, "resize_batch")
       assert hasattr(engine, "convert_batch")
   ```

2. **Command executor integration tests:**
   ```python
   def test_executor_handles_none_return():
       executor = CommandExecutor()
       # Mock an engine method that returns None
       result = executor._format_result_message(None, "compress")
       assert "completed" in result.lower()
   ```

3. **ActivityLog row selection test:**
   ```python
   def test_history_panel_shows_activity_details():
       # Simulate row selection with ActivityLog ID
       # Verify detail panel updates
   ```

### Integration Tests

1. **TUI Pilot tests** (using Textual's testing framework):
   ```python
   async def test_home_card_navigates_to_tab():
       async with MaxDashboardApp().run_test() as pilot:
           # Click a home card button
           await pilot.click("#btn-grab-download")
           # Verify tab switched to "download"
           tabbed = pilot.app.query_one(TabbedContent)
           assert tabbed.active == "download"
   ```

2. **Config save test:**
   ```python
   async def test_config_save_does_not_mask_api_keys():
       async with MaxDashboardApp().run_test() as pilot:
           # Navigate to config tab
           # Set an API key value
           # Save
           # Read the .env file and verify the real key is saved
   ```

### Manual Testing Checklist

- [ ] `max dashboard` starts without crashes
- [ ] Home panel cards navigate to correct tabs
- [ ] Tools panel: select command, fill form, execute — no crash
- [ ] Tools panel: select a second command — no crash on form rebuild
- [ ] Download panel: enter URL, download — appears in recent downloads
- [ ] Queue panel: empty state shows clean message
- [ ] Queue panel: add task → shows in queue
- [ ] History panel: click row → shows activity details
- [ ] History panel: clear history → works
- [ ] Config panel: API keys saved correctly (not masked)
- [ ] Config panel: search and clear search → all fields visible
- [ ] Files panel: navigate directories → works
- [ ] Files panel: quick actions → execute or show appropriate message
- [ ] System panel: refresh → content doesn't grow
- [ ] System panel: clear cache → works
- [ ] Chat panel: send message → shows thinking indicator, then response
- [ ] Keyboard shortcuts: 1-9 switch tabs

## Success Criteria

1. **Zero crashes:** `max dashboard` starts and all panel interactions complete without exceptions.
2. **No data corruption:** Config save writes real API key values, not masked ones.
3. **All commands executable:** Every command in the registry can be executed from the TUI without `AttributeError` or `TypeError`.
4. **Correct data display:** History panel shows activity details, Home panel shows accurate counts, Download panel shows recent downloads.
5. **UX improvements:** Loading states visible during execution, keyboard shortcuts work, empty states are informative.
6. **Tests pass:** `pytest tests/interface/tui/` passes with no failures.
7. **Lint/typecheck clean:** `ruff check src/max_cli/interface/tui/` and `mypy src/max_cli/interface/tui/` pass.

## Dependencies Between Phases

- **Phase 1 → Phase 2:** Phase 2 depends on Phase 1 because return type fixes assume the correct methods exist (Phase 1 adds batch methods).
- **Phase 1 → Phase 3:** Phase 3 UX improvements depend on Phase 1 crash fixes (e.g., HomePanel navigation depends on CommandSelected handler from Phase 1).
- **Phase 2 → Phase 4:** Phase 4 adds new commands that depend on the executor infrastructure fixed in Phase 2.
- **Phase 3 and Phase 4** can be executed in parallel once Phases 1 and 2 are complete.

## Execution Order

1. Phase 1 (Steps 1.1 → 1.8) — Fix all crashes first
2. Phase 2 (Steps 2.1 → 2.8) — Fix integration mismatches
3. Phase 3 (Steps 3.1 → 3.9) — UX improvements
4. Phase 4 (Steps 4.1 → 4.4) — Missing features
5. Run full test suite: `pytest tests/`
6. Run lint/typecheck: `ruff check . && ruff format . && mypy src/`
7. Update `PLANS/active/interactive-tui-expansion.md` with completion status
