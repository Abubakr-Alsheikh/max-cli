"""core/catalog/activity.py: runs outside the dashboard's forms and the agent
reach the activity log, which Home and History read."""

from pathlib import Path

import pytest

from max_cli.common.activity_log import ActivityLog
from max_cli.common.exceptions import ProcessingError
from max_cli.core.catalog import get_action
from max_cli.core.catalog.activity import action_for, run_recorded
from max_cli.core.engines.task_queue import TaskItem, TaskType
from max_cli.core.operations import pdf
from max_cli.core.operations.result import ActionResult


def _only_entry():
    (entry,) = ActivityLog().get_entries()
    return entry


def test_an_operation_is_found_under_its_catalog_action():
    assert action_for(pdf.merge).id == "pdf.merge"
    assert action_for(lambda: None) is None


def test_a_run_is_logged_with_its_arguments_and_result(monkeypatch):
    def merge(inputs, output=None, *, engine=None):
        return ActionResult(True, "Merged 2 files", [Path("both.pdf")])

    merge.__module__, merge.__name__ = pdf.merge.__module__, "merge"

    run_recorded(merge, inputs=[Path("a.pdf"), Path("b.pdf")], engine=object())

    entry = _only_entry()
    assert (entry.category, entry.action, entry.status) == ("pdf", "merge", "success")
    assert entry.details["args"] == {"inputs": "a.pdf, b.pdf"}  # no engine
    assert entry.details["via"] == "cli"


def test_a_failed_run_is_logged_and_still_raises():
    def merge(inputs, output=None, *, engine=None):
        raise ProcessingError("damaged PDF")

    merge.__module__, merge.__name__ = pdf.merge.__module__, "merge"

    with pytest.raises(ProcessingError):
        run_recorded(merge, inputs=[Path("a.pdf")])

    entry = _only_entry()
    assert entry.status == "failed"
    assert entry.details["error"] == "damaged PDF"


def test_the_queue_worker_logs_the_jobs_it_runs(monkeypatch, tmp_path):
    from max_cli.core.catalog import runner

    def fake_run(action, args, **hooks):
        return ActionResult(True, "Compressed", [tmp_path / "a_compressed.mp4"])

    monkeypatch.setattr(runner, "run_action", fake_run)
    task = TaskItem(
        type=TaskType.ACTION,
        title="video compress a.mp4",
        payload={"action": "video.compress", "args": {"target": str(tmp_path)}},
    )

    runner._action_executor(task)

    entry = _only_entry()
    assert (entry.category, entry.action, entry.status) == (
        "video",
        "compress",
        "success",
    )
    assert entry.details["via"] == "queue"


def test_a_cli_batch_is_one_entry(monkeypatch, tmp_path):
    from max_cli.core.catalog import runner
    from max_cli.interface.batch_cli import run_batch

    for name in ("a.mp4", "b.mp4"):
        (tmp_path / name).write_bytes(b"\0")
    monkeypatch.setattr(
        runner, "run_action", lambda action, args, **kw: ActionResult(True, "ok")
    )

    assert run_batch("video.compress", {"target": [tmp_path]})

    entry = _only_entry()
    assert entry.action == "compress" and len(entry.details["details"]["done"]) == 2
    assert get_action("video.compress").group == entry.category


def test_an_entry_added_later_comes_first_on_the_same_timestamp(monkeypatch):
    """Windows' clock gave the agent's request and its action one timestamp,
    and the request (logged last) landed below the action."""
    from datetime import datetime

    from max_cli.common import activity_log
    from max_cli.common.activity_log import ActivityLog

    frozen = datetime(2026, 10, 7, 12, 0, 0)

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen

    monkeypatch.setattr(activity_log, "datetime", Frozen)
    ActivityLog().add_entry("files", "preview", "success", {})
    ActivityLog().add_entry("ai", "agent", "success", {})

    newest, older = ActivityLog().get_entries(limit=2)

    assert (newest.category, older.category) == ("ai", "files")
