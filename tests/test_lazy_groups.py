"""Built-in command groups load on first use (hardening decision D5)."""

import subprocess
import sys

import pytest
import typer
from typer.testing import CliRunner

from max_cli.core.cli import registry
from max_cli.core.cli.lazy_group import LAZY_GROUPS, LazyTyperGroup, load_group

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})
SUBPROCESS_TIMEOUT_SECONDS = 30


def _root_app() -> typer.Typer:
    app = typer.Typer(name="max", cls=LazyTyperGroup)
    registry.register(app)
    return app


def _interface_modules_after(code: str) -> list:
    probe = (
        "import sys\n" + code + "\nprint('\\n'.join(sorted(m for m in sys.modules"
        " if m.startswith('max_cli.interface'))))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.split()


def test_registering_commands_imports_no_command_group():
    loaded = _interface_modules_after("import max_cli.main as m\nm.register(m.app)")
    assert loaded == []


def test_help_lists_groups_without_importing_them():
    loaded = _interface_modules_after(
        "import max_cli.main as m\n"
        "from typer.testing import CliRunner\n"
        "m.register(m.app)\n"
        "result = CliRunner().invoke(m.app, ['--help'])\n"
        "assert result.exit_code == 0, result.output\n"
        "assert 'video' in result.output and 'queue' in result.output\n"
    )
    assert loaded == []


def test_help_hides_aliases():
    result = runner.invoke(_root_app(), ["--help"])

    assert result.exit_code == 0, result.output
    for alias in ("img", "v", "file", "net", "a"):
        assert f" {alias} " not in result.output


@pytest.mark.parametrize("name", sorted(registry._GROUPS))
def test_every_group_loads(name):
    registry.register(typer.Typer(cls=LazyTyperGroup))

    command = load_group(name)

    assert command.name == name
    assert command.hidden == LAZY_GROUPS[name].hidden


def test_running_a_group_loads_it_on_demand():
    result = runner.invoke(_root_app(), ["queue", "stats"])

    assert result.exit_code == 0, result.output
    assert "Queue Statistics" in result.output


def test_ai_group_gets_the_full_app_for_its_command_list(monkeypatch):
    from max_cli.interface import cli_ai

    monkeypatch.setattr(cli_ai, "MAIN_APP_REF", None)
    registry.register(typer.Typer(cls=LazyTyperGroup))

    load_group("ai")

    group_names = {group.name for group in cli_ai.MAIN_APP_REF.registered_groups}
    assert {"video", "pdf", "grab", "queue"} <= group_names
