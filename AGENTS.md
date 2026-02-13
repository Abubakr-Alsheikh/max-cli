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

This document should be kept up-to-date as the project evolves and new patterns emerge.
