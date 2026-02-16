# Example Plugins

This directory contains example plugins for Max CLI.

## Installation

1. Copy the plugin file to your plugins directory:
   - `~/.max_cli/plugins/` (user-level)
   - `./plugins/` (project-level)

2. Or install as a Python package in development mode.

## Available Plugins

### Hello World Plugin

A simple demonstration plugin that adds `hello` and `goodbye` commands.

```bash
max hello --name "Your Name"
max hello --name "Alice" --verbose
max goodbye --name "Bob"
```

## Creating Your Own Plugin

Create a new Python file in the plugins directory:

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
    
    @property
    def description(self) -> str:
        return "My custom plugin"
    
    def register(self, app: typer.Typer) -> None:
        @app.command("my-command")
        def my_command():
            typer.echo("Hello from my plugin!")
```

## Plugin Types

- `CLIPlugin` - Adds CLI commands
- `EnginePlugin` - Adds processing engines
- `Plugin` - Base class for any plugin
