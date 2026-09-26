"""Bare `max` opens the dashboard at a terminal and prints help elsewhere (D2)."""

import io
import os
import subprocess
import sys
from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from max_cli.core.cli import lazy_group, registry
from max_cli.core.cli.lazy_group import LazyTyperGroup, is_interactive

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})
DASHBOARD_RUN = "max_cli.interface.tui.app.MaxDashboardApp.run"
SUBPROCESS_TIMEOUT_SECONDS = 30


def _root_app() -> typer.Typer:
    """Built like max_cli.main.app."""
    app = typer.Typer(name="max", cls=LazyTyperGroup, no_args_is_help=True)
    registry.register(app)
    return app


@pytest.fixture
def at_a_terminal(monkeypatch):
    monkeypatch.setattr(lazy_group, "is_interactive", lambda: True)


def test_bare_max_opens_the_dashboard_at_a_terminal(at_a_terminal):
    with patch(DASHBOARD_RUN) as run:
        result = runner.invoke(_root_app(), [])

    assert result.exit_code == 0, result.output
    run.assert_called_once_with()


@pytest.mark.parametrize(
    ("args", "expected"),
    [(["--help"], "Usage"), (["queue", "stats"], "Queue Statistics")],
)
def test_commands_still_run_at_a_terminal(at_a_terminal, args, expected):
    with patch(DASHBOARD_RUN) as run:
        result = runner.invoke(_root_app(), args)

    assert result.exit_code == 0, result.output
    assert expected in result.output
    run.assert_not_called()


def test_bare_max_prints_help_when_not_at_a_terminal():
    """CliRunner's streams aren't terminals, like a script's or a pipe's."""
    with patch(DASHBOARD_RUN) as run:
        result = runner.invoke(_root_app(), [])

    assert "Usage" in result.output
    run.assert_not_called()


def test_piped_bare_max_prints_help_in_a_real_process():
    """The real entry point with pipes: help, and no dashboard waiting for keys."""
    result = subprocess.run(
        [sys.executable, "-m", "max_cli.main"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "NO_COLOR": "1", "COLUMNS": "200"},
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
    )

    assert "Usage" in result.stdout + result.stderr


class _Stream(io.StringIO):
    def __init__(self, tty: bool) -> None:
        super().__init__()
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


@pytest.mark.parametrize(
    ("stdin", "stdout", "expected"),
    [
        (_Stream(True), _Stream(True), True),
        (_Stream(False), _Stream(True), False),  # input piped in
        (_Stream(True), _Stream(False), False),  # output piped or redirected
        (None, _Stream(True), False),  # pythonw.exe has no console streams
    ],
)
def test_is_interactive_needs_both_streams(monkeypatch, stdin, stdout, expected):
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)

    assert is_interactive() is expected
