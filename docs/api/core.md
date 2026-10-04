# Core Modules

`max_cli.core` holds the work. It never prints or asks questions: it takes Python values and returns results. The CLI (`max_cli.interface`) and the dashboard print and ask.

## Catalog: `max_cli.core.catalog`

One description per action: its parameters, defaults, CLI spellings, how risky it is, and whether it takes batches or the queue.

```python
from max_cli.core.catalog import get_action, group_names, load_group

group_names()                    # ("video", "grab", "images", "pdf", ...)
action = get_action("pdf.split")
action.params                    # each Param: name, kind, default, help
action.danger                    # SAFE, MOVES, OVERWRITES or DELETES
action.queueable                 # can it go to the background queue?
action.each_param()              # the file param a batch fills, or None
```

## Runner: `max_cli.core.catalog.runner`

| Function | What it does |
|----------|--------------|
| `coerce_args(action, raw_args)` | Turns form strings or JSON into typed arguments, fills defaults, raises `ValidationError` on bad input |
| `run_action(action, raw_args)` | Checks the arguments and runs the operation; returns an `ActionResult` |
| `enqueue_action(action, raw_args, title=None)` | Checks the arguments now and adds one task to the queue |

## Batches: `max_cli.core.catalog.batch`

| Function | What it does |
|----------|--------------|
| `expand_each(action, raw_args, recursive=False, redo=False)` | Turns files, folders and patterns into a `FileBatch`: `files` to run and `done_already` (results that exist) |
| `run_each(action, raw_args, recursive=False, redo=False, on_file=None)` | Runs the files side by side and returns one summed `ActionResult`. `on_file(path, result, error)` hears about each file |
| `enqueue_each(action, raw_args, recursive=False, redo=False)` | Queues one task per file; returns `(tasks, batch)` |
| `is_batch(action, raw_args)` | True for several files, a folder or a pattern |

## Results: `max_cli.core.operations.result.ActionResult`

| Field | Meaning |
|-------|---------|
| `ok` | Whether the action worked |
| `message` | One line for a person |
| `output_files` | The files it made |
| `details` | Numbers and facts (sizes, counts, pages) |
| `undo_group` | The undo log group, when the action changed files |

## Operations: `max_cli.core.operations`

One module per group (`video`, `audio`, `images`, `pdf`, `files`, `grab`, `tools`) with one function per command. Each names its output, checks its input, calls the engine and returns an `ActionResult`. Most take an optional `engine`, so you can pass one that is already set up.

```python
from pathlib import Path

from max_cli.core.operations import pdf

result = pdf.merge([Path("a.pdf"), Path("b.pdf")], Path("both.pdf"))
```

## Task queue: `max_cli.core.engines.task_manager`

```python
from max_cli.core.engines.task_manager import get_task_manager

manager = get_task_manager()     # one per process
manager.refresh()                # read what other processes changed
```

Several processes share one store in `~/.max_cli/tasks/`: the dashboard, CLI commands and the background worker. A file lock guards each change, and only one process runs tasks at a time. `max_cli.core.engines.background_worker.start_background_worker()` starts a detached worker unless one is running.

## AI: `max_cli.core.agent` and `max_cli.core.engines.ai_providers`

- `Agent.from_settings(confirm=..., on_step=None)` builds the agent on the configured provider and raises `ConfigurationError` when no AI is set up. `confirm(call)` decides about risky actions; `on_step(step)` hears each step.
- `Agent.ask(request)` returns an `AgentReply` with `text`, `steps`, `tokens`, `model` and `fallback`.
- `ai_providers.make_client()` returns a client that tries the main provider and moves to the fallback on an API error.

## Engines: `max_cli.core.engines`

The operations call these. Use them when you need a lower-level step.

| Engine | Module | Examples |
|--------|--------|----------|
| `ImageEngine` | `image_processor` | `process_single_image`, `strip_metadata`, `inspect_image` |
| `PDFEngine` | `pdf_engine` | `merge_pdfs`, `compress_pdf`, `split_by_range`, `ocr_pdf`, `fill_form`, `compare_pdfs` |
| `MediaEngine` | `media_engine` | Combines `VideoEngine`, `AudioEngine` and `StreamEngine`, all built on `FFmpegEngine` |
| `AIEngine` | `ai_engine` | `analyze_image_content`, `generate_image`, `semantic_search`, `extract_structured_data` |
| `FileOrganizer` | `file_organizer` | `order_files`, `smart_sort`, `find_duplicates`, `secure_delete`, `create_backup` |

FFmpeg engines find FFmpeg through `max_cli.common.ffmpeg_resolver`: the PATH, then `~/.max_cli/bin/`, then a download.
