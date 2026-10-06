# Agents.md - Max CLI

## 1. Project Identity & Archetype

- **Name**: Max CLI
- **Type**: High-Performance Modular CLI Framework
- **Primary Language**: Python 3.9+
- **Paradigm**: OOP / Modular Monolith (Strict Interface vs. Core separation)
- **Runtime**: Native Python
- **Key Frameworks**: Typer (CLI Layer), Rich (TUI/Formatting), Pillow/PyMuPDF/yt-dlp (Core Logic), Pydantic (Config)

## 2. Essential Commands (File-Scoped)

Use these commands for rapid, file-scoped feedback during development:

```bash
# Development
pip install -e .[dev]          # Install in editable mode with dev dependencies
python -m build                # Build package for distribution

# Testing
pytest                         # Run all tests
pytest [path/to/test.py]       # Run specific test file
pytest [path] -k [test_name]   # Run specific test function

# Quality Assurance
ruff check [path]              # Lint specific file/directory
ruff check --fix [path]        # Auto-fix linting issues
ruff format [path]             # Format specific file/directory
mypy [path]                    # Type-check specific file/module
```

## 3. Project Architecture Map

Max CLI strictly separates business logic from the user interface using a Modular Monolith approach:

```text
src/max_cli/
├── core/                      # DOMAIN / BUSINESS LOGIC
│   ├── presets.py             # Defaults shared by CLI and TUI (CRF levels, bitrates, output names)
│   ├── engines/               # Sub-domain logic (image, pdf, ai, network)
│   ├── catalog/               # One description per action: params, defaults, danger level (feeds CLI checks, dashboard forms, agent tools)
│   ├── operations/            # The work behind each catalog action; returns ActionResult, never prompts or prints
│   └── cli/                   # registry.py (lazy group table) + lazy_group.py + plugin commands
├── interface/                 # ADAPTERS / CLI LAYER
│   ├── cli_*.py               # Typer command definitions (No business logic)
│   └── config/                # CLI config wizards
├── common/                    # SHARED / INFRASTRUCTURE
│   ├── archives.py            # safe_extract_tar: use for every tar extraction
│   ├── atomic.py              # atomic_write_text/json: use for every state file
│   ├── file_kinds.py          # kind_of(path): video, audio, image, pdf ... from the suffix
│   ├── settings_file.py       # read/update ~/.max_config.env key by key
│   ├── cache.py               # Centralized caching
│   ├── concurrent.py          # Parallel processing workers
│   ├── exceptions.py          # Custom MaxError classes
│   └── logger.py              # Rich TUI formatting
├── plugins/                   # EXTENSIBILITY
│   ├── base.py                # Plugin abstract base classes
│   └── manager.py             # Discovery and lifecycle
└── config.py                  # Global settings via Pydantic

tests/                         # Pytest test suite
PLANS/                         # Project Management (Active/Deferred tasks)
```

## 4. Code Standards & Patterns

### Naming Conventions

- **Modules/Files**: `snake_case.py`
- **Classes/Engines**: `PascalCase` (e.g., `ImageEngine`, `TaskManager`)
- **Functions/Methods**: `snake_case` (Private methods prefixed with `_`)
- **Constants**: `UPPER_SNAKE_CASE`

### Code Organization Principles

- **Separation of Concerns**: `interface/` files parse CLI arguments and print output. `core/engines/` files perform the actual computation and return data.
- **Dependency Direction**: Interface → Core → Common. Core engines must *never* import from `interface/`.
- **Import Organization**: Standard library → third-party → local imports (alphabetically sorted).
- **Lazy Loading Mandate**: All heavy third-party imports (PIL, fitz, yt_dlp, openai, mutagen, requests) MUST be placed inside the methods that use them, never at module level. Interface files MUST NOT instantiate engines at module level — use `_get_engine()` helper functions instead.

### Lazy Loading Pattern (MANDATORY)

Max CLI enforces lazy loading to keep `import max_cli.main` under 200ms (about 90ms since hardening D5; `tests/test_startup_time.py` asserts it). Heavy imports are deferred until first use.

**Command groups load lazily too.** The root app uses `LazyTyperGroup` (`core/cli/lazy_group.py`). Each built-in group is one entry in `_GROUPS` in `core/cli/registry.py`: module path, help line, hidden flag. `max --help` lists the groups from that table without importing them, and `max <group> ...` imports only that group's `interface/cli_*.py`. To add a group, add an entry there; don't import `interface` modules from `registry.py` or `main.py`.

**Engine Files (`core/engines/*.py`)** — Move heavy imports inside methods:
```python
# WRONG — module-level import (loads at startup)
from PIL import Image

class ImageEngine:
    def compress(self, path):
        img = Image.open(path)

# CORRECT — lazy import (loads only when called)
class ImageEngine:
    def compress(self, path):
        from PIL import Image
        img = Image.open(path)
```

**Interface Files (`interface/cli_*.py`)** — Use `_get_engine()` helpers, never module-level instantiation:
```python
# WRONG — engine created at module import time
from max_cli.core.engines.image_processor import ImageEngine
app = typer.Typer()
engine = ImageEngine()

# CORRECT — engine created only when a command runs
app = typer.Typer()

def _get_engine():
    from max_cli.core.engines.image_processor import ImageEngine
    return ImageEngine()

@app.command("compress")
def compress_images(...):
    engine = _get_engine()
    engine.compress(...)
```

**Testing with Lazy Imports** — Mock at the package level, not the module level:
```python
# WRONG — OpenAI is no longer at module level in ai_engine
@patch("max_cli.core.engines.ai_engine.OpenAI")

# CORRECT — mock the actual package
@patch("openai.OpenAI")
```

### Design Patterns to Follow

- **Engine Pattern (Strategy)**: Domain logic is wrapped in stateless Engine classes (e.g., `AIEngine`, `MediaEngine`).
- **Decorator Pattern**: Typer commands are defined using `@app.command()`.
- **Plugin Architecture**: Optional dependencies should be handled via the Plugin system (`CLIPlugin`, `EnginePlugin`).

## 5. Quality Gates & Workflow

### Pre-Commit Requirements

- [ ] All tests pass (`pytest tests/`)
- [ ] Type checking does not regress: `python scripts/mypy_baseline.py` passes. CI fails if the mypy error count rises above `mypy-baseline.txt`. After you fix errors, run it with `--update` to lock in the lower count. Ignore missing stubs per package in `mypy.ini`, never globally.
- [ ] Code is formatted and linted cleanly (`ruff check . && ruff format .`)
- [ ] `PLANS/active/` markdown files are updated if fulfilling a planned task.
- [ ] Before you open a PR, run `python scripts/ci_local.py --full` on a clean tree. It runs ruff, the mypy ratchet and the tests with coverage on Python 3.9 to 3.12 in fresh uv virtualenvs, then builds the package. The guard hook refuses `gh pr create` until HEAD has passed it. The quick mode (no flag) covers pushes; `--install-hook` makes `git push` run it. `tests/test_ci_local.py` fails when the script's Python versions or coverage floor drift from `.github/workflows/ci.yml`, so change both together.

### Git & Task Standards

- If a task takes too long (e.g., fighting type checkers on 3rd-party libs), mark it `[D]` (Deferred) in the `PLANS/` system and move on.
- Update `README.md` and `docs/` ONLY if user-facing behavior, CLI commands, or installation steps change.
- Commit messages follow Conventional Commits (`feat`, `fix`, `perf`, `docs`, `test`, `refactor`, `chore`, `ci`; `!` or a `BREAKING CHANGE:` line for a break): the type decides the next release. No Claude attribution in commits or PR text.
- Versions follow Semantic Versioning, with the rules for major, minor and patch in `docs/contributing.md` ("Versions and Releases"). When asked to bump the version, use the `max-release` skill: `scripts/release_plan.py` suggests the level from the commits since the last tag, you recommend one with reasons and wait for the maintainer's choice, then update `pyproject.toml` and `CHANGELOG.md`, merge, tag `vX.Y.Z` and check PyPI. The Release workflow publishes the tag's `CHANGELOG.md` section as the release notes.

### Automated Enforcement (Claude Code hooks & skills)

`.claude/settings.json` wires hooks that enforce this file mechanically:

- **PostToolUse `check_rules.py`**: after every Python edit it runs `ruff check --fix`. It also runs `ruff format`, but only on files that were already formatted at HEAD. Then it runs AST checks for this file's rules: lazy heavy imports, no UI or print in core, layering, `os.path`, `shell=True`, utf-8 encoding, `/tmp`, hardcoded ffmpeg, silent broad excepts, `extractall` filter, direct `write_text` (use `max_cli.common.atomic`), reason-less `# type: ignore`, and Python 3.9 syntax. It blocks only violations the edit *introduced* compared with HEAD. Run `python .claude/hooks/check_rules.py --audit src/max_cli` for a full debt report.
- **PreToolUse `guard.py`**: denies `--no-verify`, force-push, `.env` edits, and `gh pr create` before `scripts/ci_local.py --full` has passed for HEAD. It asks before `pip install <pkg>`, `git reset --hard` and `pyproject.toml` edits.
- **Stop `stop_gate.py`**: when Python changed during the session, it runs `ruff check` plus `pytest -x` before the agent may finish. It blocks once, then warns.

Project skills in `.claude/skills/`: `max-add-command` (end-to-end command checklist), `max-testing` (fixtures and mocks), `max-review` (pre-commit review and known bug classes), `max-plans` (PLANS lifecycle), `max-release` (which version comes next, and shipping it) and `max-tui-design` (the dashboard's design system: read it before building or redesigning any dashboard page). Add a rule to `check_rules.py` when a new rule in this file can be checked mechanically.

The same folder holds vetted third-party skills: `systematic-debugging`, `test-driven-development`, `verification-before-completion`, `python-testing-patterns`, `python-type-safety`, `python-error-handling`, `ruff`, `sharp-edges`, `textual-builder` and `handoff` (session handovers in `.claude/handoffs/`; read the newest one first when resuming work). Each starts with a **Project overrides (Max CLI)** block that wins over the upstream text. `.claude/skills/THIRD_PARTY.md` records their sources, commits and licenses. Before you add another external skill, read it in full, add an override block and record it there.

## 6. Boundaries & Permissions

### ✅ Always Do

- Use existing utilities from `max_cli.common` (`@retry`, `process_batch_parallel`, `format_size`).
- Put defaults that both the CLI and the TUI use (quality levels, bitrates, output file names) in `max_cli.core.presets` and import them in both. `tests/interface/tui/test_preset_drift.py` fails when a TUI field default differs from the CLI option with the same name.
- Use custom exceptions from `max_cli.common.exceptions` (`MaxError`, `ResourceNotFoundError`).
- Use `console`, `log_success`, and `log_error` from `max_cli.common.logger` for user output in the `interface/` layer.
- Use the event system (`EventEmitter` from `max_cli.common.events`, `EventSubscriber` from `max_cli.interface.event_subscriber`) for progress tracking — never pass Rich UI objects into core/common functions.
- Use the task queue system (`TaskManager` from `max_cli.core.engines.task_manager`, `TaskItem`/`TaskType` from `max_cli.core.engines.task_queue`) for long-running operations — add `--queue` flag to heavy commands.
- Add type hints to all function signatures.

### ⚠️ Ask First Before

- Adding new heavy third-party dependencies (e.g., ML libraries, large binaries).
- Making breaking changes to existing CLI command signatures.
- Modifying `pyproject.toml` dependencies or entry points.

### 🚫 Never Do

- Never expose raw stack traces to the user (wrap top-level calls in try/except).
- Ask before a command moves, overwrites or deletes files through `interface/confirm.skip_confirmation(force)`: it honours `--force` and `CONFIRM_DESTRUCTIVE`. The dashboard's `ActionForm` does the same through `asks_first`; `files shred` asks either way.
- Report failures with `log_error`. It marks the run as failed (`common/exit_status.py`), and `main()` exits 1 even when the command returns normally. Don't print errors with a bare `console.print`, or scripts see exit 0.
- Never use `print()` or `typer.echo()` inside `core/engines/` (Engines return values; Interfaces print them).
- Never commit secrets, API keys, or `.env` files.
- Never use `os.path` (strictly use `pathlib.Path`).
- Never import heavy third-party libraries at module level (PIL, fitz, yt_dlp, openai, mutagen, requests) — always use lazy imports inside methods.
- Never instantiate Engine classes at module level in interface files — always use `_get_engine()` helper functions.
- Never import engine instances from other interface files (e.g., `from cli_ai import engine`) — use local `_get_engine()` calls instead.
- Never hardcode `"ffmpeg"` in subprocess commands — always use `str(self.ffmpeg_path)` from the resolved path.
- Never hardcode `/tmp/` paths — always use `tempfile.gettempdir()` or `Path.home() / ".max_cli"`.
- Never use unquoted type annotations for `TYPE_CHECKING` imports — always use `"ClassName"` string quotes in function signatures.

## 7. Reference Implementations

- **Good Example - Core/Interface Separation**:
  - Interface: `src/max_cli/interface/cli_images.py`
  - Operation: `src/max_cli/core/operations/images.py` (finds the images, names the outputs, runs the batch)
  - Core: `src/max_cli/core/engines/image_processor.py` (open every image through `open_image`: Pillow's formats, SVG drawn by resvg-py with PyMuPDF as the fallback, HEIC through pillow-heif when installed; `OUTPUT_FORMATS` says what Max writes, and formats without transparency get a white background; `presets.IMAGE_FORMATS` lists `convert --to`)
  - *Shows: How the CLI parses args and calls the operation, which drives the Engine and returns an `ActionResult` whose details the CLI formats into a Rich table.*
  
- **Utility Pattern**: `src/max_cli/common/concurrent.py`
  - *Shows: Standardized ThreadPoolExecutor implementation used across the app.*
  
- **Plugin Pattern**: `examples/plugins/hello_world.py` (the manager takes only concrete `Plugin` classes defined in the plugin's own module, uses its module-level `plugin` instance, and records a plugin that fails to build or load instead of stopping `max`)
  - *Shows: Correct plugin metadata definition, lifecycle hooks, and Typer command registration.*

- **Lazy Loading Pattern**:
  - Engine: `src/max_cli/core/engines/image_processor.py` (PIL imported inside methods)
  - Interface: `src/max_cli/interface/cli_images.py` (uses `_get_engine()` helper)
  - *Shows: Heavy imports deferred until first use, keeping startup under 200ms.*

- **Event-Driven Progress Pattern**:
  - Events: `src/max_cli/common/events.py` (EventEmitter, event models)
  - Subscriber: `src/max_cli/interface/event_subscriber.py` (Rich UI updates)
  - Batch: `src/max_cli/common/concurrent.py` (emits events, zero Rich imports)
  - Operation: `src/max_cli/core/operations/images.py` (takes an optional `emitter` and hands it to the batch)
  - Interface: `src/max_cli/interface/cli_images.py` (subscribes an EventSubscriber and passes the emitter in)
  - *Shows: Core emits pure events, interface translates to Rich progress bars. Core stays 100% UI-agnostic.*

- **Command Catalog Pattern** (roadmap Step 2, `PLANS/active/command-catalog.md`; ported groups: `video`, `images`, `pdf`, `files`, `audio`, `tools`, and `grab download`, whose CLI calls the operation but keeps its own flags):
  - Operation: `src/max_cli/core/operations/video.py`. One function per command. It does the output naming, input checks and engine calls, and returns `ActionResult`. It takes an optional `engine`, so the CLI can pass one that asks before downloading FFmpeg.
  - Catalog: `src/max_cli/core/catalog/groups/video.py`. One `Action` per command: its params (kind, default, CLI spellings), `danger`, `queueable` and `surfaces`. A default of `Setting("GRAB_QUALITY")` reads the user's config when the action runs; the operation then takes `None` for it. `multiple=True` marks a list (several arguments or a repeated option on the CLI, a JSON array for the agent, `;`-separated text in a form). `ParamKind.SECRET` is masked in forms; keep actions with one off the agent's `surfaces`. Catalog modules import no engines.
  - Interface: `src/max_cli/interface/cli_media.py` parses options, calls the operation through `_run` and prints the result.
  - Batches: a FILE param with `each=True` (and `kinds`, the file kinds a folder gives) runs once per file, while the operation keeps one path. `Action.output_name` ("{stem}_compressed.mp4") names the default result; `tests/test_catalog_batch.py` runs every templated operation with a fake engine and checks the template. `core/catalog/batch.py`: `expand_each` (files, folders, patterns, `recursive`; folder and pattern finds skip files whose result exists and Max's own results, unless `redo`; named files always run; a name that exists is a file even with `[ ]` in it; files whose results would share a name go to `FileBatch.clashes` and don't run; `output`/`output_dir` is refused with several files; an unreadable folder is a `ValidationError`), `run_each` (side by side, one summed ActionResult; one plain file goes straight to `runner.run_action`), `enqueue_each` (one task per file; `runner.enqueue_action` stores absolute paths, since the worker may start in another folder). The CLI command takes `target: list[Path]`, `--recursive`, `--redo` (only with an `output_name`) and `--queue` (queueable), and calls `interface/batch_cli.run_batch` first, which returns False for one plain file so the command's own code runs; that code calls the file `source`. The drift test allows those options and a list only on `each` actions. `ActionForm` and the agent go through the same module. Not batches: `files shred` (no undo) and `pdf stamp` (its text is positional).
  - Runner: `src/max_cli/core/catalog/runner.py`. `coerce_args` turns form strings or agent JSON into typed arguments, `run_action` calls the operation, and `enqueue_action` queues it as one `TaskType.ACTION` task (pass `title=` to name it). The queue executor gives an operation `should_cancel` and `progress_hook` when its signature takes them, so queued downloads report progress and stop on cancel.
  - Prompts: operations never ask. The CLI keeps its own confirmation prompts and `--force`; the catalog has no `force` param, because the dashboard and the agent ask according to `danger`. An operation that changes files records a TransactionLog and returns its id as `undo_group` (`core/operations/files.py`).
  - Tests: `tests/test_catalog_drift.py` fails when a CLI command, its catalog entry and its operation disagree on options, spellings or defaults. It allows `--force` only on actions that move, overwrite or delete. When you change a command in a ported group, change all three.
  - *Shows: one description of each action, so the CLI, the dashboard and the agent offer the same options and run the same code.*

- **AI Providers Pattern**: `src/max_cli/core/engines/ai_providers.py`. `PROVIDERS` (openai, openrouter, gemini, ollama), each with its key, model and URL settings; `AI_PROVIDER` picks the main one (empty: Ollama when the older `OLLAMA_ENABLED`, else openai) and `AI_FALLBACK_PROVIDER` the fallback. `make_client()` returns a `FallbackClient` (`chat.completions.create` only): it sends each provider its own model, moves to the fallback on any `openai.APIError` and stays there; `last_provider`, `model` and `used_fallback` say who answered. Every AI caller gets its client here (`AIEngine`, the agent). `check(provider, key, url, model)` and `list_models(provider, key, url)` take the values typed on the Settings page before they're saved; a provider is set up only with a key (Ollama: none) and a model (OpenRouter and Gemini start with none). Each provider also has an image model (`image_setting`: `AI_IMAGE_MODEL`, `OPENROUTER_IMAGE_MODEL`, `GEMINI_IMAGE_MODEL`; Ollama none); `make_client(image=True, model=None)` sends image requests to them with the same fallback, and `AIEngine.generate_image`/`edit_image` use it. `all_models` reads a provider's list once; `chat_models`/`image_models` split it. Settings page: `widgets/ai_slot.AISlot`, one for the main AI and one for the fallback; models are typed (`SuggestFromList`) or picked in `widgets/model_picker.ModelPicker`, a searchable list that also takes a typed name; each slot shows only the chosen provider's fields, keeps a `Draft` per provider, reports its own `changes()`, and ignores change events that match what it shows (Textual posts them after the code that set the control). Tests stub `_openai_client`; build openai errors with `cls.__new__` (openai 1-2 use httpx, 3 uses httpx2)
- **AI Agent Pattern** (PLANS/active/dashboard-first-ai-agent.md, step 4):
  - Core: `src/max_cli/core/agent/`. `agent.Agent` holds one conversation over an OpenAI-compatible client (`ai_engine.make_client()`, `chat_model()`); `ask(request)` loops: call the model, run the tool calls, repeat until it answers in words. `Agent.from_settings(confirm=..., on_step=...)` raises `ConfigurationError` when no AI is set up
  - Tools (`agent/tools.py`): five look without changing anything (`agent/looks.py`; never confirmed, reported as LOOKED steps): `list_folder`, `inspect` (the pages' `describe` functions), `find_files` (subfolders by kind, name, size, age; capped at 20,000 files), `probe_link` (`grab.probe`) and `recent_activity` (the activity log and the undo log). Paths stay inside the scope. `load_group(name)` and `run_action(action, arguments)` act; `run_action` takes `queue: true` for queueable actions when the Agent has `can_queue` (the AI page, and the CLI, which then starts the background worker). The agent logs each request and each action it runs, queues or fails to `common/activity_log.ActivityLog` (moved from `interface/tui/` so core can use it) The system prompt lists the groups with their action names; `load_group` returns that group's `catalog.schema.action_schema` JSON. `tests/test_agent.py` keeps the first prompt under its character budget and free of action arguments
  - Guardrails: no shell; `run_action` goes through `catalog.runner` (`coerce_args` errors go back to the model); every path argument must sit under `agent/scope.PathScope` (the starting folder, folders named in requests, the download folder; never a drive root); MOVES, OVERWRITES and DELETES call `confirm` whatever CONFIRM_DESTRUCTIVE says, except with `dry_run` true; `MAX_STEPS` model turns, `MAX_ACTIONS` tool calls and `TOKEN_LIMIT` tokens per request; `dry_run` checks without running
  - Parallel actions: `_tools` answers one turn's tool calls in order. Looks, checks and confirmations run one at a time; `_run` returns a `_Run` for each action that passed, and `_run_all` runs them in a thread pool (`PARALLEL_ACTIONS`), or in order when `_overlap` finds two naming the same path or a folder holding the other's path. `_report` holds a lock, so `on_step` and the activity log see one step at a time. Each `Step` carries the tool call's `call_id`: the AI page keys its `ToolCard`s by it, and the CLI's `_StepPrinter` names an action again above a result that arrives after another action's lines. `resolve_ffmpeg` holds a lock, so parallel actions download FFmpeg once
  - Batches: `run_action` takes `each`, a list of files; `_run_each` fills the action's first FILE param (else FOLDER) with each one, checks them all, asks `confirm` once with a `_files_text` summary, and returns a `_Batch` whose runs join the turn's parallel runs. The model gets one JSON summary (files, worked, failed, outputs). `find_files` takes `missing` (an extension): it keeps files with no same-name file of that type beside them and lists the others under `already_done`, so a conversion skips finished work. The system prompt tells the model to plan the file set first and never redo finished work
  - Gemini thought signatures: Gemini 3 puts `extra_content.google.thought_signature` on its tool calls and refuses the next request without it. `_tool_call_message` keeps `extra_content`; `ai_providers.messages_for` adds Google's stand-in (`GEMINI_SKIP_SIGNATURE`) to a tool-call turn Gemini didn't make (after a fallback) and strips `extra_content` for other providers
  - Callers: `interface/cli_ai.py` (`ai ask`, `ai chat`, and `max <text>` through `LazyTyperGroup.route`; a first word close to a group or command (`TYPO_CUTOFF`) that stands alone, comes before an option or before a command of that group is a typo, and click answers "Did you mean") and `interface/tui/widgets/ai_panel.py`. They show the `Step`s `on_step` reports (an action sends STARTED with its arguments, then RAN or FAILED with its result and seconds; the page draws a `ToolCard` per action inside an `AgentTurn`, and renders replies with Textual's `Markdown`, the CLI with Rich's); the dashboard's `confirm` runs in the worker and waits on a `ConfirmDialog` it opens through `call_from_thread`
  - Tests: a scripted client (`SimpleNamespace` responses with `tool_calls`) instead of the network: `tests/test_agent.py`, `tests/test_cli_ai.py`, `tests/interface/tui/test_ai_page.py`
- **Task Queue Pattern**:
  - Schema: `src/max_cli/core/engines/task_queue.py` (TaskItem, TaskType, executor registry)
  - Manager: `src/max_cli/core/engines/task_manager.py`. Several processes share the store (dashboard, CLI commands, the background worker). Every change goes through `_store()`: `queue.lock` (`common/file_lock.FileLock`, a byte lock the OS drops when the process dies), then the in-process lock (that order, so reads like `get_stats` never wait on another process), reload, change, save. `_store()` raises `TaskManagerError` when a file can't be read (it would save over it) or the save fails, so `add()` never reports a task it didn't store; a file that isn't a task list is moved to `<name>.corrupt-<time>`. `_reload` merges disk copies into the objects this process holds, by id; the task running here keeps its progress and takes only a cancel. Only the holder of `worker.lock` runs tasks (`_process_loop`, `process_now`, `run_until_idle`); `_claim` marks a task running under the store lock, and a new lock holder sends orphaned running tasks back to pending (`_recover_orphans`), or fails one whose worker died on more than 1 + `MAX_RETRIES` runs (each claim bumps `retry_count`). `run_until_idle` waits `WORKER_START_WAIT_SECONDS` for `worker.lock`, so a `worker_alive()` probe can't turn a starting worker away. `_watch` saves a running task's progress every `PROGRESS_SAVE_SECONDS`. Don't change `_queue` items without `_store()`: a status set only in memory is overwritten by the next reload. `refresh()` keeps its lists when a read fails; screens on a timer call `try_refresh()`, which waits at most `UI_REFRESH_TIMEOUT_SECONDS` and never raises. `_archive` removes by id.
  - Background worker: `core/engines/background_worker.start_background_worker()` starts `max queue worker` (hidden; `run_until_idle`) detached, unless `worker_alive()`. On Windows it uses `CREATE_NO_WINDOW`, never `DETACHED_PROCESS`: without a console of its own, every ffmpeg or yt-dlp it started opened a window. `max queue start`, `--queue` on video and grab commands and the CLI agent (`can_queue=True`, `jobs_hint`) call it. Tests: the autouse `no_background_worker` fixture replaces `_spawn`, because a real worker would run the real `~/.max_cli` queue; `tests/test_task_shared.py` runs two real worker processes on one store. `TaskItem.speed` and `eta` are text: pydantic doesn't validate assignments, so a number saves fine and fails on the next load
  - Interface: `src/max_cli/interface/cli_queue.py` (`max queue` command group)
  - Executors: each engine module registers its executors when imported. `task_queue.EXECUTOR_MODULES` maps every task type to that module, and `get_executor` imports it on first use. Add new task types there.
  - One store: `~/.max_cli/tasks/queue.json` and `history.json` hold every task type, including `max grab` downloads. Don't add another queue or history file. Use `get_task_manager()` to share one instance per process.
  - Migration: `task_migration.py` folds the old `grab_queue.json`, `grab_history.json` and `download_history.json` into the store once, then renames them to `*.migrated`.
  - *Shows: Heavy commands support `--queue` flag, tasks are executed via registered executors, results persisted to history.*

- **FFmpeg Auto-Resolution Pattern**:
  - Resolver: `src/max_cli/common/ffmpeg_resolver.py` (3-tier: PATH → `~/.max_cli/bin/` → auto-download)
  - Engine: `src/max_cli/core/engines/ffmpeg_base.py` (`FFmpegEngine.__init__` calls `_resolve_ffmpeg`; every command uses `self.ffmpeg_path`). `VideoEngine`, `AudioEngine` and `StreamEngine` subclass it, and `media_engine.MediaEngine` combines all three for existing callers
  - Prompt: `src/max_cli/interface/ffmpeg_prompt.py` supplies the download confirmation and progress callbacks. The resolver never prompts itself
  - Interface: `src/max_cli/interface/cli_media.py` (`_get_engine()` with `auto_resolve=True`)
  - *Shows: Zero-friction onboarding — user never sees "FFmpeg not found". Binary auto-downloaded, validated, and cached.*

- **Transaction Log Pattern** (`TransactionLog.make_dirs` records folders it creates as `OP_MKDIR`; undo removes them once empty. `list_groups` sorts by each group's timestamp, not file time, so undone groups don't jump to the top):
  - Log: `src/max_cli/common/transaction_log.py` (TransactionLog, TransactionError, JSON persistence)
  - Engine: `src/max_cli/core/engines/file_organizer.py` (optional `transaction_log` param on all mutating methods)
  - Interface: `src/max_cli/interface/cli_files.py` (`max files undo`, `max files history`)
  - *Shows: Every destructive file operation is recorded; `max files undo` reverses the last group atomically. Auto-backups protect deletes.*

- **TUI Dashboard Pattern** (design rules, theme and components: the `max-tui-design` skill; screenshots: `python scripts/tui_screenshot.py <page> <out.png> --sample`):
  - Entry: `src/max_cli/interface/tui/dashboard.py` (`max dashboard` command). A bare `max` runs it too when stdin and stdout are a terminal: `LazyTyperGroup.parse_args` in `core/cli/lazy_group.py` (roadmap D2). Scripts and pipes still get help
  - App: `src/max_cli/interface/tui/app.py` (Textual App with a sidebar of 11 sections. It starts open with names; Ctrl+B folds it to icons and `ui_prefs` keeps the choice as `sidebar_open` (older keys are ignored). `widgets/sidebar.py` holds `SECTIONS` (order = number keys 1-9, then 0; Settings sits on `,`, bound as `SETTINGS_KEY_NAME` "comma" because Textual splits binding keys on commas), `SECTION_GROUPS` (Do, Track, More) and `Badge`. The sidebar's up and down are priority bindings: when the pages overflow, the scroll area around them would take those keys. Change pages with `app.navigate(section_id)`: it marks the sidebar, keeps the Alt+Left back list and saves the last page in `ui_prefs`. Keys: numbers jump, `?` help (`dialogs.HelpScreen`), `Esc` sidebar, `ctrl+b` icons only, `q` quit, `r` refresh. Badges come from `DownloadPanel.RunningChanged` and a 2-second `_refresh_badges`)
  - Theme: `interface/tui/theme.py` registers `max-cyber`; style with its variables (`$primary` cyan, `$secondary` magenta, `$accent` violet, `$panel` page, `$surface` card, `$boost` hover, `$border`). They reach every widget's CSS and `Content` styles; don't redefine `$variables` in app CSS, which only its own CSS sees
  - Jobs window: `widgets/jobs_drawer.py`, toggled with `J`; post `JobsDrawer.Show()` after queueing work to open it
  - Activity page: `widgets/activity_panel.py`, tabs Queue (`queue_panel.QueuePanel`, `brand=False` inside it), History (`history_panel.HistoryPanel`: the activity log a page of 10 rows at a time, kind filter, Failed only, search, detail line) and Undo (`undo_panel.UndoPanel`: `TransactionLog.list_groups` with each group's folder; Undo runs `files.undo`, which reverses the newest group not undone yet). Open a tab from another page with `messages.OpenPage("activity", tab="history")`. The app refreshes only the open tab. Old saved pages "queue" and "history" open Activity
  - Queue tab: `widgets/queue_panel.py`. Tiles, then NOW RUNNING, UP NEXT and FINISHED lists of `TaskRow`s with one-line buttons that call `TaskManager` (`cancel`, `pause`, `resume`, `retry`). Rows update in place; a list is rebuilt only when its tasks or their order change. Rows have no widget id, because a task moving between lists gets a new row while the old one is still being removed
  - Charts: `widgets/charts.py` (`BarChart`, `StackChart` (bars split by kind, one colour per cell), `HBarChart`, `Spark` on a fixed 0-100 scale, `Meter`); each redraws only when `set_data` gets different data
  - Home: `widgets/home_panel.py` draws; `interface/tui/home_stats.py` counts. Every Home number comes from the activity log's finished entries (success or failed) over `WINDOW_DAYS`, so tiles, the stacked chart and BY TYPE agree; `TYPE_LOOK` gives each command group its name and colour ($error stays for failures) and `OLD_CATEGORIES` maps what older versions logged. The ask bar posts `messages.AskAI`; the app opens the AI page and calls `AIPanel.ask_from`. Launch tiles and PICK UP AGAIN chips are `Launcher` widgets, not Buttons (app CSS styles every Button); chips carry no id, since a removed widget lingers. `-narrow` below `NARROW_WIDTH` stacks the cards. `scripts/tui_screenshot.py --sample` seeds entries shaped like real ones
  - Page marks: `widgets/page_icons.py`. A page shows as a neon code: `page_bar(section_id, lit)` (a thin bar in `page_colour`, faded at `DIM` unless lit), `page_code(key)` ("02") and its name in uppercase; `page_glyph` adds a Nerd Font glyph or an emoji when `DASHBOARD_ICONS` is `nerd` or `emoji`; `auto` (the default) adds the Nerd Font glyph when `common/terminal_font.terminal_has_nerd_font()` (inside Windows Terminal, `WT_SESSION`, whose default font face is a Nerd Font). `common/terminal_font.py` backs `max config setup-font`: downloads the Nerd Fonts CascadiaMono archive, installs four styles per user (registry values under HKCU on Windows, `fc-cache` on Linux) and sets `profiles.defaults.font.face` in Windows Terminal's settings.json after a `.max-backup` copy, refusing a file with comments. The tests' `isolated_home` unsets `WT_SESSION` so `auto` never reads a developer's terminal. `page_colour` takes a command group's colour from `home_stats.TYPE_LOOK`, so a page looks the same in the sidebar, on the launchpad and in BY TYPE; use only the theme's own colour variables there (custom ones break when you switch themes). The sidebar lights the open, hovered or focused page. Launch tiles light up in their page's colour (`LAUNCH_HOVER_CSS`). Emoji, chips on symbols and pixel-art icons were tried and dropped (2026-10-04): they clashed with the theme or looked heavy
  - Design: every page copies the Home page's anatomy (a `◢◤ PAGE // WHAT IT DOES` header, `$surface` cards with uppercase `$primary` titles, `Grid` rows) and uses theme tokens only. The `max-tui-design` skill has the patterns, the smoothness rules and the CSS pitfalls
  - Widgets: `src/max_cli/interface/tui/widgets/` (Sidebar, HomePanel, DownloadPanel, ToolPage, ActivityPanel, SettingsPanel, AIPanel, ExtrasPanel)
  - Forms: `widgets/action_form.py` builds a form from a catalog `Action`: every option with its CLI default, advanced options folded away, Browse for paths, a confirmation for `MOVES`/`OVERWRITES`/`DELETES`, and a thread worker for the run. `widgets/dialogs.py` holds `ConfirmDialog` and `HelpScreen`. Every Browse button opens `widgets/path_picker.PathPicker(start, mode, file_types=group)`: PLACES (usual folders, pins, recent folders, drives), Back and Up, a filtered list read in a thread worker, and `PickMode.FILE`, `FOLDER` or `SAVE` (an `OUTPUT` param). It remembers the last folder, recent folders and pins in `ui_prefs`. Every catalog action has its group's page (the Tools page that listed them all is gone); pages reuse `ActionForm` (pass `include=` and `embedded=True` to place chosen fields inside a page's own layout, or `compact=True` for a few rows: fields two to a row, on/off options as checkboxes, help in tooltips)
  - Download page: `widgets/download_panel.py` calls `core/operations/grab.py`. It shows a preview (`grab.probe`; Check locks and shows a spinner until it answers), quality choices, an OPTIONS card, and one `DownloadRow` per download with a real Cancel (`should_cancel`). `GRAB_MAX_CONCURRENT` limits parallel downloads. History shows a page of 8 rows with a filter, never an inner scroll area. The Tools card shows download stats and installs the YouTube fix (`grab.youtube_fix_status`, `grab.install_youtube_fix`, the same steps as `max grab pot-setup`). `interface/tui/ui_prefs.py` remembers small page choices
  - Page links: a page asks the app to show another page by posting `messages.OpenPage(section_id)`, or to show a command-group page with a file picked there with `messages.OpenFile(page_id, path)`
  - Command-group pages: `widgets/tool_page.py` (one layout: FILE card with facts, ACTIONS in sections, the chosen action's `ActionForm`) set up by a `ToolPageSpec` in `interface/tui/tool_pages.py` (group, header, sections, a `describe` function run in a thread). `TOOL_PAGES` lists them; the app mounts one `ToolPage` per spec. `tests/interface/tui/test_tool_pages.py` fails when a dashboard action of the group sits in no section. Video (`video.describe` runs ffprobe via `FFmpegEngine.probe_media` and never downloads FFmpeg), Images (`images.describe` via `ImageEngine.inspect_image`: pixels after the EXIF rotation, format, colour mode, frames, date, camera, GPS; a folder gives its image count, size and formats; the spec's `file_title` names the card FILE OR FOLDER), PDF (`pdf.describe` via `PDFEngine.inspect_pdf`: pages, paper size, form fields, locked, scanned), Audio (`audio.describe`: tags, length, bitrate, cover art; a folder's track count, length, formats and untagged tracks; `ToolPageSpec.prefill` fills `set` with the file's tags in a thread, and `action_defaults` starts organize at `TUI_AUDIO_ORGANIZE_PATTERN`) and Files (`files.describe`: a folder's own files by kind, size, subfolders, the biggest; a file's kind, size and date). A spec's `kinds` (`common/file_kinds`) say which files the page is for: another page offers "Open on the PDF page" for such a file (`OpenFile`). `file_param` fills the first input FILE param, else the first FOLDER param that isn't `output`/`output_dir`; a folder param gets a picked file's folder; `no_fill` names actions whose path fields aren't for the picked path (`files.backups`). Chip grids drop to 2 or 1 columns when the longest action name wouldn't fit. Page numbers in text come from `SECTION_KEYS`, never literals. Plan: `PLANS/active/dashboard-tool-pages.md`
  - Extras page: `widgets/extras_panel.py`, the `tools` actions in three cards, each an `ActionForm`. The page listens for `ActionForm.Finished` (posted after a run with its `ActionResult`) to show the QR code and offer the pasted image on the Images page
  - Ctrl+P: `interface/tui/commands.py`, a command palette provider (`MaxDashboardApp.COMMANDS`) listing every page and every dashboard action from the catalog. `GROUP_PAGES` maps a group to its page; picking an action calls `app.open_action(id)`, which shows its form with the first field focused. A test fails when a group has no page
  - Settings page: `widgets/settings_panel.py` (replaced Config, System and Analytics). `CARDS` lists every setting with its control. `tests/interface/tui/test_settings_page.py` fails when a setting isn't on the page or no code reads it: delete such a setting from `config.py` and add it to `config.REMOVED_SETTINGS`, which the page's Maintenance card, the dashboard's start and `max config validate` point out in a settings file. Saving goes through `common/settings_file.update_settings_file`, which changes only the given keys of `~/.max_config.env` and keeps the rest; then the page sets the new values on the shared `settings` object
  - Actions: every dashboard action comes from the catalog (`core/catalog`) and runs through `core/catalog/runner.py`; the old hand-written `command_registry.py` and `command_executor.py` are gone (2026-10-02)
  - Activity: `src/max_cli/common/activity_log.py`. Several processes write it, so `_save` takes `activity_log.lock`, re-reads the file and merges only the entries this instance changed (`_changed`, by id). The dashboard's forms and the agent log their own runs; `core/catalog/activity.py` logs the rest: `run_recorded(operation, **kwargs)` in every CLI `_run` helper (it finds the operation's catalog action), `record(...)` for CLI batches, queued tasks the worker finishes (`via: queue`) and Download page rows. Logging never fails the work
  - Tests: `tests/interface/tui/` (Textual Pilot API for simulating interactions)
  - *Shows: Required dependencies (`textual`, `psutil`; the `tui` extra is empty and kept for old install commands), interactive command execution, unified activity log, file browser, AI chat, keyboard shortcuts, loading states, config-aware defaults, graceful degradation.*

## 8. Escalation & Discovery

When uncertain about implementation:

1. **Check the Plans**: Read `PLANS/active/README.md` and related active tasks.
2. **Review Plugin Docs**: Check `PLANS/docs/plugins.md` if extending functionality.
3. **Check Base Utilities**: Search `src/max_cli/common/` for existing helpers before writing new ones (e.g., `Cache`, `retry`).
4. **Propose before rewriting**: If an engine requires significant restructuring, outline the proposed Architecture changes before modifying files.

## 9. Stack-Specific Notes

### Python & CLI Specifics

- **GIL & Parallelism**: Max CLI utilizes multithreading (not asyncio) for I/O bound tasks via `ThreadPoolExecutor`. CPU-bound tasks rely on native C-extensions (like Pillow) releasing the GIL or subprocesses (like FFmpeg).
- **Subprocess Handling**: External tools (like FFmpeg via `MediaEngine`) use `subprocess.run`. Always capture `stderr` and wrap failures in a `RuntimeError` or `MaxError`.
- **Type Checking Limitations**: Many dependencies (Pillow, PyMuPDF, yt-dlp) lack strict type stubs. Use `# type: ignore` sparingly and only on specific lines where third-party types fail, rather than disabling checks globally.

## 10. Zero-Tolerance "Anti-Slop" Rules

To maintain Max CLI as a production-grade, enterprise-quality framework, all code contributions must be free of "slop" (lazy programming, messy hacks, and boilerplate).

### Strict Coding Constraints

- **No Dead Code**: Never leave commented-out code, unused variables, or unused imports in your commits. If code is no longer needed, delete it.
- **No Blanket Exceptions**: Never use `except Exception: pass`. Always catch specific exceptions (e.g., `FileNotFoundError`, `requests.exceptions.RequestException`). If a broad exception must be caught at the top level, it *must* be logged using `max_cli.common.logger.log_error`.
- **No Magic Numbers or Strings**: Extract repeated raw strings or numbers into named constants (e.g., `DEFAULT_CHUNK_SIZE = 1024`).
- **No Vague Naming**: Variables must describe their data. Use `output_file_path` instead of `out`, `page_count` instead of `count`, and `image_metadata` instead of `data`.
- **No Duplicate Utilities**: Before writing a helper function (e.g., file size formatting, hashing, retries), verify it doesn't already exist in `src/max_cli/common/`.
- **Enforce Type Checking**: Do not bypass the type checker with `# type: ignore` simply to save time. Only use it when a third-party library genuinely lacks stubs, and always add a brief comment explaining why it is necessary.

## 11. Context & Discovery Mandate (Read Before You Write)

Agents are strictly forbidden from "guessing" implementations, file structures, or function signatures. You must possess the full context before writing or modifying code.

### The "Look Before You Leap" Protocol

1. **Request Missing Context**: If you are asked to modify a file or use a module but the content of that file has not been provided in the prompt context, you **must** request to read the file first (e.g., using a `read_file` tool or asking the user to paste it).
2. **Verify Imports**: Before importing a class or function from another module within the project, verify its exact location and signature in the source code.
3. **Analyze the Blast Radius**: If you are changing a Core Engine (e.g., `ImageEngine`), search the `interface/` directory to see how existing CLI commands use that engine to avoid breaking contracts.
4. **Read the Plans**: Always check the `PLANS/` directory for active architectural decisions or deferred tasks related to your current objective to prevent redundant work.

## 12. Executive Summary (TL;DR)

Whenever you reset or start a new task, keep this core philosophy in mind:

**What is Max CLI?**
Max CLI is a "Lazy, Fast Terminal Assistant." It wraps complex, multi-step operations (like running FFmpeg to compress video, using PyMuPDF to merge PDFs, or hitting AI APIs) into simple, human-friendly terminal commands (e.g., `max video compress movie.mp4`).

**The Architectural Golden Rule:**
The project is built on a **Strict Separation of Concerns**.

- The User Interface (`src/max_cli/interface/`) handles exactly three things: parsing user inputs via Typer, calling the Core Engines, and printing pretty colors/progress bars via Rich.
- The Core (`src/max_cli/core/`) handles the actual file manipulation, math, and API calls. Core engines know nothing about the terminal, colors, or Typer. They only take Python primitives/objects and return Python primitives/objects.

By enforcing this modular monolith pattern, utilizing existing shared common tools, and strictly avoiding sloppy coding habits, Max CLI remains robust, scalable, and beautifully clean.

## 13. Testing Protocol & Mocks

Max CLI relies on external binaries (FFmpeg) and network calls (AI APIs, Downloads). Tests must run reliably in CI environments where these external dependencies might not exist.

### Testing Rules

- **No Real Network Calls**: Any test touching `NetworkEngine` or `AIEngine` **must** mock the external API using `unittest.mock.patch` or `responses`.
- **No Real Binary Execution**: When testing `MediaEngine`, mock `subprocess.run` and `shutil.which` to simulate FFmpeg success/failure without requiring the actual binary.
- **Use Provided Fixtures**: Always use the fixtures defined in `tests/conftest.py` (e.g., `temp_directory`, `dummy_image`, `dummy_pdf`, `mock_env_vars`) instead of creating ad-hoc test files.
- **Test Core vs. Interface Independently**:
  - Test Core Engines by directly instantiating the class and asserting the return values or file state.
  - Test CLI Interfaces using `typer.testing.CliRunner` to assert stdout output and exit codes.
- **Mock Lazy Imports Correctly**: Since engines no longer import heavy libraries at module level, mock at the package level (`@patch("openai.OpenAI")`), NOT at the module level (`@patch("max_cli.core.engines.ai_engine.OpenAI")`).
- **Set `_client` Directly**: When testing `AIEngine`, set `engine._client = mock_client` instead of `engine.client = mock_client`, since `client` is now a lazy property.

## 14. Safe File Operations & Idempotency

Because this CLI modifies user files (renaming, deleting, compressing), destructive operations must be handled with extreme care to prevent data loss.

### File Handling Rules

- **Idempotency**: CLI commands should be idempotent where possible. Running a command twice on the same file should not crash; it should either gracefully skip (like `files order`) or safely overwrite if the user intends it.
- **Destructive Confirmations**: Any command that permanently deletes or fundamentally alters data (e.g., `files shred`, `files duplicates --delete`) must implement a confirmation prompt using `Rich.prompt.Confirm.ask()`, bypassed only by a explicit `--force` or `-f` flag.
- **Atomic Operations**: When generating a new file (e.g., downloading or compressing), write to a temporary file first or ensure the process completes before replacing the original file. Do not leave half-written, corrupted files if the user hits `Ctrl+C`.
- **Cross-Platform Paths**: Exclusively use `pathlib.Path`. Never use string concatenation for file paths (e.g., `dir + "/" + file`).

## 15. Agent Communication & Workflow (Meta-Rules)

When responding to the user or generating code in this project, adhere strictly to these communication standards:

- **Concise Explanations**: Do not write long essays explaining standard Python concepts unless asked. Focus your explanation on *why* a specific architectural decision was made.
- **Unified Diffs / Snippets over Full Files**: When modifying an existing file, do not regurgitate the entire 500-line file. Provide only the relevant modified functions or classes with enough surrounding context to apply the patch cleanly.
- **Self-Correction Logging**: If you write code, run a test, and the test fails, do not silently ignore it. Acknowledge the failure, explain the root cause briefly, and provide the corrected implementation.
- **Completion Check**: Before saying a task is "done", verify you have:
  1. Written the logic.
  2. Registered the command (if applicable).
  3. Added Type Hints.
  4. Written/Updated Tests.
  5. Updated `PLANS/active/[task].md` (if applicable).

## 16. Security & Subprocess Safety (CRITICAL)

Because Max CLI takes user input, translates it via AI, and executes local system commands (like FFmpeg or file operations), security is paramount.

- **No `shell=True`**: Never use `subprocess.run(..., shell=True)` under any circumstances. It introduces severe shell injection vulnerabilities. Always pass a list of arguments (e.g., `["ffmpeg", "-i", input]`).
- **Input Sanitization**: If a user-provided string must be passed to a command line interface, use `shlex.split()` to safely parse it, or better yet, handle it entirely via Python's native `pathlib` and standard library.
- **AI Output Validation**: When parsing JSON responses from the `AIEngine`, never trust the structure blindly. Always use `.get()` with safe defaults or wrap the parsing in a `try/except json.JSONDecodeError` block.

## 17. Cross-Platform Compatibility (Windows vs. POSIX)

Max CLI must work seamlessly on Linux, macOS, and Windows. AI agents often default to Linux-centric assumptions, which breaks Windows builds.

- **Temporary Files**: Never hardcode paths like `/tmp/`. Always use Python’s built-in `tempfile` module or the dedicated `Path.home() / ".max_cli" / "cache"` directory.
- **Executable Resolution**: Do not assume binaries are simply named `ffmpeg`. Always use `shutil.which("ffmpeg")` to resolve the path, as it handles `.exe` extensions on Windows automatically.
- **Line Endings & Encoding**: When reading or writing text files, always explicitly specify `encoding="utf-8"`. Do not rely on the OS default encoding, which might be `cp1252` on Windows and will crash on emojis or special characters.

## 18. API Rate Limiting, State, & Caching

Max CLI interfaces with external APIs (OpenAI, Google Gemini). Hitting these APIs unnecessarily causes rate-limit errors and wastes user credits.

- **Use the Built-in Cache**: If you are adding a feature that fetches static metadata, categorizes files, or performs an expensive operation, you MUST wrap it using the `@cached` decorator from `max_cli.common.cache` or explicitly use `get_default_cache()`.
- **Background Queue Awareness**: For long-running network tasks (like `yt-dlp` downloads), never block the main thread. Queue them as tasks through `get_task_manager()` from `max_cli.core.engines.task_manager`. Downloads use `make_download_task()` from `network_engine`, and their history is read through `DownloadHistory` in `core/engines/download_history.py`.

## 19. The "Halt and Catch Fire" Rule (Anti-Looping)

AI coding agents sometimes get stuck in a loop: writing code, running a test, failing, writing the exact same code, failing again, and wasting context tokens.

- **The 2-Strike Rule**: If you attempt to fix a failing test or a type-check error twice and it still fails, **STOP**.
- Do not attempt a third guess.
- Instead, output a `[HALT]` message. Summarize exactly what is failing, state your hypotheses for why it's happening, and ask the human user how they would like to proceed.
- **Graceful Degradation**: If a new feature requires an external dependency that is failing to resolve in the environment, write the code so that it degrades gracefully (e.g., catching `ImportError` and showing a friendly Typer warning) rather than crashing the whole CLI.

## 20. CLI App Ecosystem & Routing Summary

Max CLI is structured as a tree of sub-applications (Typer `app` instances) registered in `src/max_cli/interface/`. Agents must understand this ecosystem to place new commands in the correct domain.

### The Core Apps (What they have and do)

- **`cli_images.py` (`max images`)**: Handles static visual media. (Commands: `compress`, `resize`, `convert`, `strip`).
- **`cli_media.py` (`max video`)**: Handles time-based media via FFmpeg. (Commands: `compress`, `to-audio`, `cut`, `gif`, `concat`, `stream`, etc.).
- **`cli_audio.py` (`max audio`)**: Handles audio tags via Mutagen and compresses via FFmpeg; calls `core/operations/audio.py`. (Commands: `get`, `set`, `clear`, `batch`, `organize`, `compress`, `denoise`).
- **`cli_pdf.py` (`max pdf`)**: Handles document manipulation via PyMuPDF. (Commands: `merge`, `split`, `compress`, `ocr`, `stamp`, `lock`).
- **`cli_files.py` (`max files`)**: Handles OS-level file operations. (Commands: `order`, `smart-sort`, `duplicates`, `shred`, `backup`).
- **`cli_network.py` (`max grab`)**: Handles downloading and queueing via yt-dlp. (Commands: `download`, `queue`, `history`).
- **`cli_ai.py` (`max ai`)**: The AI agent and the vision and image API. `ask` and `chat` run the agent (`core/agent`); `max <text>` routes to `ask`. (Commands: `ask`, `chat`, `analyze`, `create`, `edit`, `search`, `extract`).
- **`cli_config.py` (`max config`)**: Handles environment variables, global state, and setup wizards.
- **`cli_tools.py` (`max tools`)**: Lightweight system utilities; calls `core/operations/tools.py`. (Commands: `share`, `paste`, `copy`.)

### The Importance of Strict App Routing

You must respect these boundaries. Never put an image-resizing command inside `cli_files.py`, and never put a text-translation command inside `cli_tools.py`.

1. **The "Router" Principle**: Typer Apps are strictly **routers**. Their only job is to parse arguments, display Rich progress bars, catch `MaxError` exceptions, and pass validated data to the Core Engines. They must contain **zero business logic**.
2. **The Plugin Migration Roadmap**: Max CLI is actively migrating heavy command groups (`ai`, `video`, `grab`, `pdf`) into optional, lazy-loaded plugins (see `PLANS/active/plugin_commands_migration.md`). If you leak business logic or heavy imports (like `import ffmpeg` or `from openai import OpenAI`) into the Interface Apps instead of keeping them hidden in the Core Engines, you will break the lazy-loading architecture and crash the CLI for users who haven't installed those optional dependencies.
3. **User Experience (UX) Consistency**: The Typer Apps auto-generate the CLI's `--help` documentation. By placing commands in their correct Apps, the `--help` menu remains logical and discoverable for the end-user.

## 21. Final Agent Directives (The "Max" Philosophy)

As an AI coding on this repository, you are not just writing Python scripts; you are building a tool designed for humans who want to save time.

- **Be Lazy for the User**: If a command takes 5 arguments, provide smart defaults for 4 of them.
- **Be Fast for the User**: Use threading for batch jobs. Use caching for repeated AI calls.
- **Be Beautiful for the User**: Never let a command succeed or fail silently. Always use `Rich` panels, spinners, and color-coded text to tell the user exactly what just happened.

## 22. The Living Documentation Mandate (Continuous Updates)

Max CLI relies on accurate documentation for both human users and future AI agents. **You are strictly responsible for keeping the documentation in sync with the code.**

Never consider a task "complete" until the following documentation checks are resolved:

### 1. Agent-to-Agent Memory (`AGENTS.md`)

`AGENTS.md` is the collective memory of this project. If you make a systemic change, you MUST update this file so future agents know about it.

- **Update it when:** You introduce a new architectural pattern, add a new Core Engine, implement a new core utility in `common/`, or change a strict coding rule.
- **Do NOT update it when:** You fix a simple bug, add a standard command to an existing Engine, or refactor an isolated function.

### 2. User-Facing Documentation (`README.md` & `docs/`)

If a human user cannot find out how to use your new feature, the feature does not exist.

- **Update it when:** You add a new Typer command, add a new CLI flag/argument, change default behaviors, or add new configuration variables to `.env.example`/`config.py`.
- **Where to update:**
  1. Add the command and its examples to the main `README.md`.
  2. Update the specific markdown file in `docs/commands/` (e.g., if you add a PDF command, update `docs/commands/pdf.md`).
  3. If you create an entirely new command group (e.g., `docs/commands/zip.md`), you MUST register that new file in the `nav` section of `mkdocs.yml`.

### 3. The "Doc-Sync" Workflow

When generating your final response for a completed feature:

1. Write/modify the Python code.
2. Write/modify the Pytest tests.
3. Check if the change alters the user experience. If yes, update `README.md` and `docs/`.
4. Check if the change alters the developer architecture. If yes, update `AGENTS.md`.
5. Explicitly state in your final output: *"Documentation has been synchronized."*

**[END OF AGENTS.MD]**
