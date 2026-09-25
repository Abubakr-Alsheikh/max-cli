"""One task store for queue, grab downloads and download history (decision D1)."""

import json

import pytest

from max_cli.core.engines import task_manager as task_manager_module
from max_cli.core.engines.download_history import DownloadHistory
from max_cli.core.engines.network_engine import _download_executor, make_download_task
from max_cli.core.engines.task_manager import TaskManager, get_task_manager
from max_cli.core.engines.task_queue import TaskItem, TaskStatus, TaskType


def _write_json(path, data) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


GRAB_QUEUE = [
    {"id": "q1", "url": "https://youtu.be/a", "status": "pending", "quality": "m"},
    {"id": "q2", "url": "https://youtu.be/b", "status": "downloading"},
]
GRAB_HISTORY = [
    {
        "id": "h1",
        "url": "https://youtu.be/c",
        "status": "completed",
        "title": "Song C",
        "audio_only": True,
        "file_path": "/music/c.mp3",
        "file_size": 42,
        "added_at": "2026-09-01T10:00:00",
        "completed_at": "2026-09-01T10:05:00",
    }
]
DOWNLOAD_HISTORY = {
    "downloads": [
        {
            "url": "https://vimeo.com/1",
            "title": "",
            "timestamp": "2026-09-10T09:00:00",
            "output_files": ["/videos/one.mp4"],
            "settings": {"quality": "h", "subtitles": True},
            "file_size": 7,
            "status": "completed",
        }
    ],
    "last_output": {},
    "last_settings": {},
}


class TestLegacyMigration:
    def test_old_stores_fold_into_task_store(self, isolated_task_store):
        _write_json(isolated_task_store / "grab_queue.json", GRAB_QUEUE)
        _write_json(isolated_task_store / "grab_history.json", GRAB_HISTORY)
        _write_json(isolated_task_store / "download_history.json", DOWNLOAD_HISTORY)

        manager = TaskManager()

        queued = manager.get_all()
        assert [t.id for t in queued] == ["q1", "q2"]
        assert all(t.status == TaskStatus.PENDING for t in queued)
        assert queued[0].payload == {"url": "https://youtu.be/a", "quality": "m"}

        history = manager.get_history(limit=0)
        assert [t.payload["url"] for t in history] == [
            "https://vimeo.com/1",
            "https://youtu.be/c",
        ]
        grabbed = history[1]
        assert grabbed.title == "Song C"
        assert grabbed.output_files == ["/music/c.mp3"]
        assert grabbed.result["file_size"] == 42
        assert grabbed.payload["audio_only"] is True

    def test_old_files_are_renamed_not_deleted(self, isolated_task_store):
        _write_json(isolated_task_store / "grab_history.json", GRAB_HISTORY)

        TaskManager()

        assert not (isolated_task_store / "grab_history.json").exists()
        assert (isolated_task_store / "grab_history.json.migrated").exists()

    def test_migration_runs_once(self, isolated_task_store):
        _write_json(isolated_task_store / "grab_history.json", GRAB_HISTORY)
        TaskManager()

        second = TaskManager()

        assert len(second.get_history(limit=0)) == 1

    def test_unreadable_old_file_is_left_in_place(self, isolated_task_store):
        broken = isolated_task_store / "grab_queue.json"
        broken.write_text("{not json", encoding="utf-8")

        manager = TaskManager()

        assert broken.exists()
        assert manager.get_all() == []


class TestTaskManagerFilters:
    def test_process_now_runs_only_the_requested_type(self, monkeypatch):
        manager = TaskManager()
        ran = []
        monkeypatch.setattr(
            task_manager_module,
            "get_executor",
            lambda task_type: lambda task: ran.append(task.type) or {},
        )
        manager.add(TaskItem(type=TaskType.CUSTOM, title="other"))
        manager.add(TaskItem(type=TaskType.DOWNLOAD, title="download"))

        assert manager.process_now(task_type=TaskType.DOWNLOAD) == 1
        assert ran == [TaskType.DOWNLOAD]
        assert [t.type for t in manager.get_pending()] == [TaskType.CUSTOM]

    def test_clear_by_type_keeps_other_tasks(self):
        manager = TaskManager()
        manager.add(TaskItem(type=TaskType.CUSTOM))
        manager.add(TaskItem(type=TaskType.DOWNLOAD))

        assert manager.clear(task_type=TaskType.DOWNLOAD) == 1
        assert [t.type for t in manager.get_all()] == [TaskType.CUSTOM]

    def test_record_adds_finished_task_to_history(self):
        manager = TaskManager()

        task = manager.record(
            TaskItem(type=TaskType.DOWNLOAD, status=TaskStatus.COMPLETED)
        )

        assert manager.get_history(limit=0) == [task]
        assert task.completed_at is not None
        assert TaskManager().get_history(limit=0)[0].id == task.id  # persisted

    def test_refresh_sees_tasks_added_by_another_instance(self):
        manager = TaskManager()
        TaskManager().add(TaskItem(type=TaskType.CUSTOM, title="elsewhere"))

        manager.refresh()

        assert [t.title for t in manager.get_all()] == ["elsewhere"]

    def test_get_task_manager_shares_one_instance(self):
        assert get_task_manager() is get_task_manager()


class TestDownloadHistoryView:
    @pytest.fixture
    def history(self) -> DownloadHistory:
        return DownloadHistory(TaskManager())

    def test_recorded_download_is_found_by_url(self, history):
        history.record_download(
            url="https://youtu.be/x",
            title="X",
            output_files=["/dl/x.mp4"],
            settings_used={"quality": "h", "output_path": "/dl"},
        )

        entry = history.is_already_downloaded("https://youtu.be/x")
        assert entry is not None
        assert entry["title"] == "X"
        assert history.is_already_downloaded("https://youtu.be/other") is None

    def test_last_output_path_is_per_domain(self, history):
        history.record_download(url="https://youtu.be/a", output_files=["/yt/a.mp4"])
        history.record_download(url="https://vimeo.com/b", output_files=["/vm/b.mp4"])

        assert history.get_last_output_path("https://youtu.be/new").endswith("yt")
        assert history.get_last_output_path("https://example.com/c") is None

    def test_last_settings_come_from_newest_download(self, history):
        history.record_download(url="https://a.com/1", settings_used={"quality": "s"})
        history.record_download(url="https://a.com/2", settings_used={"quality": "x"})

        assert history.get_last_settings() == {"quality": "x"}

    def test_recent_lists_each_url_once(self, history):
        history.record_download(url="https://a.com/1", status="failed")
        history.record_download(url="https://a.com/1")

        recent = history.get_recent()
        assert len(recent) == 1
        assert recent[0]["status"] == "completed"

    def test_clear_removes_only_downloads(self):
        manager = TaskManager()
        history = DownloadHistory(manager)
        history.record_download(url="https://a.com/1")
        manager.record(TaskItem(type=TaskType.CUSTOM, status=TaskStatus.COMPLETED))

        assert history.clear_history() == 1
        assert [t.type for t in manager.get_history(limit=0)] == [TaskType.CUSTOM]


class TestDownloadTasks:
    def test_make_download_task_keeps_only_download_options(self, tmp_path):
        task = make_download_task(
            "https://youtu.be/a", quality="m", output_path=tmp_path, unknown=1
        )

        assert task.type == TaskType.DOWNLOAD
        assert task.payload == {
            "url": "https://youtu.be/a",
            "quality": "m",
            "output_path": str(tmp_path),
        }

    def test_executor_reports_downloaded_files(self, tmp_path, monkeypatch):
        downloaded = tmp_path / "Song.mp4"
        downloaded.write_bytes(b"12345")
        seen = {}

        def fake_download(self, **kwargs):
            seen.update(kwargs)
            hook = kwargs["progress_hook"]
            hook({"status": "downloading", "downloaded_bytes": 5, "total_bytes": 10})
            hook(
                {
                    "status": "finished",
                    "filename": str(downloaded),
                    "info_dict": {"title": "Song"},
                }
            )
            return {}

        monkeypatch.setattr(
            "max_cli.core.engines.network_engine.NetworkEngine.download_media",
            fake_download,
        )
        task = make_download_task(
            "https://youtu.be/a", output_path=tmp_path, playlist_items="2"
        )

        result = _download_executor(task)

        assert result["output_files"] == [str(downloaded)]
        assert result["file_size"] == 5
        assert task.title == "Song"
        assert seen["playlist_items"] == "2"
