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
│   ├── engines/               # Sub-domain logic (image, pdf, ai, network)
│   └── cli/                   # Command & Plugin registry
├── interface/                 # ADAPTERS / CLI LAYER
│   ├── cli_*.py               # Typer command definitions (No business logic)
│   └── config/                # CLI config wizards
├── common/                    # SHARED / INFRASTRUCTURE
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
- **Classes/Engines**: `PascalCase` (e.g., `ImageEngine`, `QueueManager`)
- **Functions/Methods**: `snake_case` (Private methods prefixed with `_`)
- **Constants**: `UPPER_SNAKE_CASE`

### Code Organization Principles

- **Separation of Concerns**: `interface/` files parse CLI arguments and print output. `core/engines/` files perform the actual computation and return data.
- **Dependency Direction**: Interface → Core → Common. Core engines must *never* import from `interface/`.
- **Import Organization**: Standard library → third-party → local imports (alphabetically sorted).
- **Lazy Loading Mandate**: All heavy third-party imports (PIL, fitz, yt_dlp, openai, mutagen, requests) MUST be placed inside the methods that use them, never at module level. Interface files MUST NOT instantiate engines at module level — use `_get_engine()` helper functions instead.

### Lazy Loading Pattern (MANDATORY)

Max CLI enforces lazy loading to keep `max --help` startup under 200ms. Heavy imports are deferred until first use.

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
- [ ] Type checking passes without ignoring third-party lack of stubs unnecessarily (`mypy src/`)
- [ ] Code is formatted and linted cleanly (`ruff check . && ruff format .`)
- [ ] `PLANS/active/` markdown files are updated if fulfilling a planned task.

### Git & Task Standards

- If a task takes too long (e.g., fighting type checkers on 3rd-party libs), mark it `[D]` (Deferred) in the `PLANS/` system and move on.
- Update `README.md` and `docs/` ONLY if user-facing behavior, CLI commands, or installation steps change.

## 6. Boundaries & Permissions

### ✅ Always Do

- Use existing utilities from `max_cli.common` (`@retry`, `process_batch_parallel`, `format_size`).
- Use custom exceptions from `max_cli.common.exceptions` (`MaxError`, `ResourceNotFoundError`).
- Use `console`, `log_success`, and `log_error` from `max_cli.common.logger` for user output in the `interface/` layer.
- Use the event system (`EventEmitter` from `max_cli.common.events`, `EventSubscriber` from `max_cli.interface.event_subscriber`) for progress tracking — never pass Rich UI objects into core/common functions.
- Use the task queue system (`DaemonManager` from `max_cli.core.engines.daemon_manager`, `TaskItem`/`TaskType` from `max_cli.core.engines.task_queue`) for long-running operations — add `--queue` flag to heavy commands.
- Add type hints to all function signatures.

### ⚠️ Ask First Before

- Adding new heavy third-party dependencies (e.g., ML libraries, large binaries).
- Making breaking changes to existing CLI command signatures.
- Modifying `pyproject.toml` dependencies or entry points.

### 🚫 Never Do

- Never expose raw stack traces to the user (wrap top-level calls in try/except).
- Never use `print()` or `typer.echo()` inside `core/engines/` (Engines return values; Interfaces print them).
- Never commit secrets, API keys, or `.env` files.
- Never use `os.path` (strictly use `pathlib.Path`).
- Never import heavy third-party libraries at module level (PIL, fitz, yt_dlp, openai, mutagen, requests) — always use lazy imports inside methods.
- Never instantiate Engine classes at module level in interface files — always use `_get_engine()` helper functions.
- Never import engine instances from other interface files (e.g., `from cli_ai import engine`) — use local `_get_engine()` calls instead.

## 7. Reference Implementations

- **Good Example - Core/Interface Separation**:
  - Interface: `src/max_cli/interface/cli_images.py`
  - Core: `src/max_cli/core/engines/image_processor.py`
  - *Shows: How CLI parses args and passes them to the Engine, which returns stats for the CLI to format into a Rich table.*
  
- **Utility Pattern**: `src/max_cli/common/concurrent.py`
  - *Shows: Standardized ThreadPoolExecutor implementation used across the app.*
  
- **Plugin Pattern**: `examples/plugins/hello_world.py`
  - *Shows: Correct plugin metadata definition, lifecycle hooks, and Typer command registration.*

- **Lazy Loading Pattern**:
  - Engine: `src/max_cli/core/engines/image_processor.py` (PIL imported inside methods)
  - Interface: `src/max_cli/interface/cli_images.py` (uses `_get_engine()` helper)
  - *Shows: Heavy imports deferred until first use, keeping startup under 200ms.*

- **Event-Driven Progress Pattern**:
  - Events: `src/max_cli/common/events.py` (EventEmitter, event models)
  - Subscriber: `src/max_cli/interface/event_subscriber.py` (Rich UI updates)
  - Batch: `src/max_cli/common/concurrent.py` (emits events, zero Rich imports)
  - Interface: `src/max_cli/interface/cli_images.py` (uses EventSubscriber)
  - *Shows: Core emits pure events, interface translates to Rich progress bars. Core stays 100% UI-agnostic.*

- **Task Queue Pattern**:
  - Schema: `src/max_cli/core/engines/task_queue.py` (TaskItem, TaskType, executor registry)
  - Manager: `src/max_cli/core/engines/daemon_manager.py` (queue operations, daemon processing)
  - Interface: `src/max_cli/interface/cli_queue.py` (`max queue` command group)
  - Executors: `src/max_cli/core/engines/media_engine.py` (registers video task executors)
  - *Shows: Heavy commands support `--queue` flag, tasks are executed via registered executors, results persisted to history.*

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
- **Background Queue Awareness**: For long-running network tasks (like `yt-dlp` downloads), never block the main thread. Ensure integration with `max_cli.core.engines.queue_manager.QueueManager` to allow background processing.

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
- **`cli_audio.py` (`max audio`)**: Handles audio metadata via Mutagen. (Commands: `get`, `set`, `clear`, `batch`).
- **`cli_pdf.py` (`max pdf`)**: Handles document manipulation via PyMuPDF. (Commands: `merge`, `split`, `compress`, `ocr`, `stamp`, `lock`).
- **`cli_files.py` (`max files`)**: Handles OS-level file operations. (Commands: `order`, `smart-sort`, `duplicates`, `shred`, `backup`).
- **`cli_network.py` (`max grab`)**: Handles downloading and queueing via yt-dlp. (Commands: `download`, `queue`, `history`).
- **`cli_ai.py` (`max ai`)**: Handles LLM and Vision API interactions. (Commands: `ask`, `chat`, `analyze`, `create`, `search`).
- **`cli_config.py` (`max config`)**: Handles environment variables, global state, and setup wizards.
- **`cli_tools.py` (`max tools`)**: Lightweight system utilities (clipboard management, QR codes).

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
