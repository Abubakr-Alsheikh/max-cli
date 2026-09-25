"""TUI command defaults must match the CLI (hardening Phase 4).

For every TUI command that has a CLI twin, each field whose name matches a
CLI parameter must default to the same value. Before Phase 4 the TUI used
CRF 32 for "max" video compression and the CLI used 35.
"""

import importlib

import pytest
import typer

from max_cli.interface.tui.command_registry import CommandRegistry

CLI_APPS = {
    "video": "max_cli.interface.cli_media",
    "images": "max_cli.interface.cli_images",
    "pdf": "max_cli.interface.cli_pdf",
    "audio": "max_cli.interface.cli_audio",
    "files": "max_cli.interface.cli_files",
    "grab": "max_cli.interface.cli_network",
    "ai": "max_cli.interface.cli_ai",
}


# Deliberate differences. The dashboard previews file moves before running them.
INTENDED_DIFFERENCES = {
    ("files", "order", "dry_run"),
    ("files", "smart_sort", "dry_run"),
}


def _cli_defaults(category: str, command: str) -> dict:
    module = importlib.import_module(CLI_APPS[category])
    group = typer.main.get_command(module.app)
    cli_command = group.commands.get(command.replace("_", "-")) or group.commands.get(
        command
    )
    if cli_command is None:
        return {}
    return {param.name: param.default for param in cli_command.params}


def _shared_commands():
    for category in CommandRegistry.get_categories():
        if category not in CLI_APPS:
            continue
        for command, schema in CommandRegistry.get_commands(category).items():
            yield pytest.param(category, command, schema, id=f"{category}.{command}")


@pytest.mark.parametrize("category, command, schema", _shared_commands())
def test_tui_defaults_match_cli(category, command, schema):
    cli_defaults = _cli_defaults(category, command)
    mismatches = {
        field["name"]: (field["default"], cli_defaults[field["name"]])
        for field in schema["fields"]
        if field["name"] in cli_defaults
        and (category, command, field["name"]) not in INTENDED_DIFFERENCES
        and field["default"] is not None
        and cli_defaults[field["name"]] is not None
        and field["default"] != cli_defaults[field["name"]]
    }
    assert mismatches == {}, f"TUI default vs CLI default: {mismatches}"


def test_video_compress_levels_come_from_presets():
    from max_cli.core.presets import VIDEO_CRF_BY_LEVEL
    from max_cli.interface.tui.command_executor import CommandExecutor

    schema = CommandRegistry.get_command("video", "compress")
    executor = CommandExecutor()
    for level, crf in VIDEO_CRF_BY_LEVEL.items():
        params = executor._map_engine_params(
            "video", "compress", {"level": level}, schema
        )
        assert params["crf"] == crf
