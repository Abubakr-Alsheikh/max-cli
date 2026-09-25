"""CliRunner tests for `max queue` (src/max_cli/interface/cli_queue.py).

The autouse `isolated_task_store` fixture points the shared TaskManager at a
temp folder, so these tests use the real manager instead of a mock.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest
import typer
from rich.console import Console
from typer.testing import CliRunner

from max_cli.common import logger
from max_cli.common.exceptions import MaxError
from max_cli.core.engines.task_manager import get_task_manager
from max_cli.core.engines.task_queue import TaskItem, TaskStatus, TaskType
from max_cli.interface import cli_queue
from max_cli.interface.cli_queue import app as queue_app

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})


@pytest.fixture(autouse=True)
def plain_console(monkeypatch):
    """Swap the shared Rich console for a wide, colorless one.

    The logger console is built at import time, so the runner's NO_COLOR and
    COLUMNS never reach it; without this it emits ANSI codes and wraps paths.
    """
    plain = Console(
        theme=logger.custom_theme,
        width=300,
        height=1000,
        color_system=None,
        force_terminal=False,
        legacy_windows=False,
    )
    monkeypatch.setattr(logger, "console", plain)
    monkeypatch.setattr(cli_queue, "console", plain)


def _add_task(
    title: str,
    status: TaskStatus = TaskStatus.PENDING,
    task_type: TaskType = TaskType.CUSTOM,
) -> TaskItem:
    return get_task_manager().add(TaskItem(type=task_type, title=title, status=status))


def _record_history(title: str, task_type: TaskType = TaskType.CUSTOM) -> TaskItem:
    return get_task_manager().record(
        TaskItem(type=task_type, title=title, status=TaskStatus.COMPLETED)
    )


@pytest.mark.parametrize(
    "args",
    [
        ["--help"],
        ["status", "--help"],
        ["history", "--help"],
        ["cancel", "--help"],
        ["retry", "--help"],
        ["clear", "--help"],
        ["process", "--help"],
        ["stats", "--help"],
    ],
)
def test_help(args):
    result = runner.invoke(queue_app, args)
    assert result.exit_code == 0, result.output
    assert "Usage" in result.output


class TestStatus:
    def test_empty_queue(self):
        result = runner.invoke(queue_app, ["status"])
        assert result.exit_code == 0, result.output
        assert "Queue is empty." in result.output

    def test_lists_tasks_and_summary(self):
        pending = _add_task("Pending job")
        _add_task("Broken job", status=TaskStatus.FAILED)

        result = runner.invoke(queue_app, ["status"])

        assert result.exit_code == 0, result.output
        assert pending.id in result.output
        assert "Pending job" in result.output
        assert "Task Queue (2 total)" in result.output
        assert "Pending: 1" in result.output
        assert "Failed: 1" in result.output


class TestHistory:
    def test_empty_history(self):
        result = runner.invoke(queue_app, ["history"])
        assert result.exit_code == 0, result.output
        assert "No history." in result.output

    def test_filters_by_type(self):
        _record_history("Downloaded clip", TaskType.DOWNLOAD)
        _record_history("Merged pdfs", TaskType.PDF_MERGE)

        result = runner.invoke(queue_app, ["history", "--type", "pdf_merge"])

        assert result.exit_code == 0, result.output
        assert "Merged pdfs" in result.output
        assert "Downloaded clip" not in result.output
        assert "Task History (1 items)" in result.output

    def test_unknown_type_is_reported(self):
        result = runner.invoke(queue_app, ["history", "--type", "bogus"])
        assert result.exit_code != 0
        assert not isinstance(result.exception, ValueError)


class TestCancelAndRetry:
    def test_cancel_removes_pending_task(self):
        task = _add_task("To cancel")

        result = runner.invoke(queue_app, ["cancel", task.id])

        assert result.exit_code == 0, result.output
        assert f"Cancelled task {task.id}" in result.output
        assert get_task_manager().get_all() == []

    def test_cancel_unknown_task_fails(self):
        result = runner.invoke(queue_app, ["cancel", "nope1234"])
        assert result.exit_code == 1
        assert "not found or is running" in result.output

    def test_retry_moves_history_task_back_to_queue(self):
        task = _record_history("Old job")

        result = runner.invoke(queue_app, ["retry", task.id])

        assert result.exit_code == 0, result.output
        assert f"Retrying task {task.id}: Old job" in result.output
        queued = get_task_manager().get_all()
        assert [t.id for t in queued] == [task.id]
        assert queued[0].status == TaskStatus.PENDING

    def test_retry_unknown_task_fails(self):
        result = runner.invoke(queue_app, ["retry", "nope1234"])
        assert result.exit_code == 1
        assert "Task nope1234 not found" in result.output


class TestClear:
    def test_force_clears_pending_only(self):
        _add_task("Pending one")
        failed = _add_task("Failed one", status=TaskStatus.FAILED)

        result = runner.invoke(queue_app, ["clear", "--force"])

        assert result.exit_code == 0, result.output
        assert "Cleared 1 pending tasks" in result.output
        assert [t.id for t in get_task_manager().get_all()] == [failed.id]

    def test_failed_flag_clears_failed_only(self):
        pending = _add_task("Pending one")
        _add_task("Failed one", status=TaskStatus.FAILED)

        result = runner.invoke(queue_app, ["clear", "--failed", "--force"])

        assert result.exit_code == 0, result.output
        assert "Cleared 1 failed tasks" in result.output
        assert [t.id for t in get_task_manager().get_all()] == [pending.id]

    def test_all_flag_clears_everything(self):
        _add_task("Pending one")
        _add_task("Failed one", status=TaskStatus.FAILED)

        result = runner.invoke(queue_app, ["clear", "--all", "--force"])

        assert result.exit_code == 0, result.output
        assert "Cleared 2 tasks" in result.output
        assert get_task_manager().get_all() == []

    def test_declined_prompt_keeps_tasks(self):
        _add_task("Pending one")

        result = runner.invoke(queue_app, ["clear"], input="n\n")

        assert result.exit_code == 0, result.output
        assert "Cancelled." in result.output
        assert len(get_task_manager().get_all()) == 1

    def test_accepted_prompt_clears(self):
        _add_task("Pending one")

        result = runner.invoke(queue_app, ["clear"], input="y\n")

        assert result.exit_code == 0, result.output
        assert "Cleared 1 pending tasks" in result.output
        assert get_task_manager().get_all() == []


class TestProcessAndStats:
    def test_process_empty_queue(self):
        result = runner.invoke(queue_app, ["process"])
        assert result.exit_code == 0, result.output
        assert "Processed 0 tasks" in result.output

    @patch("max_cli.interface.cli_queue._get_engine")
    def test_process_passes_max(self, mock_get_engine):
        manager = MagicMock()
        manager.process_now.return_value = 2
        mock_get_engine.return_value = manager

        result = runner.invoke(queue_app, ["process", "--max", "2"])

        assert result.exit_code == 0, result.output
        manager.process_now.assert_called_once_with(max_tasks=2)
        assert "Processed 2 tasks" in result.output

    def test_stats_counts_by_status_and_type(self):
        _add_task("a", task_type=TaskType.DOWNLOAD)
        _add_task("b", task_type=TaskType.DOWNLOAD)
        _add_task("c", status=TaskStatus.PAUSED, task_type=TaskType.PDF_MERGE)

        result = runner.invoke(queue_app, ["stats"])

        assert result.exit_code == 0, result.output
        assert "Queue Statistics" in result.output
        assert "Total in queue:  3" in result.output
        assert "Pending:       2" in result.output
        assert "Paused:        1" in result.output
        assert "download: 2" in result.output
        assert "pdf_merge: 1" in result.output


class TestErrors:
    @patch("max_cli.interface.cli_queue._get_engine")
    def test_max_error_propagates_to_top_level_handler(self, mock_get_engine):
        mock_get_engine.return_value.get_stats.side_effect = MaxError("store broken")

        result = runner.invoke(queue_app, ["stats"])

        # cli_queue has no local handler; main() turns MaxError into a message.
        assert result.exit_code == 1
        assert isinstance(result.exception, MaxError)

    @patch("max_cli.interface.cli_queue._get_engine")
    def test_main_reports_max_error_without_traceback(
        self, mock_get_engine, monkeypatch, capsys
    ):
        from max_cli import main as main_module

        mock_get_engine.return_value.get_stats.side_effect = MaxError("store broken")
        monkeypatch.setattr(main_module, "app", typer.Typer(name="max"))
        monkeypatch.setattr(main_module, "init_plugins", MagicMock())
        monkeypatch.setattr(sys, "argv", ["max", "queue", "stats"])

        with pytest.raises(SystemExit) as exit_info:
            main_module.main()

        assert exit_info.value.code == 1
        output = capsys.readouterr().out
        assert "Error:" in output
        assert "store broken" in output
        assert "Traceback" not in output
