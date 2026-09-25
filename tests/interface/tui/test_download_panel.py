from types import SimpleNamespace
from unittest.mock import patch

from textual.worker import WorkerState

from max_cli.interface.tui.widgets.download_panel import DownloadPanel


def _state_event(state: WorkerState, result=None, error=None) -> SimpleNamespace:
    worker = SimpleNamespace(name="_download_worker", result=result, error=error)
    return SimpleNamespace(worker=worker, state=state)


def test_worker_success_calls_finished_handler():
    panel = DownloadPanel()
    payload = {"result": None, "values": {"url": "https://example.com"}}

    with patch.object(DownloadPanel, "_on_download_finished") as finished:
        panel.on_worker_state_changed(_state_event(WorkerState.SUCCESS, result=payload))

    finished.assert_called_once_with(payload)


def test_worker_error_calls_error_handler():
    panel = DownloadPanel()

    with patch.object(DownloadPanel, "_on_download_error") as failed:
        panel.on_worker_state_changed(
            _state_event(WorkerState.ERROR, error=RuntimeError("boom"))
        )

    failed.assert_called_once_with("boom")
