# Plan: User-Defined Workflows & Aliases

> Status: Draft
> Priority: P1
> Related: User Experience & Laziness (Feature 2D)
> Depends on: None (standalone feature)

## Overview

Max CLI wraps complex multi-step operations into single commands. But users often have **personal multi-command routines** they run repeatedly (e.g., "convert video to podcast audio" = `to-audio` → `normalize` → `set metadata`). Currently, users must either remember and type each command individually, or write their own shell scripts.

This plan introduces two complementary systems:

1. **Workflows** — YAML-defined multi-command pipelines stored in `~/.max_cli/workflows.yaml`, executed via `max workflows run <name> [args...]`.
2. **Aliases** — Simple one-liner shortcuts defined in `~/.max_config.env`, registered as hidden Typer commands at startup.

Together, these make Max CLI truly "lazy" — users define their own compound operations once and invoke them with a single command.

## Problem Analysis

### Current Limitations

1. **No composition**: Each `max` command is atomic. Users cannot chain `max video to-audio` + `max audio normalize` into one call.
2. **No personalization**: Users who always run the same sequence of commands must re-type them every time.
3. **Shell scripts are fragile**: Users writing bash wrappers lose Max CLI's error handling, Rich UI, cross-platform path handling, and lazy loading.
4. **No discoverability**: Even if a user writes a shell script, `max --help` won't show it. New team members won't know about shared workflows.

### Why This Matters

- A video creator might always: download → compress → extract audio → tag metadata. That's 4 commands.
- A developer might always: `max pdf merge` → `max pdf compress` → `max files smart-sort`. That's 3 commands.
- Reducing these to `max workflows run podcast-prep video.mp4` or `max vcompress video.mp4` saves time and reduces errors.

## Goals

- [ ] Add `pyyaml` as a dependency in `pyproject.toml`
- [ ] Create `~/.max_cli/workflows.yaml` schema and default template
- [ ] Implement `WorkflowEngine` in `src/max_cli/common/workflow_engine.py`
- [ ] Implement `max workflows` command group in `src/max_cli/interface/cli_workflows.py`
- [ ] Support variable substitution (`$1`, `$2`, `$input`, `$output`)
- [ ] Validate referenced subcommands before execution
- [ ] Support simple aliases via `MAX_ALIAS_*` in `~/.max_config.env`
- [ ] Register aliases as hidden Typer commands at startup
- [ ] Add comprehensive tests for parsing, substitution, execution, and error handling
- [ ] Update `README.md` and `docs/` with usage examples

## Implementation Details

### Phase 1: Add `pyyaml` Dependency

**File**: `pyproject.toml`

```toml
dependencies = [
    "typer>=0.12.0",
    "rich>=13.0.0",
    "shellingham>=1.5.0",
    "pillow>=10.0.0",
    "pymupdf>=1.22.0",
    "pydantic-settings>=2.0.0",
    "openai>=1.0.0",
    "requests>=2.31.0",
    "yt-dlp>=2023.0.0",
    "segno>=1.5.0",
    "pyperclip>=1.8.0",
    "mutagen>=1.47.0",
    "pyyaml>=6.0",          # NEW: Workflow YAML parsing
]
```

**Rationale**: `pyyaml` is the standard YAML library for Python. It's lightweight, well-maintained, and already used by thousands of Python projects. We need it to parse the workflow definition file.

---

### Phase 2: Define Workflow YAML Schema

**File**: `~/.max_cli/workflows.yaml` (created on first use)

```yaml
# Max CLI Workflow Definitions
# Run 'max workflows create <name>' to add new workflows interactively.
# Run 'max workflows list' to see available workflows.

workflows:
  podcast-prep:
    description: "Convert video to podcast-ready audio"
    commands:
      - max video to-audio $1 --format mp3
      - max audio normalize $1.mp3
      - max audio set $1.mp3 --genre "Podcast"

  quick-compress:
    description: "Fast video compression"
    commands:
      - max video compress $1 --quality 50

  pdf-pack:
    description: "Merge, compress, and organize PDFs"
    commands:
      - max pdf merge $@ --output merged.pdf
      - max pdf compress merged.pdf --output packed.pdf
      - max files smart-sort . --by date
```

**Schema rules**:
- Top-level key: `workflows` (dict of workflow name → definition)
- Each workflow has:
  - `description` (string, required) — shown in `max workflows list`
  - `commands` (list of strings, required) — shell commands to execute sequentially
- Variable substitution:
  - `$1`, `$2`, `$3`... — positional arguments
  - `$@` — all arguments joined with spaces
  - `$input` — alias for `$1` (first argument, more readable)
  - `$output` — derived output path (first arg's stem + `_output` + original extension, or user-specified via `--output` flag in the workflow definition)
- Commands are executed via `subprocess.run` (NOT `shell=True`) — each command string is split with `shlex.split()` after variable substitution.

**Default template** (created if file doesn't exist):

```yaml
# Max CLI Workflow Definitions
# See 'max workflows --help' for usage.

workflows:
  example:
    description: "Example workflow — replace with your own"
    commands:
      - max video compress $1 --quality 75
```

---

### Phase 3: Create `WorkflowEngine` (Core)

**File**: `src/max_cli/common/workflow_engine.py`

```python
# src/max_cli/common/workflow_engine.py

import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from max_cli.common.exceptions import MaxError, ConfigurationError, ProcessingError
from max_cli.config import settings


class WorkflowError(MaxError):
    """Raised when a workflow operation fails."""
    pass


class WorkflowNotFoundError(WorkflowError):
    """Raised when a requested workflow does not exist."""
    pass


class WorkflowValidationError(WorkflowError):
    """Raised when a workflow definition is invalid."""
    pass


class WorkflowEngine:
    """
    Loads, validates, and executes user-defined workflows from YAML.

    Workflows are stored in ~/.max_cli/workflows.yaml and define
    sequences of max CLI commands with variable substitution.
    """

    WORKFLOW_FILE = Path.home() / ".max_cli" / "workflows.yaml"

    def __init__(self, workflow_file: Optional[Path] = None) -> None:
        self._workflow_file = workflow_file or self.WORKFLOW_FILE
        self._workflows: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _ensure_dir(self) -> None:
        """Ensure the ~/.max_cli directory exists."""
        self._workflow_file.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        """Load workflows from the YAML file."""
        if not self._workflow_file.exists():
            self._workflows = {}
            return

        try:
            content = self._workflow_file.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            raise WorkflowValidationError(
                f"Failed to parse workflow file: {e}"
            )

        if data is None:
            self._workflows = {}
            return

        if not isinstance(data, dict) or "workflows" not in data:
            raise WorkflowValidationError(
                "Workflow file must contain a top-level 'workflows' key."
            )

        workflows = data["workflows"]
        if not isinstance(workflows, dict):
            raise WorkflowValidationError(
                "'workflows' must be a mapping of name → definition."
            )

        # Validate each workflow
        for name, definition in workflows.items():
            self._validate_workflow(name, definition)

        self._workflows = workflows

    def _validate_workflow(self, name: str, definition: Any) -> None:
        """Validate a single workflow definition."""
        if not isinstance(definition, dict):
            raise WorkflowValidationError(
                f"Workflow '{name}' must be a mapping."
            )
        if "description" not in definition:
            raise WorkflowValidationError(
                f"Workflow '{name}' is missing a 'description'."
            )
        if "commands" not in definition:
            raise WorkflowValidationError(
                f"Workflow '{name}' is missing a 'commands' list."
            )
        if not isinstance(definition["commands"], list):
            raise WorkflowValidationError(
                f"Workflow '{name}': 'commands' must be a list."
            )
        if not definition["commands"]:
            raise WorkflowValidationError(
                f"Workflow '{name}': 'commands' must not be empty."
            )
        for i, cmd in enumerate(definition["commands"]):
            if not isinstance(cmd, str):
                raise WorkflowValidationError(
                    f"Workflow '{name}': command at index {i} must be a string."
                )

    def list_workflows(self) -> Dict[str, str]:
        """
        Return a dict of workflow name → description.
        """
        return {
            name: wf.get("description", "")
            for name, wf in self._workflows.items()
        }

    def get_workflow(self, name: str) -> Dict[str, Any]:
        """Get a workflow definition by name."""
        if name not in self._workflows:
            raise WorkflowNotFoundError(f"Workflow '{name}' not found.")
        return self._workflows[name]

    def workflow_exists(self, name: str) -> bool:
        """Check if a workflow exists."""
        return name in self._workflows

    def add_workflow(self, name: str, description: str, commands: List[str]) -> None:
        """Add or update a workflow and persist to disk."""
        if not name or not name.strip():
            raise WorkflowValidationError("Workflow name cannot be empty.")
        if not commands:
            raise WorkflowValidationError("Workflow must have at least one command.")

        self._workflows[name] = {
            "description": description,
            "commands": commands,
        }
        self._save()

    def delete_workflow(self, name: str) -> bool:
        """Delete a workflow. Returns True if it existed."""
        if name not in self._workflows:
            return False
        del self._workflows[name]
        self._save()
        return True

    def _save(self) -> None:
        """Persist workflows to the YAML file."""
        self._ensure_dir()
        data = {"workflows": self._workflows}
        # Write atomically: write to temp, then rename
        temp_file = self._workflow_file.with_suffix(".yaml.tmp")
        temp_file.write_text(
            yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        temp_file.replace(self._workflow_file)

    @staticmethod
    def _substitute_variables(command: str, args: List[str]) -> str:
        """
        Substitute variables in a command string.

        Supported variables:
        - $1, $2, $3... — positional arguments
        - $@ — all arguments joined with spaces
        - $input — alias for $1
        - $output — derived output path (stem_output + original extension)
        """
        if not args:
            # Remove variable references if no args provided
            result = command
            result = result.replace("$@", "")
            result = result.replace("$input", "")
            result = result.replace("$output", "")
            for i in range(1, 20):  # support up to $19
                result = result.replace(f"${i}", "")
            # Clean up double spaces
            while "  " in result:
                result = result.replace("  ", " ")
            return result.strip()

        result = command

        # $@ — all arguments
        result = result.replace("$@", shlex.join(args))

        # $input — first argument
        result = result.replace("$input", args[0])

        # $output — derived output path
        output_path = WorkflowEngine._derive_output(args[0])
        result = result.replace("$output", output_path)

        # $1, $2, $3... — positional
        for i, arg in enumerate(args, start=1):
            result = result.replace(f"${i}", arg)

        return result

    @staticmethod
    def _derive_output(input_arg: str) -> str:
        """
        Derive an output path from the input argument.

        Rules:
        - If input is a file path: <stem>_output<ext>
        - If input is a directory: <dir>/output
        """
        path = Path(input_arg)
        if path.suffix:
            # Has extension — it's a file
            return str(path.parent / f"{path.stem}_output{path.suffix}")
        else:
            # No extension — treat as directory or bare name
            return str(path / "output")

    def validate_commands(self, name: str) -> List[Tuple[str, bool, str]]:
        """
        Validate that referenced max subcommands exist.

        Returns a list of (command, exists, reason) tuples.
        This is a best-effort check — it verifies the first two
        tokens of each command match a known max subcommand.
        """
        workflow = self.get_workflow(name)
        results = []

        # Known top-level commands from the registry
        known_commands = {
            "images", "video", "audio", "pdf", "files",
            "grab", "ai", "config", "tools", "workflows", "queue",
        }

        for cmd in workflow["commands"]:
            # Substitute with dummy args for validation
            test_cmd = self._substitute_variables(cmd, ["dummy_input"])
            parts = shlex.split(test_cmd)

            if len(parts) < 3:
                results.append((cmd, False, "Command too short"))
                continue

            # Check if it starts with 'max'
            if parts[0] != "max":
                results.append((cmd, False, "Command must start with 'max'"))
                continue

            # Check if the subcommand is known
            subcommand = parts[1]
            if subcommand in known_commands:
                results.append((cmd, True, ""))
            else:
                results.append(
                    (cmd, False, f"Unknown subcommand: '{subcommand}'")
                )

        return results

    def run_workflow(
        self,
        name: str,
        args: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Execute a workflow sequentially.

        Args:
            name: Workflow name.
            args: Positional arguments for variable substitution.
            dry_run: If True, return commands without executing.

        Returns:
            List of result dicts with keys: command, exit_code, stdout, stderr, success

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            WorkflowError: If a command fails (unless continue_on_error).
        """
        workflow = self.get_workflow(name)
        args = args or []
        results = []

        for cmd_template in workflow["commands"]:
            cmd = self._substitute_variables(cmd_template, args)

            if dry_run:
                results.append({
                    "command": cmd,
                    "exit_code": None,
                    "stdout": "",
                    "stderr": "",
                    "success": True,
                    "dry_run": True,
                })
                continue

            try:
                parts = shlex.split(cmd)
            except ValueError as e:
                results.append({
                    "command": cmd,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": f"Failed to parse command: {e}",
                    "success": False,
                })
                raise WorkflowError(
                    f"Command parsing failed in workflow '{name}': {e}"
                )

            if not parts:
                continue

            # Execute via subprocess (NEVER shell=True)
            try:
                proc = subprocess.run(
                    parts,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=settings.DOWNLOAD_TIMEOUT,
                )

                results.append({
                    "command": cmd,
                    "exit_code": proc.returncode,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "success": proc.returncode == 0,
                })

                if proc.returncode != 0:
                    raise WorkflowError(
                        f"Command failed (exit code {proc.returncode}) "
                        f"in workflow '{name}':\n  {cmd}\n"
                        f"  stderr: {proc.stderr.strip()}"
                    )

            except subprocess.TimeoutExpired:
                results.append({
                    "command": cmd,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": "Command timed out",
                    "success": False,
                })
                raise WorkflowError(
                    f"Command timed out in workflow '{name}': {cmd}"
                )
            except FileNotFoundError:
                results.append({
                    "command": cmd,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": f"Executable not found: {parts[0]}",
                    "success": False,
                })
                raise WorkflowError(
                    f"Executable not found in workflow '{name}': {parts[0]}"
                )

        return results
```

**Design decisions**:
- **Atomic writes**: Uses temp file + `replace()` to prevent corruption if interrupted.
- **`shlex.split()`**: Safely parses command strings into argument lists — handles quoted strings, spaces in paths.
- **`subprocess.run` with `capture_output=True`**: Never uses `shell=True` (security mandate from AGENTS.md).
- **Timeout**: Uses `settings.DOWNLOAD_TIMEOUT` (default 300s) to prevent hung workflows.
- **Fail-fast**: Stops on first command failure with a clear error message showing which command failed.
- **Dry-run mode**: CLI can preview what would run without executing.
- **Variable substitution is static**: Simple string replacement, not shell evaluation. This is safe and predictable.

---

### Phase 4: Create `max workflows` Command Group (Interface)

**File**: `src/max_cli/interface/cli_workflows.py`

```python
# src/max_cli/interface/cli_workflows.py

from typing import List, Optional
from pathlib import Path

import typer
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from max_cli.common.workflow_engine import (
    WorkflowEngine,
    WorkflowError,
    WorkflowNotFoundError,
    WorkflowValidationError,
)
from max_cli.common.logger import console, log_success, log_error

app = typer.Typer(help="Manage and run user-defined workflows.")


def _get_engine() -> WorkflowEngine:
    from max_cli.common.workflow_engine import WorkflowEngine
    return WorkflowEngine()


@app.command("list")
@app.command("ls", hidden=True)
def workflows_list():
    """List all available workflows."""
    engine = _get_engine()
    workflows = engine.list_workflows()

    if not workflows:
        console.print("[dim]No workflows defined.[/dim]")
        console.print(
            "[dim]Run 'max workflows create <name>' to add one.[/dim]"
        )
        return

    table = Table(
        title="Available Workflows",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    table.add_column("Steps", justify="right")

    for name, description in sorted(workflows.items()):
        wf = engine.get_workflow(name)
        step_count = len(wf.get("commands", []))
        table.add_row(name, description, str(step_count))

    console.print(table)
    console.print(f"\n[dim]Total: {len(workflows)} workflow(s)[/dim]")


@app.command("run")
@app.command("r", hidden=True)
def workflows_run(
    name: str = typer.Argument(..., help="Workflow name to execute."),
    args: Optional[List[str]] = typer.Argument(
        None, help="Arguments for the workflow."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Show commands without executing."
    ),
    skip_validation: bool = typer.Option(
        False, "--skip-validation", help="Skip subcommand existence check."
    ),
):
    """Execute a workflow with the given arguments."""
    engine = _get_engine()
    args = args or []

    try:
        # Validate subcommands
        if not skip_validation:
            validation = engine.validate_commands(name)
            failed = [(cmd, reason) for cmd, ok, reason in validation if not ok]
            if failed:
                console.print("[yellow]Warning: Some commands may not work:[/yellow]")
                for cmd, reason in failed:
                    console.print(f"  [red]✗[/red] {cmd} — {reason}")

                from rich.prompt import Confirm
                if not Confirm.ask("Continue anyway?", default=False):
                    console.print("[dim]Cancelled.[/dim]")
                    raise typer.Exit(0)

        if dry_run:
            console.print(f"[bold]Dry run — workflow '{name}'[/bold]\n")
            results = engine.run_workflow(name, args, dry_run=True)
            for i, result in enumerate(results, start=1):
                console.print(f"  [cyan]{i}.[/cyan] {result['command']}")
            console.print(f"\n[dim]{len(results)} command(s) would be executed.[/dim]")
            return

        # Execute
        workflow = engine.get_workflow(name)
        console.print(f"[bold]Running workflow:[/bold] [cyan]{name}[/cyan]")
        console.print(f"[dim]{workflow['description']}[/dim]\n")

        results = engine.run_workflow(name, args)

        for i, result in enumerate(results, start=1):
            status = "[green]✓[/green]" if result["success"] else "[red]✗[/red]"
            console.print(f"  {status} [{i}/{len(results)}] {result['command']}")

        console.print()
        log_success(f"Workflow '{name}' completed successfully.")

    except WorkflowNotFoundError as e:
        log_error(str(e))
        console.print("[dim]Run 'max workflows list' to see available workflows.[/dim]")
        raise typer.Exit(1)
    except WorkflowError as e:
        log_error(str(e))
        raise typer.Exit(1)


@app.command("create")
def workflows_create(
    name: str = typer.Argument(..., help="Name for the new workflow."),
):
    """Create a new workflow interactively."""
    engine = _get_engine()

    if engine.workflow_exists(name):
        from rich.prompt import Confirm
        console.print(f"[yellow]Workflow '{name}' already exists.[/yellow]")
        if not Confirm.ask("Overwrite?", default=False):
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(0)

    description = typer.prompt("Description")

    commands = []
    console.print("\nEnter commands one per line (empty line to finish):")
    console.print("[dim]Use $1, $2, $input, $output for arguments.[/dim]")

    while True:
        cmd = typer.prompt(f"  Command {len(commands) + 1}", default="", show_default=False)
        if not cmd.strip():
            if not commands:
                console.print("[yellow]At least one command is required.[/yellow]")
                continue
            break
        commands.append(cmd.strip())

    try:
        engine.add_workflow(name, description, commands)
        log_success(f"Workflow '{name}' created with {len(commands)} command(s).")
        console.print(f"[dim]Edit it at: {WorkflowEngine.WORKFLOW_FILE}[/dim]")
    except WorkflowValidationError as e:
        log_error(str(e))
        raise typer.Exit(1)


@app.command("edit")
def workflows_edit(
    name: str = typer.Argument(..., help="Workflow name to edit."),
):
    """Open a workflow's YAML definition in your editor."""
    engine = _get_engine()

    if not engine.workflow_exists(name):
        log_error(f"Workflow '{name}' not found.")
        raise typer.Exit(1)

    import subprocess
    import os

    editor = os.environ.get("EDITOR", "notepad" if os.name == "nt" else "vi")
    try:
        subprocess.run(
            [editor, str(WorkflowEngine.WORKFLOW_FILE)],
            check=True,
        )
        # Reload after edit
        engine._load()
        log_success(f"Workflow file saved. Run 'max workflows list' to verify.")
    except subprocess.CalledProcessError:
        log_error(f"Editor '{editor}' failed.")
        raise typer.Exit(1)
    except FileNotFoundError:
        log_error(f"Editor '{editor}' not found. Set the EDITOR environment variable.")
        raise typer.Exit(1)


@app.command("delete")
@app.command("rm", hidden=True)
def workflows_delete(
    name: str = typer.Argument(..., help="Workflow name to delete."),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation."),
):
    """Delete a workflow."""
    engine = _get_engine()

    if not engine.workflow_exists(name):
        log_error(f"Workflow '{name}' not found.")
        raise typer.Exit(1)

    if not force:
        from rich.prompt import Confirm
        if not Confirm.ask(f"Delete workflow '{name}'?", default=False):
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(0)

    engine.delete_workflow(name)
    log_success(f"Workflow '{name}' deleted.")
```

**Design decisions**:
- **`_get_engine()` helper**: Follows lazy loading pattern — engine is created only when a command runs.
- **Hidden aliases**: `ls`, `r`, `rm` are hidden shortcuts for power users.
- **Interactive create**: Uses `typer.prompt` for step-by-step workflow creation.
- **Edit opens the whole file**: Simpler than parsing/editing a single workflow in YAML. Users can use their preferred editor.
- **Confirmation prompts**: Destructive operations (delete, overwrite) require confirmation unless `--force` is passed.

---

### Phase 5: Register Workflows Command

**File**: `src/max_cli/core/cli/commands/workflows.py` (new)

```python
# src/max_cli/core/cli/commands/workflows.py

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typer import Typer

from max_cli.interface import cli_workflows


def register(app: "Typer") -> None:
    """Register workflow commands."""
    app.add_typer(
        cli_workflows.app,
        name="workflows",
        help="User-defined command pipelines.",
    )
```

**File**: `src/max_cli/core/cli/commands/__init__.py` (update)

```python
from max_cli.core.cli.commands import (
    ai,
    audio,
    config,
    files,
    media,
    network,
    plugins as plugin_commands,
    queue,
    tools,
    workflows,        # NEW
)

__all__ = [
    "ai",
    "audio",
    "config",
    "files",
    "media",
    "network",
    "plugin_commands",
    "queue",
    "tools",
    "workflows",       # NEW
]
```

**File**: `src/max_cli/core/cli/registry.py` (update)

```python
def register(app: "Typer") -> None:
    """Register all CLI commands."""
    commands.media.register(app)
    commands.files.register(app)
    commands.network.register(app)
    commands.ai.register(app)
    commands.tools.register(app)
    commands.config.register(app)
    commands.plugin_commands.register(app)
    commands.audio.register(app)
    commands.queue.register(app)
    commands.workflows.register(app)   # NEW
```

---

### Phase 6: Simple Aliases via `~/.max_config.env`

**Concept**: Users can define simple one-liner aliases in their existing config file. These are parsed at startup and registered as hidden Typer commands.

**File**: `~/.max_config.env` (user adds lines like):

```env
MAX_ALIAS_VCOMPRESS=video compress --quality 50
MAX_ALIAS_PODCAST=workflows run podcast-prep
MAX_ALIAS_QPDF=pdf compress --output compressed.pdf
```

**How it works**: Aliases are parsed from environment variables (via pydantic-settings `extra = "ignore"` currently captures them). We need to explicitly read `MAX_ALIAS_*` variables and register them as commands.

**File**: `src/max_cli/config.py` (update)

```python
# Add to Settings class:

class Settings(BaseSettings):
    # ... existing fields ...

    # --- Aliases ---
    # Parsed from MAX_ALIAS_* environment variables
    # These are populated dynamically in _load_aliases()
    _aliases: Dict[str, str] = {}

    def _load_aliases(self) -> Dict[str, str]:
        """Load MAX_ALIAS_* variables from environment."""
        import os
        aliases = {}
        prefix = "MAX_ALIAS_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                alias_name = key[len(prefix):].lower().replace("_", "-")
                aliases[alias_name] = value
        return aliases

    @property
    def aliases(self) -> Dict[str, str]:
        if not self._aliases:
            self._aliases = self._load_aliases()
        return self._aliases

    class Config:
        env_file = [str(Path.home() / ".max_config.env"), ".env"]
        env_file_encoding = "utf-8"
        extra = "ignore"
```

**File**: `src/max_cli/common/alias_engine.py` (new)

```python
# src/max_cli/common/alias_engine.py

import os
import shlex
import subprocess
import sys
from typing import Dict, List, Optional, Tuple

from max_cli.common.exceptions import MaxError
from max_cli.config import settings


class AliasError(MaxError):
    """Raised when an alias operation fails."""
    pass


class AliasEngine:
    """
    Manages simple command aliases defined via MAX_ALIAS_* env vars.

    Aliases are one-liners that expand to max CLI subcommands.
    They are registered as hidden Typer commands at startup.
    """

    def __init__(self) -> None:
        self._aliases: Dict[str, str] = settings.aliases

    def list_aliases(self) -> Dict[str, str]:
        """Return all registered aliases."""
        return dict(self._aliases)

    def get_alias(self, name: str) -> Optional[str]:
        """Get the expansion for an alias."""
        return self._aliases.get(name)

    def alias_exists(self, name: str) -> bool:
        return name in self._aliases

    def run_alias(
        self,
        name: str,
        extra_args: Optional[List[str]] = None,
    ) -> int:
        """
        Execute an alias command.

        Args:
            name: Alias name.
            extra_args: Additional arguments appended to the command.

        Returns:
            Exit code of the subprocess.

        Raises:
            AliasError: If alias not found or execution fails.
        """
        expansion = self.get_alias(name)
        if expansion is None:
            raise AliasError(f"Alias '{name}' not found.")

        # Build the full command
        parts = ["max"] + shlex.split(expansion)
        if extra_args:
            parts.extend(extra_args)

        # Execute as a subprocess of the same Python executable
        # This ensures the 'max' command uses the same installation
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "max_cli"] + parts[1:],
                timeout=settings.DOWNLOAD_TIMEOUT,
            )
            return proc.returncode
        except subprocess.TimeoutExpired:
            raise AliasError(f"Alias '{name}' timed out.")
        except FileNotFoundError:
            raise AliasError("Max CLI executable not found.")
```

**File**: `src/max_cli/interface/cli_aliases.py` (new)

```python
# src/max_cli/interface/cli_aliases.py

from typing import List, Optional

import typer

from max_cli.common.alias_engine import AliasEngine, AliasError
from max_cli.common.logger import console, log_success, log_error

app = typer.Typer(hidden=True)  # Hidden — accessed via alias commands directly


def _get_engine() -> AliasEngine:
    return AliasEngine()


def register_alias_commands(app: typer.Typer, alias_engine: AliasEngine) -> None:
    """
    Register each alias as a hidden Typer command on the main app.

    This is called from main.py during startup.
    """
    for name, expansion in alias_engine.list_aliases().items():
        # Create a dynamic command for each alias
        def _make_alias_handler(alias_name: str, alias_expansion: str):
            def handler(
                extra_args: Optional[List[str]] = typer.Argument(
                    None, help="Additional arguments."
                ),
            ):
                engine = _get_engine()
                try:
                    exit_code = engine.run_alias(alias_name, extra_args)
                    raise typer.Exit(code=exit_code)
                except AliasError as e:
                    log_error(str(e))
                    raise typer.Exit(1)

            # Set command metadata
            handler.__name__ = f"alias_{alias_name}"
            handler.__doc__ = f"Alias: {alias_expansion}"
            return handler

        cmd = _make_alias_handler(name, expansion)
        app.command(name, hidden=True)(cmd)
```

**File**: `src/max_cli/main.py` (update)

```python
import sys

import typer

from max_cli.common.exceptions import MaxError
from max_cli.core.cli.registry import register, init_plugins
from max_cli.common.logger import console
from max_cli.common.alias_engine import AliasEngine
from max_cli.interface.cli_aliases import register_alias_commands

app = typer.Typer(
    name="max",
    help="MAX: The High-Performance CLI Utility.",
    add_completion=True,
    no_args_is_help=True,
)


def main():
    """Main entry point."""
    register(app)

    # Register user-defined aliases as hidden commands
    alias_engine = AliasEngine()
    if alias_engine.list_aliases():
        register_alias_commands(app, alias_engine)

    try:
        init_plugins(app)
        app()
    except MaxError as e:
        console.print(f"[bold red]X Error:[/bold red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print("[bold red]!! Critical Error (Unexpected)[/bold red]")
        console.print(f"An error occurred: {e}")
        console.print(
            "[dim]If this persists, please report this to the developer.[/dim]"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
```

**Design decisions**:
- **Aliases are hidden commands**: They don't appear in `max --help` to avoid clutter, but they work exactly like normal commands.
- **`subprocess.run` with `sys.executable -m max_cli`**: Ensures the alias runs the same Max CLI installation, not a different one on PATH.
- **Extra args appended**: `max vcompress file.mp4 --crf 28` → expansion is `video compress --quality 50`, final command is `max video compress --quality 50 file.mp4 --crf 28`.
- **No YAML needed**: Aliases use the existing `.env` config system — no new file format to learn.
- **Naming convention**: `MAX_ALIAS_NAME_IN_ENV` becomes `max name-in-env`. Underscores convert to hyphens.

---

### Phase 7: Command Execution Flow

When a user runs `max workflows run podcast-prep video.mp4`:

```
1. main.py → register(app) → workflows.register(app)
2. Typer parses: name="podcast-prep", args=["video.mp4"]
3. cli_workflows.py:workflows_run() called
4. _get_engine() → WorkflowEngine() → loads ~/.max_cli/workflows.yaml
5. engine.validate_commands("podcast-prep") → checks subcommands exist
6. engine.run_workflow("podcast-prep", ["video.mp4"]):
   a. Substitute $1 → "video.mp4" in each command
   b. shlex.split() → argument list
   c. subprocess.run() → execute
   d. Check exit code → fail fast on error
7. Rich UI shows progress: ✓ [1/3] max video to-audio video.mp4 --format mp3
                             ✓ [2/3] max audio normalize video.mp4.mp3
                             ✓ [3/3] max audio set video.mp4.mp3 --genre "Podcast"
8. log_success("Workflow 'podcast-prep' completed successfully.")
```

## Testing Strategy

### Unit Tests

**File**: `tests/test_workflow_engine.py`

```python
import pytest
from unittest.mock import patch, MagicMock
from max_cli.common.workflow_engine import (
    WorkflowEngine,
    WorkflowError,
    WorkflowNotFoundError,
    WorkflowValidationError,
)


class TestWorkflowEngine:
    """Tests for workflow parsing and execution."""

    def test_load_empty_file(self, tmp_path):
        """Test loading when workflow file doesn't exist."""
        engine = WorkflowEngine(workflow_file=tmp_path / "nonexistent.yaml")
        assert engine.list_workflows() == {}

    def test_load_valid_workflows(self, tmp_path):
        """Test loading a valid workflow file."""
        wf_file = tmp_path / "workflows.yaml"
        wf_file.write_text(
            """
workflows:
  test-wf:
    description: "Test workflow"
    commands:
      - max video compress $1
""",
            encoding="utf-8",
        )
        engine = WorkflowEngine(workflow_file=wf_file)
        workflows = engine.list_workflows()
        assert "test-wf" in workflows
        assert workflows["test-wf"] == "Test workflow"

    def test_load_invalid_yaml(self, tmp_path):
        """Test loading malformed YAML."""
        wf_file = tmp_path / "workflows.yaml"
        wf_file.write_text("invalid: yaml: {", encoding="utf-8")
        with pytest.raises(WorkflowValidationError, match="Failed to parse"):
            WorkflowEngine(workflow_file=wf_file)

    def test_load_missing_workflows_key(self, tmp_path):
        """Test YAML without 'workflows' key."""
        wf_file = tmp_path / "workflows.yaml"
        wf_file.write_text("other_key: value", encoding="utf-8")
        with pytest.raises(WorkflowValidationError, match="'workflows' key"):
            WorkflowEngine(workflow_file=wf_file)

    def test_load_workflow_missing_description(self, tmp_path):
        """Test workflow without description."""
        wf_file = tmp_path / "workflows.yaml"
        wf_file.write_text(
            """
workflows:
  bad-wf:
    commands:
      - max video compress $1
""",
            encoding="utf-8",
        )
        with pytest.raises(WorkflowValidationError, match="missing a 'description'"):
            WorkflowEngine(workflow_file=wf_file)

    def test_load_workflow_missing_commands(self, tmp_path):
        """Test workflow without commands."""
        wf_file = tmp_path / "workflows.yaml"
        wf_file.write_text(
            """
workflows:
  bad-wf:
    description: "No commands"
""",
            encoding="utf-8",
        )
        with pytest.raises(WorkflowValidationError, match="missing a 'commands'"):
            WorkflowEngine(workflow_file=wf_file)

    def test_add_workflow(self, tmp_path):
        """Test adding a new workflow."""
        wf_file = tmp_path / "workflows.yaml"
        engine = WorkflowEngine(workflow_file=wf_file)
        engine.add_workflow("my-wf", "My workflow", ["max video compress $1"])
        assert engine.workflow_exists("my-wf")

        # Verify persistence
        engine2 = WorkflowEngine(workflow_file=wf_file)
        assert engine2.workflow_exists("my-wf")

    def test_delete_workflow(self, tmp_path):
        """Test deleting a workflow."""
        wf_file = tmp_path / "workflows.yaml"
        engine = WorkflowEngine(workflow_file=wf_file)
        engine.add_workflow("del-wf", "To delete", ["max video compress $1"])
        assert engine.delete_workflow("del-wf")
        assert not engine.workflow_exists("del-wf")

    def test_delete_nonexistent_workflow(self, tmp_path):
        """Test deleting a workflow that doesn't exist."""
        wf_file = tmp_path / "workflows.yaml"
        engine = WorkflowEngine(workflow_file=wf_file)
        assert not engine.delete_workflow("nonexistent")

    def test_get_nonexistent_workflow(self, tmp_path):
        """Test getting a workflow that doesn't exist."""
        wf_file = tmp_path / "workflows.yaml"
        engine = WorkflowEngine(workflow_file=wf_file)
        with pytest.raises(WorkflowNotFoundError):
            engine.get_workflow("nonexistent")


class TestVariableSubstitution:
    """Tests for variable substitution in workflow commands."""

    def test_positional_args(self):
        """Test $1, $2 substitution."""
        cmd = "max video compress $1 --quality $2"
        result = WorkflowEngine._substitute_variables(cmd, ["input.mp4", "50"])
        assert result == "max video compress input.mp4 --quality 50"

    def test_input_variable(self):
        """Test $input substitution."""
        cmd = "max audio normalize $input"
        result = WorkflowEngine._substitute_variables(cmd, ["song.mp3"])
        assert result == "max audio normalize song.mp3"

    def test_output_variable(self):
        """Test $output derivation."""
        cmd = "max video compress $1 --output $output"
        result = WorkflowEngine._substitute_variables(cmd, ["movie.mp4"])
        assert "movie_output.mp4" in result

    def test_all_args_variable(self):
        """Test $@ substitution."""
        cmd = "max pdf merge $@"
        result = WorkflowEngine._substitute_variables(cmd, ["a.pdf", "b.pdf"])
        assert "a.pdf" in result
        assert "b.pdf" in result

    def test_no_args_cleanup(self):
        """Test variable cleanup when no args provided."""
        cmd = "max video compress $1"
        result = WorkflowEngine._substitute_variables(cmd, [])
        assert "$1" not in result

    def test_derive_output_file(self):
        """Test output path derivation from file."""
        output = WorkflowEngine._derive_output("video.mp4")
        assert output == "video_output.mp4"

    def test_derive_output_directory(self):
        """Test output path derivation from directory."""
        output = WorkflowEngine._derive_output("my_folder")
        assert output == "my_folder/output"


class TestWorkflowExecution:
    """Tests for workflow command execution."""

    @patch("subprocess.run")
    def test_run_workflow_success(self, mock_run, tmp_path):
        """Test successful workflow execution."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        wf_file = tmp_path / "workflows.yaml"
        wf_file.write_text(
            """
workflows:
  test:
    description: "Test"
    commands:
      - max video compress $1
""",
            encoding="utf-8",
        )
        engine = WorkflowEngine(workflow_file=wf_file)
        results = engine.run_workflow("test", ["input.mp4"])

        assert len(results) == 1
        assert results[0]["success"] is True
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_run_workflow_failure(self, mock_run, tmp_path):
        """Test workflow stops on first failure."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=1, stdout="", stderr="error"),
        ]

        wf_file = tmp_path / "workflows.yaml"
        wf_file.write_text(
            """
workflows:
  test:
    description: "Test"
    commands:
      - max video compress $1
      - max audio normalize $1
""",
            encoding="utf-8",
        )
        engine = WorkflowEngine(workflow_file=wf_file)

        with pytest.raises(WorkflowError, match="Command failed"):
            engine.run_workflow("test", ["input.mp4"])

    def test_run_workflow_dry_run(self, tmp_path):
        """Test dry-run mode."""
        wf_file = tmp_path / "workflows.yaml"
        wf_file.write_text(
            """
workflows:
  test:
    description: "Test"
    commands:
      - max video compress $1
""",
            encoding="utf-8",
        )
        engine = WorkflowEngine(workflow_file=wf_file)
        results = engine.run_workflow("test", ["input.mp4"], dry_run=True)

        assert len(results) == 1
        assert results[0]["dry_run"] is True
        assert "input.mp4" in results[0]["command"]

    def test_validate_commands_valid(self, tmp_path):
        """Test command validation for valid commands."""
        wf_file = tmp_path / "workflows.yaml"
        wf_file.write_text(
            """
workflows:
  test:
    description: "Test"
    commands:
      - max video compress $1
      - max audio normalize $1
""",
            encoding="utf-8",
        )
        engine = WorkflowEngine(workflow_file=wf_file)
        results = engine.validate_commands("test")
        assert all(ok for _, ok, _ in results)

    def test_validate_commands_invalid(self, tmp_path):
        """Test command validation for invalid commands."""
        wf_file = tmp_path / "workflows.yaml"
        wf_file.write_text(
            """
workflows:
  test:
    description: "Test"
    commands:
      - max nonexistent command $1
""",
            encoding="utf-8",
        )
        engine = WorkflowEngine(workflow_file=wf_file)
        results = engine.validate_commands("test")
        assert not results[0][1]  # Should be invalid
```

### Unit Tests for Alias Engine

**File**: `tests/test_alias_engine.py`

```python
import pytest
from unittest.mock import patch, MagicMock
from max_cli.common.alias_engine import AliasEngine, AliasError


class TestAliasEngine:
    """Tests for alias parsing and execution."""

    def test_no_aliases(self, monkeypatch):
        """Test when no MAX_ALIAS_* variables exist."""
        monkeypatch.delenv("MAX_ALIAS_TEST", raising=False)
        engine = AliasEngine()
        assert engine.list_aliases() == {}

    def test_single_alias(self, monkeypatch):
        """Test parsing a single alias."""
        monkeypatch.setenv("MAX_ALIAS_VCOMPRESS", "video compress --quality 50")
        engine = AliasEngine()
        aliases = engine.list_aliases()
        assert "vcompress" in aliases
        assert aliases["vcompress"] == "video compress --quality 50"

    def test_multiple_aliases(self, monkeypatch):
        """Test parsing multiple aliases."""
        monkeypatch.setenv("MAX_ALIAS_VCOMPRESS", "video compress --quality 50")
        monkeypatch.setenv("MAX_ALIAS_PODCAST", "workflows run podcast-prep")
        engine = AliasEngine()
        aliases = engine.list_aliases()
        assert len(aliases) == 2
        assert "vcompress" in aliases
        assert "podcast" in aliases

    def test_alias_name_conversion(self, monkeypatch):
        """Test env var name to alias name conversion."""
        monkeypatch.setenv("MAX_ALIAS_MY_LONG_ALIAS", "video compress")
        engine = AliasEngine()
        assert "my-long-alias" in engine.list_aliases()

    @patch("subprocess.run")
    def test_run_alias(self, mock_run, monkeypatch):
        """Test executing an alias."""
        monkeypatch.setenv("MAX_ALIAS_TEST", "video compress")
        mock_run.return_value = MagicMock(returncode=0)

        engine = AliasEngine()
        exit_code = engine.run_alias("test", ["input.mp4"])
        assert exit_code == 0

    def test_run_nonexistent_alias(self, monkeypatch):
        """Test running an alias that doesn't exist."""
        monkeypatch.delenv("MAX_ALIAS_TEST", raising=False)
        engine = AliasEngine()
        with pytest.raises(AliasError, match="not found"):
            engine.run_alias("nonexistent")
```

### CLI Interface Tests

**File**: `tests/test_cli_workflows.py`

```python
import pytest
from typer.testing import CliRunner
from max_cli.interface import cli_workflows


class TestWorkflowsCLI:
    """Tests for the workflows CLI commands."""

    def test_list_empty(self, tmp_path, monkeypatch):
        """Test listing when no workflows exist."""
        monkeypatch.setenv("HOME", str(tmp_path))
        runner = CliRunner()
        result = runner.invoke(cli_workflows.app, ["list"])
        assert result.exit_code == 0
        assert "No workflows defined" in result.stdout

    def test_list_with_workflows(self, tmp_path, monkeypatch):
        """Test listing workflows."""
        wf_dir = tmp_path / ".max_cli"
        wf_dir.mkdir()
        wf_file = wf_dir / "workflows.yaml"
        wf_file.write_text(
            """
workflows:
  test-wf:
    description: "A test workflow"
    commands:
      - max video compress $1
""",
            encoding="utf-8",
        )
        monkeypatch.setenv("HOME", str(tmp_path))
        runner = CliRunner()
        result = runner.invoke(cli_workflows.app, ["list"])
        assert result.exit_code == 0
        assert "test-wf" in result.stdout
        assert "A test workflow" in result.stdout

    def test_run_nonexistent(self, tmp_path, monkeypatch):
        """Test running a workflow that doesn't exist."""
        monkeypatch.setenv("HOME", str(tmp_path))
        runner = CliRunner()
        result = runner.invoke(cli_workflows.app, ["run", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.stdout

    def test_dry_run(self, tmp_path, monkeypatch):
        """Test dry-run mode."""
        wf_dir = tmp_path / ".max_cli"
        wf_dir.mkdir()
        wf_file = wf_dir / "workflows.yaml"
        wf_file.write_text(
            """
workflows:
  test:
    description: "Test"
    commands:
      - max video compress $1
""",
            encoding="utf-8",
        )
        monkeypatch.setenv("HOME", str(tmp_path))
        runner = CliRunner()
        result = runner.invoke(cli_workflows.app, ["run", "test", "input.mp4", "--dry-run"])
        assert result.exit_code == 0
        assert "Dry run" in result.stdout
        assert "input.mp4" in result.stdout
```

### Test Fixtures (update `conftest.py`)

```python
@pytest.fixture
def workflow_file(tmp_path):
    """Creates a temporary workflow YAML file."""
    wf_file = tmp_path / "workflows.yaml"
    wf_file.write_text(
        """
workflows:
  test-workflow:
    description: "Test workflow"
    commands:
      - max video compress $1
      - max audio normalize $1
""",
        encoding="utf-8",
    )
    return wf_file


@pytest.fixture
def mock_subprocess(monkeypatch):
    """Mocks subprocess.run to always succeed."""
    from unittest.mock import MagicMock
    mock = MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))
    monkeypatch.setattr("subprocess.run", mock)
    return mock
```

---

## Migration Path

1. **Step 1**: Add `pyyaml>=6.0` to `pyproject.toml` dependencies.
2. **Step 2**: Create `src/max_cli/common/workflow_engine.py` with `WorkflowEngine` class.
3. **Step 3**: Create `src/max_cli/common/alias_engine.py` with `AliasEngine` class.
4. **Step 4**: Create `src/max_cli/interface/cli_workflows.py` with `max workflows` command group.
5. **Step 5**: Create `src/max_cli/interface/cli_aliases.py` with alias registration logic.
6. **Step 6**: Create `src/max_cli/core/cli/commands/workflows.py` registration module.
7. **Step 7**: Update `src/max_cli/core/cli/commands/__init__.py` to include `workflows`.
8. **Step 8**: Update `src/max_cli/core/cli/registry.py` to register workflows.
9. **Step 9**: Update `src/max_cli/config.py` to add `_load_aliases()` method.
10. **Step 10**: Update `src/max_cli/main.py` to register alias commands at startup.
11. **Step 11**: Write tests in `tests/test_workflow_engine.py`, `tests/test_alias_engine.py`, `tests/test_cli_workflows.py`.
12. **Step 12**: Update `tests/conftest.py` with workflow fixtures.
13. **Step 13**: Run `ruff check . && ruff format . && mypy src/ && pytest tests/`.
14. **Step 14**: Update `README.md` with workflow and alias usage examples.
15. **Step 15**: Create `docs/commands/workflows.md` with full documentation.
16. **Step 16**: Register new doc in `mkdocs.yml` nav.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| `pyyaml` adds startup overhead | Minor — delays `max --help` | YAML is only loaded when `max workflows` is invoked, not at startup. `WorkflowEngine` is lazy-loaded via `_get_engine()`. |
| Workflow YAML file corruption | Data loss — user loses all workflows | Atomic writes (temp file + `replace()`). File is only written on add/delete, not on read. |
| Subcommand validation is incomplete | False positives/negatives | Validation is best-effort (checks first two tokens against known commands). `--skip-validation` flag bypasses it. |
| Aliases conflict with existing commands | Command collision | Aliases are registered as hidden commands. If a name collision occurs, Typer's last-registered wins. Users should avoid naming aliases after existing commands. |
| `subprocess.run` inherits environment | Security — env vars leak | This is intentional — workflows need access to the same env (API keys, paths). No `shell=True` prevents injection. |
| Windows path handling in `shlex.split()` | Commands with spaces in paths break | `shlex.split()` handles quoted paths correctly. Users must quote paths in workflow definitions: `max video compress "$1"`. |
| Workflow commands reference non-existent `max` subcommands | Confusing errors at runtime | Pre-execution validation catches this. The `validate_commands()` method checks against known subcommands before running. |
| Circular workflow references | Infinite loop | Workflows execute `max` as a subprocess, not as a Python import. A workflow calling itself would just be a new process — not infinite, but wasteful. Add a warning in docs. |
| `MAX_ALIAS_*` env vars leak into pydantic-settings | Settings pollution | `extra = "ignore"` in pydantic-settings Config already ignores unknown env vars. Aliases are read separately via `os.environ`. |

---

## Success Criteria

- [ ] `pyyaml` is listed in `pyproject.toml` dependencies
- [ ] `max workflows list` shows available workflows in a Rich table
- [ ] `max workflows run podcast-prep video.mp4` executes all commands sequentially
- [ ] Variable substitution works: `$1`, `$2`, `$input`, `$output`, `$@`
- [ ] Workflow stops on first command failure with clear error message
- [ ] `max workflows create <name>` interactive wizard works
- [ ] `max workflows edit <name>` opens YAML in editor
- [ ] `max workflows delete <name>` removes workflow with confirmation
- [ ] `MAX_ALIAS_VCOMPRESS=video compress --quality 50` in `.env` creates `max vcompress` command
- [ ] Aliases appear as hidden commands (not in `max --help`)
- [ ] All tests pass (`pytest tests/`)
- [ ] Type checking passes (`mypy src/`)
- [ ] Linting passes (`ruff check .`)
- [ ] `README.md` updated with workflow/alias examples
- [ ] `docs/commands/workflows.md` created and registered in `mkdocs.yml`
- [ ] No heavy imports at module level (lazy loading enforced)
- [ ] No `shell=True` in any subprocess call
- [ ] Atomic writes prevent workflow file corruption
