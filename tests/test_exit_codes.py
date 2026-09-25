"""`max` exits 1 when a command reported an error with log_error."""

import sys
from unittest.mock import MagicMock

import pytest

from max_cli import main as main_module


def _run_max(monkeypatch, *args: str) -> int:
    monkeypatch.setattr(main_module, "init_plugins", MagicMock())
    monkeypatch.setattr(sys, "argv", ["max", *args])
    with pytest.raises(SystemExit) as exit_info:
        main_module.main()
    return exit_info.value.code


def test_reported_error_exits_1(monkeypatch, tmp_path):
    """`tools copy` logs the error and returns; the exit code used to be 0."""
    assert _run_max(monkeypatch, "tools", "copy", str(tmp_path / "missing.txt")) == 1


def test_successful_command_exits_0(monkeypatch):
    assert _run_max(monkeypatch, "queue", "stats") == 0


def test_explicit_exit_code_is_kept(monkeypatch):
    """Usage errors keep click's own code (2), not 1."""
    assert _run_max(monkeypatch, "queue", "history", "--limit", "abc") == 2
