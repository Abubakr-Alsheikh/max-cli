# AGENTS.md

This file contains guidelines and commands for agentic coding agents working in the max-cli repository.

## Project Overview

**max-cli** is a high-performance, modular CLI framework for developers and power users. It provides intelligent automation for media processing, document management, and file organization through a local-first, AI-assisted terminal interface.

## Build & Development Commands

### Installation

```bash
# Install development dependencies
pip install -e .[dev]

# Install with all dependencies
pip install -e .
```

### Code Quality & Type Checking

```bash
# Run ruff linter (auto-formats and checks style)
ruff check .
ruff format .

# Run mypy type checker
mypy src/

# Run pytest tests
pytest tests/

# Run single test file
pytest tests/test_core_images.py

# Run specific test function
pytest tests/test_core_images.py::test_compress_image
```

### Package Management

```bash
# Build package
python -m build

# Install editable mode
pip install -e .
```

## Code Style Guidelines

### Python Standards

- **Python Version**: >=3.9
- **Line Length**: 88 characters (configured in pyproject.toml)
- **Type Hints**: Required for all function signatures and class attributes
- **Imports**: Standard library → third-party → local imports, sorted alphabetically

### Import Organization Example

```python
import os
import json
import typer
from pathlib import Path
from typing import Optional, List, Dict

from PIL import Image, ImageOps

from max_cli.core.image_processor import ImageEngine
from max_cli.common.logger import console, log_success, log_error
```

### Naming Conventions

- **Classes**: PascalCase (e.g., `ImageEngine`, `SystemEngine`)
- **Functions/Variables**: snake_case (e.g., `process_single_image`, `output_path`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `SUPPORTED_EXTENSIONS`, `DEFAULT_QUALITY`)
- **Private methods**: Prefix with underscore (e.g., `_resolve_batch`, `_run_batch`)

### Error Handling

- Use custom exceptions from `max_cli.common.exceptions`:
  - `MaxError` - Base class for expected errors
  - `ResourceNotFoundError` - When files/folders are missing
  - `ValidationError` - When input arguments are invalid

```python
try:
    # Your code here
except MaxError as e:
    console.print(f"[bold red]✖ Error:[/bold red] {e}")
    sys.exit(1)
except Exception as e:
    console.print("[bold red]💥 Critical Error (Unexpected)[/bold red]")
    console.print(f"An error occurred: {e}")
    sys.exit(1)
```

### Logging & Output

- Use the rich console with custom theme from `max_cli.common.logger`
- Success messages: `log_success("message")`
- Error messages: `log_error("message")`
- Direct console output: `console.print("[color]message[/color]")`

### File Structure

```
src/max_cli/
├── core/           # Business logic and engines
├── interface/      # Typer CLI commands
├── common/         # Shared utilities and exceptions
└── __init__.py    # Package exports

tests/                   # Test files
```

### Core Architecture Patterns

#### Engine Pattern

All core functionality follows the Engine pattern:

```python
class EngineName:
    """Business logic for specific domain."""
    
    def __init__(self):
        # Initialize resources
        pass
    
    def method_name(self, param: Type) -> ReturnType:
        """Docstring describing the method."""
        pass
```

#### CLI Interface Pattern

```python
import typer
from max_cli.core.engine import EngineName
from max_cli.common.logger import console, log_success, log_error

app = typer.Typer()
engine = EngineName()

@app.command("command-name")
def command_name(
    target: Path = typer.Argument(Path("."), help="File or folder."),
    quality: int = typer.Option(85, "-q", help="Quality (1-100)."),
):
    """Docstring describing the command."""
    try:
        # Command logic
        log_success("Operation completed successfully")
    except MaxError as e:
        log_error(str(e))
```

### Configuration

- Use `max_cli.config.Settings` for centralized configuration
- Settings are loaded from `.env` file
- Access settings via `settings.OPENAI_API_KEY`, `settings.DEFAULT_QUALITY`, etc.

### Testing Guidelines

- Use pytest for all tests
- Test files should be in `tests/` directory with `test_` prefix
- Use fixtures for setup/teardown
- Test both success and error cases

### Dependencies

- **Core**: typer, rich, pillow, pymupdf, openai, requests
- **Development**: pytest, ruff, mypy
- **Optional**: ffmpeg (required for media operations)

### Performance Considerations

- Use `rich.progress.Progress` for long-running operations
- Implement batch processing for multiple files
- Use efficient image processing with Pillow
- Add proper error handling to prevent crashes

### Security Best Practices

- Never commit API keys or secrets
- Validate all user inputs
- Handle file operations safely with Path objects
- Use try-except blocks for external API calls

## Development Workflow

1. **Setup**: Install dependencies with `pip install -e .[dev]`
2. **Code**: Follow the established patterns and style guidelines
3. **Test**: Run `pytest tests/` to ensure all tests pass
4. **Lint**: Run `ruff check .` and `ruff format .` for code quality
5. **Type Check**: Run `mypy src/` to verify type hints
6. **Commit**: Follow conventional commit messages if applicable

## Common Patterns

### Batch Processing

```python
def _resolve_batch(target: Path) -> Tuple[List[Path], Path]:
    if target.is_file():
        return [target], target.parent
    files = [f for f in target.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]
    out_dir = target.parent / f"{target.name}_optimized"
    out_dir.mkdir(exist_ok=True)
    return files, out_dir
```

### Rich Table Output

```python
table = Table(title="Summary", box=box.ROUNDED)
table.add_column("File", style="cyan")
table.add_column("Original", justify="right")
table.add_column("Final", justify="right", style="green")
table.add_column("Saved", justify="right", style="bold yellow")
for s in stats_list:
    table.add_row(s["file_name"], s["original_size"], s["final_size"], f"{s['reduction_pct']}%")
console.print(table)
```

### Progress Bars

```python
with Progress(
    SpinnerColumn(),
    TextColumn("[progress.description]{task.description}"),
    BarColumn(),
    transient=True,
) as progress:
    task = progress.add_task("Processing...", total=len(files))
    for f in files:
        # Process file
        progress.advance(task)
```

## AI Agent Instructions

Before starting any task, agents should check for AI-specific instruction files in the project root directory. Look for files with patterns like:

- `GEMINI.md`
- `CLAUDE.md`
- `OPENAI.md`
- `AGENT.md`
- `AI_INSTRUCTIONS.md`

If any of these files exist, read them first and follow their instructions. These files contain specific guidelines for AI agents working on this codebase. If no instruction files are found, proceed with the standard development workflow.

---

## Continuous Improvement System

### The Improvement Plan

This project uses `PLAN.md` as the single source of truth for all improvement tasks. The plan is divided into phases:

- **Phase 1**: Foundation & Code Quality (Testing, Type Safety, Linting)
- **Phase 2**: Performance & Architecture (Parallel Processing, Caching)
- **Phase 3**: Feature Enhancements (Media, PDF, AI, File Management)
- **Phase 4**: Developer Experience (Documentation, CI/CD, Plugin System)
- **Phase 5**: Advanced Features (Cloud, Voice, System Integration)

### Task Tracking System

Tasks in PLAN.md use checkboxes `[ ]` for pending and `[x]` for completed. When an agent works on a task:

1. **Read the Plan**: Always read `PLAN.md` first to understand current priorities
2. **Check Task Status**: Verify the task is still `[ ]` (not started)
3. **Mark In Progress**: Update the checkbox to `[~]` (in progress) while working
4. **Complete the Task**: Update to `[x]` when finished
5. **Update README if Needed**: Only update README.md if the task adds user-facing features
6. **Create Implementation Files**: For complex tasks, create `.md` files with implementation details

### Task Status Legend

| Symbol | Meaning | Description |
|--------|---------|-------------|
| `[ ]` | Pending | Not started, available for work |
| `[~]` | In Progress | Currently being worked on |
| `[x]` | Completed | Finished and verified |
| `[S]` | Skipped | Will not implement |
| `[D]` | Deferred | Moved to future phase |

### Working on Improvement Tasks

When asked to work on project improvements:

```
1. Read PLAN.md to understand current priorities
2. Select the highest priority task (P0 first, then P1, etc.)
3. Check if the task is already marked as in progress or completed
4. Implement the solution:
   - For simple tasks: Implement directly in the codebase
   - For complex tasks: Create an implementation guide file
5. Test the changes (run pytest, ruff, mypy)
6. Update PLAN.md to mark task as complete [x]
7. Only update README.md if user-facing changes require it
8. If implementation was complex, create an implementation guide
```

### Implementation Guides for Complex Tasks

When a task is too complex to implement in a single session:

1. Create an implementation guide in `tasks/implementation/` directory
2. Name it descriptively: `tasks/implementation/<task-name>.md`
3. Include:
   - Overview of what needs to be built
   - Step-by-step implementation plan
   - Code snippets for key components
   - Testing strategy
   - Potential pitfalls

Example template:
```markdown
# Implementation Guide: <Feature Name>

## Overview
Brief description of the feature.

## Implementation Steps

### Step 1: <Name>
Description and code snippet.

### Step 2: <Name>
Description and code snippet.

## Testing Strategy
How to test this feature.

## Potential Issues
Known issues and how to avoid them.

## Related Tasks
Links to related tasks in PLAN.md.
```

### Updating Documentation

**When to UPDATE README.md:**
- New CLI commands are added
- New features that users need to know about
- Breaking changes to existing commands
- Installation requirement changes

**When NOT to UPDATE README.md:**
- Internal refactoring
- Test coverage improvements
- Type hint additions
- CI/CD improvements
- Code style changes

### Running Quality Checks

Before marking a task as complete, always run:

```bash
# 1. Run tests
pytest tests/

# 2. Run linter
ruff check .
ruff format .

# 3. Run type checker
mypy src/

# 4. Verify no regressions
pytest tests/ -v
```

### The Improvement Loop

This creates a continuous improvement cycle:

1. **Agent reads PLAN.md** → understands priorities
2. **Agent works on task** → implements or creates guide
3. **Agent runs checks** → ensures quality
4. **Agent updates PLAN.md** → marks complete
5. **Agent updates README if needed** → keeps users informed
6. **Next agent reads PLAN.md** → sees updated status
7. **Repeat** → project continuously improves

This document should be kept up-to-date as the project evolves and new patterns emerge.
