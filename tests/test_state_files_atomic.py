"""A crash during a save must leave every state file as it was (hardening Phase 2).

Each test saves once, then makes Path.replace fail during a second save (the
moment an atomic write swaps files) and checks the first version survived.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from max_cli.common.cache import Cache
from max_cli.common.transaction_log import TransactionLog
from max_cli.core.engines.daemon_manager import DaemonManager
from max_cli.core.engines.queue_manager import QueueManager
from max_cli.core.engines.task_queue import TaskItem, TaskType
from max_cli.plugins.manager import PluginManager


def _break_replace(monkeypatch) -> None:
    def crash(self, destination):
        raise OSError("simulated crash while swapping files")

    monkeypatch.setattr(Path, "replace", crash)


def _no_temp_files(folder: Path) -> bool:
    return not any(p.name.endswith(".tmp") for p in folder.iterdir())


def test_daemon_queue_survives_crash(tmp_path, monkeypatch):
    queue_dir = tmp_path / "tasks"
    monkeypatch.setattr(DaemonManager, "QUEUE_DIR", queue_dir)
    monkeypatch.setattr(DaemonManager, "QUEUE_FILE", queue_dir / "queue.json")
    monkeypatch.setattr(DaemonManager, "HISTORY_FILE", queue_dir / "history.json")
    daemon = DaemonManager()
    daemon.add(TaskItem(type=TaskType.CUSTOM, title="first"))
    before = (queue_dir / "queue.json").read_text(encoding="utf-8")

    _break_replace(monkeypatch)
    daemon.add(TaskItem(type=TaskType.CUSTOM, title="second"))

    assert (queue_dir / "queue.json").read_text(encoding="utf-8") == before
    assert [t["title"] for t in json.loads(before)] == ["first"]
    assert _no_temp_files(queue_dir)


def test_grab_queue_survives_crash(tmp_path, monkeypatch):
    queue_file = tmp_path / "grab_queue.json"
    monkeypatch.setattr(QueueManager, "QUEUE_FILE", queue_file)
    monkeypatch.setattr(QueueManager, "HISTORY_FILE", tmp_path / "grab_history.json")
    manager = QueueManager()
    first = MagicMock()
    first.to_dict.return_value = {"url": "https://example.com/1"}
    manager._queue = [first]
    manager._save_queue()
    before = queue_file.read_text(encoding="utf-8")

    _break_replace(monkeypatch)
    second = MagicMock()
    second.to_dict.return_value = {"url": "https://example.com/2"}
    manager._queue = [first, second]
    manager._save_queue()

    assert queue_file.read_text(encoding="utf-8") == before
    assert _no_temp_files(tmp_path)


def test_cache_entry_survives_crash(tmp_path, monkeypatch):
    cache = Cache(cache_dir=tmp_path)
    cache.set("key", "v1")

    _break_replace(monkeypatch)
    with pytest.raises(OSError):
        cache.set("key", "v2")

    assert cache.get("key") == "v1"
    assert _no_temp_files(tmp_path)


def test_transaction_log_survives_crash(tmp_path, monkeypatch):
    log = TransactionLog("files order", tmp_path)
    log.record(
        op_type=TransactionLog.OP_MOVE, original_path=Path("a"), new_path=Path("b")
    )
    saved = log.save()
    before = saved.read_text(encoding="utf-8")

    _break_replace(monkeypatch)
    log.record(
        op_type=TransactionLog.OP_MOVE, original_path=Path("c"), new_path=Path("d")
    )
    with pytest.raises(OSError):
        log.save()

    assert saved.read_text(encoding="utf-8") == before
    assert _no_temp_files(tmp_path)


def test_plugin_config_survives_crash(tmp_path, monkeypatch):
    manager = PluginManager(plugin_dirs=[], config_dir=tmp_path)
    manager._enabled_plugins = {"hello": True}
    manager._save_config()
    config_file = tmp_path / "plugins.json"
    before = config_file.read_text(encoding="utf-8")

    _break_replace(monkeypatch)
    manager._enabled_plugins = {"hello": False}
    with pytest.raises(OSError):
        manager._save_config()

    assert config_file.read_text(encoding="utf-8") == before
    assert _no_temp_files(tmp_path)


def test_ai_chat_history_survives_crash(tmp_path, monkeypatch):
    from max_cli.core.engines.ai_engine import AIEngine

    engine = AIEngine.__new__(AIEngine)  # skip __init__: no client, no ~/.max_cli
    engine._history_file = tmp_path / "chat_history.json"
    engine.history = [{"role": "user", "content": "first"}]
    engine._save_history()
    before = engine._history_file.read_text(encoding="utf-8")

    _break_replace(monkeypatch)
    engine.history.append({"role": "user", "content": "second"})
    with pytest.raises(OSError):
        engine._save_history()

    assert engine._history_file.read_text(encoding="utf-8") == before
    assert _no_temp_files(tmp_path)
