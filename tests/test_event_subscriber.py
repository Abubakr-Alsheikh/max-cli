from max_cli.common.events import (
    EventEmitter,
    BatchProgressEvent,
    FileStartEvent,
    FileCompleteEvent,
    FileErrorEvent,
    CompleteEvent,
    StatusEvent,
    ProgressEvent,
)
from max_cli.interface.event_subscriber import EventSubscriber


class TestEventSubscriber:
    def setup_method(self):
        self.emitter = EventEmitter()
        self.subscriber = EventSubscriber(self.emitter)

    def teardown_method(self):
        self.subscriber.unsubscribe()
        self.emitter.clear()

    def test_subscribe_receives_events(self):
        self.subscriber.subscribe()
        self.emitter.emit(StatusEvent(message="test"))
        self.subscriber.unsubscribe()

    def test_batch_progress_updates(self):
        self.subscriber.subscribe()
        self.subscriber.create_progress_context(3, "Test")
        self.emitter.emit(BatchProgressEvent(current=1, total=3, description="Test"))
        assert self.subscriber._progress is not None

    def test_file_start_creates_task(self):
        self.subscriber.subscribe()
        self.subscriber.create_progress_context(3, "Test")
        self.emitter.emit(FileStartEvent(file="a.txt", action="Compress"))
        assert "a.txt" in self.subscriber._file_tasks

    def test_file_complete_updates_stats(self):
        self.subscriber.subscribe()
        self.subscriber.create_progress_context(1, "Test")
        self.emitter.emit(FileStartEvent(file="a.txt", action="Compress"))
        self.emitter.emit(FileCompleteEvent(file="a.txt", result={"size": 100}))
        assert self.subscriber._stats["success"] == 1
        assert "a.txt" not in self.subscriber._file_tasks

    def test_file_error_updates_stats(self):
        self.subscriber.subscribe()
        self.subscriber.create_progress_context(1, "Test")
        self.emitter.emit(FileStartEvent(file="a.txt", action="Compress"))
        self.emitter.emit(FileErrorEvent(file="a.txt", error="fail"))
        assert self.subscriber._stats["failed"] == 1

    def test_complete_event_prints_summary(self):
        self.subscriber.subscribe()
        self.subscriber.create_progress_context(1, "Test")
        self.emitter.emit(
            CompleteEvent(summary={"successful": 1, "failed": 0, "total": 1})
        )
        self.subscriber.unsubscribe()

    def test_progress_event_updates_task(self):
        self.subscriber.subscribe()
        self.subscriber.create_progress_context(1, "Test")
        self.emitter.emit(FileStartEvent(file="a.txt", action="Compress"))
        self.emitter.emit(ProgressEvent(file="a.txt", percentage=50.0))
        self.subscriber.unsubscribe()

    def test_create_progress_context(self):
        ctx = self.subscriber.create_progress_context(5, "Testing")
        assert ctx is not None
        assert self.subscriber._batch_task is not None
