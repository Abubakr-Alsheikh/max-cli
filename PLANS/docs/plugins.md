# Plugin System Guide

The max-cli plugin system allows you to extend the CLI with custom commands and functionality. This guide covers how to create, install, and manage plugins.

## Table of Contents

1. [Overview](#overview)
2. [Plugin Types](#plugin-types)
3. [Creating a Plugin](#creating-a-plugin)
4. [Plugin Metadata](#plugin-metadata)
5. [Lifecycle Hooks](#lifecycle-hooks)
6. [Installing Plugins](#installing-plugins)
7. [Managing Plugins](#managing-plugins)
8. [Best Practices](#best-practices)
9. [Examples](#examples)

---

## Overview

max-cli supports two types of plugins:

- **CLIPlugin**: Adds CLI commands to the application
- **EnginePlugin**: Adds business logic/engine functionality

Plugins are automatically discovered from:
- `~/.max_cli/plugins/` (user plugins)
- `./plugins/` (project plugins)

---

## Plugin Types

### CLIPlugin

Use `CLIPlugin` when you want to add new commands to the CLI:

```python
from max_cli.plugins.base import CLIPlugin
import typer

class MyPlugin(CLIPlugin):
    @property
    def name(self) -> str:
        return "my-plugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    def register(self, app: typer.Typer) -> None:
        @app.command("my-command")
        def my_command():
            """My custom command."""
            typer.echo("Hello from my plugin!")
```

### EnginePlugin

Use `EnginePlugin` for business logic that doesn't directly add CLI commands:

```python
from max_cli.plugins.base import EnginePlugin

class MyEnginePlugin(EnginePlugin):
    @property
    def name(self) -> str:
        return "my-engine"

    @property
    def version(self) -> str:
        return "1.0.0"

    def register(self, app) -> None:
        # Register engine services or extend functionality
        pass
```

---

## Creating a Plugin

### Step 1: Create the Plugin File

Create a Python file in your plugin directory:

```
~/.max_cli/plugins/my_awesome_plugin.py
```

### Step 2: Define Your Plugin Class

```python
import typer
from pathlib import Path

from max_cli.plugins.base import CLIPlugin


class AwesomePlugin(CLIPlugin):
    """A sample plugin demonstrating best practices."""

    def __init__(self):
        super().__init__(
            name="awesome",
            version="1.0.0",
            description="An awesome plugin for demonstration",
            author="Your Name",
            author_email="you@example.com",
            url="https://github.com/you/awesome-plugin",
            license="MIT",
            tags=["awesome", "demo", "example"],
            min_cli_version="0.1.0",
            dependencies=[],
        )

    @property
    def priority(self) -> int:
        """Lower = registered first. Default is 100."""
        return 100

    def validate(self) -> tuple[bool, Optional[str]]:
        """Validate plugin requirements before loading."""
        # Check for required dependencies, configs, etc.
        return True, None

    def on_load(self, context) -> None:
        """Called when plugin is loaded."""
        pass

    def on_unload(self) -> None:
        """Called when plugin is unloaded."""
        pass

    def register(self, app: typer.Typer) -> None:
        """Register commands with the CLI app."""

        @app.command("awesome")
        @app.command("aw")  # Alias
        def awesome_command(
            name: str = typer.Option("World", "--name", "-n", help="Name to greet"),
            verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
        ) -> None:
            """Say something awesome!"""
            msg = f"Awesome, {name}!"
            if verbose:
                msg += " Welcome to the awesome plugin!"
            typer.echo(msg)

        @app.command("awesome-config")
        def awesome_config(
            action: str = typer.Argument(..., help="Action: get, set, list"),
        ) -> None:
            """Manage awesome plugin configuration."""
            if action == "list":
                typer.echo("Available config options:")
            else:
                typer.echo(f"Action: {action}")


# IMPORTANT: Instantiate your plugin class at module level
# The plugin manager will discover and load this class
plugin = AwesomePlugin()
```

---

## Plugin Metadata

All plugins support the following metadata:

| Property | Type | Description |
|----------|------|-------------|
| `name` | str | Unique plugin identifier (kebab-case recommended) |
| `version` | str | Semantic version (e.g., "1.0.0") |
| `description` | str | Short description of what the plugin does |
| `author` | str | Plugin author name |
| `author_email` | str | Author contact email |
| `url` | str | Plugin homepage/repository URL |
| `license` | str | License name (e.g., "MIT", "GPL-3.0") |
| `tags` | list[str] | Searchable tags |
| `min_cli_version` | str | Minimum max-cli version required |
| `dependencies` | list[str] | Other plugins this depends on |

---

## Lifecycle Hooks

Plugins can implement lifecycle methods:

### `validate() -> tuple[bool, Optional[str]]`

Called before loading. Return `(True, None)` if valid, or `(False, "error message")` if validation fails.

```python
def validate(self) -> tuple[bool, Optional[str]]:
    # Check for required environment variables
    import os
    if not os.getenv("MY_API_KEY"):
        return False, "MY_API_KEY environment variable is required"
    return True, None
```

### `on_load(context: PluginContext) -> None`

Called when plugin is loaded. Use to initialize resources:

```python
def on_load(self, context: PluginContext) -> None:
    # context.app - the Typer app
    # context.plugin_dir - path to plugin directory
    # context.config - plugin configuration
    self.engine = MyEngine()
```

### `on_unload() -> None`

Called when plugin is unloaded. Use to clean up resources:

```python
def on_unload(self) -> None:
    if hasattr(self, 'engine'):
        self.engine.cleanup()
```

### `unregister(app: typer.Typer) -> None`

Called when plugin is unregistered. Use to remove commands or clean up:

```python
def unregister(self, app: typer.Typer) -> None:
    # Custom cleanup logic
    pass
```

---

## Installing Plugins

### Method 1: Local Directory

Create a `plugins` folder in your project root:

```
your-project/
├── plugins/
│   ├── my_plugin.py
│   └── another_plugin.py
└── max-cli/
```

### Method 2: User Plugins

Create a `.max_cli/plugins` folder in your home directory:

```bash
# Linux/macOS
mkdir -p ~/.max_cli/plugins

# Windows
mkdir %USERPROFILE%\.max_cli\plugins
```

Then copy your plugin files there.

### Method 3: Development Mode

For development, use the project-level `plugins/` directory:

```
max-cli/
├── plugins/           # Auto-discovered
└── src/max_cli/
```

---

## Managing Plugins

### List All Plugins

```bash
max plugins list
max plugins list --all    # Include disabled plugins
```

### Get Plugin Information

```bash
max plugins info <plugin-name>
```

### Enable/Disable Plugins

```bash
max plugins enable <plugin-name>
max plugins disable <plugin-name>
```

Configuration is saved to `~/.max_cli/plugins.json`.

---

## Best Practices

### 1. Use Descriptive Names

Choose clear, descriptive plugin names:

```python
@property
def name(self) -> str:
    return "image-watermark"  # Good: descriptive
    # return "iw"              # Bad: too short
```

### 2. Add Command Aliases

Provide short aliases for frequently used commands:

```python
@app.command("compress")
@app.command("c")  # Alias
def compress_images(...):
    ...
```

### 3. Handle Errors Gracefully

Catch exceptions and provide helpful error messages:

```python
def register(self, app: typer.Typer) -> None:
    @app.command("mycommand")
    def my_command():
        try:
            # Your logic
            pass
        except FileNotFoundError as e:
            typer.echo(f"File not found: {e}", err=True)
            raise typer.Exit(1)
```

### 4. Validate Dependencies

Check for required dependencies in `validate()`:

```python
def validate(self) -> tuple[bool, Optional[str]]:
    try:
        import required_module
    except ImportError:
        return False, "required_module is required. Install with: pip install required_module"
    return True, None
```

### 5. Follow CLI Conventions

- Use kebab-case for command names: `my-command`
- Use PascalCase for option names: `--MyOption`
- Keep help text concise and actionable
- Provide sensible defaults

### 6. Document Your Plugin

Add docstrings and help text:

```python
@app.command("watermark")
def add_watermark(
    image: Path = typer.Argument(..., help="Image file to watermark"),
    text: str = typer.Option("©2024", "--text", "-t", help="Watermark text"),
    position: str = typer.Option("bottom-right", "--position", "-p", help="Position"),
) -> None:
    """Add a watermark to an image.
    
    Examples:
        max images watermark photo.jpg --text "My Site"
        max images watermark photo.jpg --position center
    """
```

---

## Examples

### Example 1: Simple Hello World

See `examples/plugins/hello_world.py`

### Example 2: Plugin with Configuration

```python
import typer
import json
from pathlib import Path

from max_cli.plugins.base import CLIPlugin


class ConfigPlugin(CLIPlugin):
    """Plugin with persistent configuration."""

    def __init__(self):
        super().__init__(
            name="config-demo",
            version="1.0.0",
            description="Demonstrates plugin configuration",
        )
        self.config_file = None

    def on_load(self, context) -> None:
        # Load or create config
        if context.plugin_dir:
            self.config_file = context.plugin_dir / "config.json"
            if not self.config_file.exists():
                self.config_file.write_text("{}")

    def register(self, app: typer.Typer) -> None:
        @app.command("config-demo")
        def config_demo(
            key: str = typer.Option(..., "--key", "-k", help="Config key"),
            value: str = typer.Option(None, "--value", "-v", help="Config value"),
        ) -> None:
            """Demo plugin configuration."""
            config = json.loads(self.config_file.read_text())
            
            if value is None:
                typer.echo(f"{key}: {config.get(key, 'not set')}")
            else:
                config[key] = value
                self.config_file.write_text(json.dumps(config, indent=2))
                typer.echo(f"Set {key} = {value}")


plugin = ConfigPlugin()
```

### Example 3: Migrating Existing Commands to a Plugin

If you have commands in `cli_tools.py` you want to move to a plugin:

1. **Create the plugin file** (`~/.max_cli/plugins/max_tools.py`):

```python
import typer
from pathlib import Path

from max_cli.plugins.base import CLIPlugin


class ToolsPlugin(CLIPlugin):
    """System utilities extracted to a plugin."""

    def __init__(self):
        super().__init__(
            name="tools",
            version="1.0.0",
            description="System utilities (Clipboard, QR, etc.)",
            author="MAX CLI Team",
        )

    def register(self, app: typer.Typer) -> None:
        # Copy your existing command functions here
        @app.command("share")
        def share_qr(
            target: Path = typer.Argument(..., help="File to share"),
        ) -> None:
            """Generate a QR code for sharing a file."""
            # Implementation from cli_tools.py
            ...

        @app.command("paste")
        def paste_image() -> None:
            """Paste image from clipboard."""
            # Implementation from cli_tools.py
            ...


plugin = ToolsPlugin()
```

2. **Remove the commands from main.py** (or keep them as fallbacks)

3. **Test the plugin**:

```bash
max plugins list
max --help  # Should show new commands
```

---

## Troubleshooting

### Plugin Not Loading

1. Check plugin directory exists:
   ```bash
   ls ~/.max_cli/plugins/
   ```

2. Verify file has no syntax errors:
   ```bash
   python -m py_compile ~/.max_cli/plugins/your_plugin.py
   ```

3. Check plugin list:
   ```bash
   max plugins list --all
   ```

### Import Errors

If your plugin imports other max-cli modules, ensure they're available:

```python
# Good: Import only what's needed
from max_cli.common.logger import console

# May cause issues if dependencies aren't loaded
from max_cli.core.some_engine import SomeEngine
```

### Debug Logging

Enable debug logging to troubleshoot:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Add this at the top of your plugin file for development.

---

## API Reference

### Plugin Base Class

```python
class Plugin(ABC):
    @property
    def name(self) -> str: ...
    
    @property
    def version(self) -> str: ...
    
    @property
    def description(self) -> str: ...
    
    @property
    def metadata(self) -> PluginMetadata: ...
    
    @property
    def priority(self) -> int: ...
    
    def validate(self) -> tuple[bool, Optional[str]]: ...
    
    def on_load(self, context: PluginContext) -> None: ...
    
    def on_unload(self) -> None: ...
    
    @abstractmethod
    def register(self, app: typer.Typer) -> None: ...
    
    def unregister(self, app: typer.Typer) -> None: ...
```

### PluginContext

```python
@dataclass
class PluginContext:
    app: typer.Typer           # The main CLI app
    plugin_dir: Optional[Path] # Directory containing the plugin
    config: dict[str, Any]    # Plugin configuration
```

### PluginManager

```python
class PluginManager:
    def load_all(context: PluginContext) -> None: ...
    def register_all(app: typer.Typer) -> None: ...
    def enable_plugin(name: str) -> bool: ...
    def disable_plugin(name: str) -> bool: ...
    def get_plugin_info(name: str) -> Optional[dict]: ...
    def list_plugins(include_disabled: bool = False) -> list[str]: ...
```
