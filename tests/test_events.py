from max_cli.common.events import (
    EventEmitter,
    EventType,
    EventLevel,
    StatusEvent,
    BatchProgressEvent,
    FileErrorEvent,
    CompleteEvent,
    get_emitter,
    reset_emitter,
)
from max_cli.common.concurrent import process_batch_parallel, process_batch_sequential


class TestEventTypes:
    def test_event_type_enum_values(self):
        assert EventType.PROGRESS.value == "progress"
        assert EventType.BATCH_PROGRESS.value == "batch_progress"
        assert EventType.FILE_START.value == "file_start"
        assert EventType.FILE_COMPLETE.value == "file_complete"
        assert EventType.FILE_ERROR.value == "file_error"
        assert EventType.STATUS.value == "status"
        assert EventType.COMPLETE.value == "complete"

    def test_event_level_enum_values(self):
        assert EventLevel.INFO.value == "info"
        assert EventLevel.ERROR.value == "error"
        assert EventLevel.WARNING.value == "warning"
        assert EventLevel.SUCCESS.value == "success"

    def test_status_event_defaults(self):
        event = StatusEvent(message="test")
        assert event.type == EventType.STATUS
        assert event.message == "test"
        assert event.level == EventLevel.INFO

    def test_batch_progress_event(self):
        event = BatchProgressEvent(
            current=5, total=10, percentage=50.0, description="Test"
        )
        assert event.type == EventType.BATCH_PROGRESS
        assert event.current == 5
        assert event.total == 10
        assert event.percentage == 50.0

    def test_file_error_event(self):
        event = FileErrorEvent(file="test.txt", error="fail")
        assert event.type == EventType.FILE_ERROR
        assert event.level == EventLevel.ERROR


class TestEventEmitter:
    def setup_method(self):
        self.emitter = EventEmitter()

    def teardown_method(self):
        self.emitter.clear()

    def test_subscribe_and_emit(self):
        received = []
        self.emitter.subscribe(lambda e: received.append(e))
        self.emitter.emit(StatusEvent(message="hello"))
        assert len(received) == 1
        assert received[0].message == "hello"

    def test_multiple_subscribers(self):
        received1, received2 = [], []
        self.emitter.subscribe(lambda e: received1.append(e))
        self.emitter.subscribe(lambda e: received2.append(e))
        self.emitter.emit(StatusEvent(message="test"))
        assert len(received1) == 1
        assert len(received2) == 1

    def test_unsubscribe(self):
        received = []

        def cb(e):
            received.append(e)

        self.emitter.subscribe(cb)
        self.emitter.unsubscribe(cb)
        self.emitter.emit(StatusEvent(message="test"))
        assert len(received) == 0

    def test_queue_mode(self):
        self.emitter.emit(StatusEvent(message="hello"))
        self.emitter.emit(CompleteEvent())
        events = list(self.emitter.event_generator())
        assert len(events) == 2
        assert events[0].type == EventType.STATUS
        assert events[1].type == EventType.COMPLETE

    def test_subscriber_error_does_not_crash_emit(self):
        def bad_cb(e):
            raise ValueError("boom")

        self.emitter.subscribe(bad_cb)
        self.emitter.emit(StatusEvent(message="test"))

    def test_clear(self):
        self.emitter.subscribe(lambda e: None)
        self.emitter.emit(StatusEvent(message="test"))
        self.emitter.clear()
        assert len(self.emitter._subscribers) == 0

    def test_get_emitter_singleton(self):
        reset_emitter()
        e1 = get_emitter()
        e2 = get_emitter()
        assert e1 is e2
        reset_emitter()


class TestProcessBatchWithEvents:
    def setup_method(self):
        self.emitter = EventEmitter()

    def teardown_method(self):
        self.emitter.clear()

    def test_parallel_emits_events(self):
        results = process_batch_parallel(
            [1, 2, 3], lambda x: x * 2, emitter=self.emitter, action="Doubling"
        )
        events = []
        while not self.emitter.get_queue().empty():
            events.append(self.emitter.get_queue().get())
        assert any(e.type == EventType.COMPLETE for e in events)
        assert len(results) == 3

    def test_parallel_emits_file_events(self):
        process_batch_parallel(
            ["a.txt", "b.txt"],
            lambda x: x.upper(),
            emitter=self.emitter,
            action="Upper",
        )
        events = []
        while not self.emitter.get_queue().empty():
            events.append(self.emitter.get_queue().get())
        start_events = [e for e in events if e.type == EventType.FILE_START]
        complete_events = [e for e in events if e.type == EventType.FILE_COMPLETE]
        assert len(start_events) == 2
        assert len(complete_events) == 2

    def test_parallel_handles_errors(self):
        def failing(x):
            if x == 2:
                raise ValueError("fail")
            return x
        results = process_batch_parallel(
            [1, 2, 3], failing, emitter=self.emitter, action="Test"
        )
        assert len(results) == 3
        error_result = next(r for r in results if r.get("item") == 2)
        assert error_result["error"] == "fail"
        events = []
        while not self.emitter.get_queue().empty():
            events.append(self.emitter.get_queue().get())
        error_events = [e for e in events if e.type == EventType.FILE_ERROR]
        assert len(error_events) == 1

    def test_sequential_emits_events(self):
        results = process_batch_sequential(
            [1, 2, 3], lambda x: x * 2, emitter=self.emitter, action="Doubling"
        )
        events = []
        while not self.emitter.get_queue().empty():
            events.append(self.emitter.get_queue().get())
        assert any(e.type == EventType.COMPLETE for e in events)
        assert len(results) == 3

    def test_no_emitter_still_works(self):
        results = process_batch_parallel([1, 2, 3], lambda x: x * 2)
        assert len(results) == 3
        assert {r["result"] for r in results} == {2, 4, 6}

    def test_complete_event_has_summary(self):
        def failing(x):
            if x == 2:
                raise ValueError("fail")
            return x

        process_batch_parallel([1, 2, 3], failing, emitter=self.emitter, action="Test")
        events = []
        while not self.emitter.get_queue().empty():
            events.append(self.emitter.get_queue().get())
        complete = [e for e in events if e.type == EventType.COMPLETE][0]
        assert complete.summary["total"] == 3
        assert complete.summary["successful"] == 2
        assert complete.summary["failed"] == 1
