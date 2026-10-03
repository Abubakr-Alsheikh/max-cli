"""interface/tui/home_stats.py: what the Home page counts and shows."""

from datetime import date, datetime, timedelta

from max_cli.common.activity_log import ActivityEntry
from max_cli.interface.tui import home_stats

TODAY = date(2026, 10, 4)
NOW = datetime(2026, 10, 4, 15, 30)


def _entry(
    category: str,
    action: str = "compress",
    day: date = TODAY,
    status: str = "success",
    hour: int = 12,
    **details,
) -> ActivityEntry:
    entry = ActivityEntry(category, action, status=status, details=details)
    entry.timestamp = (
        datetime.combine(day, datetime.min.time()).replace(hour=hour).isoformat()
    )
    return entry


def test_kinds_have_their_own_name_and_colour():
    entries = [
        _entry("video"),
        _entry("video"),
        _entry("audio"),
        _entry("grab", "download"),  # an old alias of download
        _entry("command", "x"),  # what older versions logged
    ]

    counts = home_stats.type_counts(entries, TODAY)

    assert counts == [("video", 2), ("audio", 1), ("download", 1), ("tools", 1)]
    assert home_stats.look("video").label == "Video"
    assert home_stats.look("download").label == "Downloads"
    assert home_stats.look("nothing-known") == home_stats.OTHER


def test_only_finished_entries_in_the_window_count():
    entries = [
        _entry("video"),
        _entry("video", status="failed"),
        _entry("video", status="running"),  # not done yet
        _entry("video", status="queued"),
        _entry("video", day=TODAY - timedelta(days=20)),  # too old
    ]

    assert home_stats.type_counts(entries, TODAY) == [("video", 2)]
    stacks = home_stats.daily_stacks(entries, TODAY)
    assert len(stacks) == home_stats.WINDOW_DAYS
    assert stacks[-1].label == "now" and stacks[-1].highlight
    assert stacks[-1].total == 2


def test_a_day_is_split_by_kind_biggest_kind_first():
    entries = [_entry("audio"), _entry("video"), _entry("video")]

    today = home_stats.daily_stacks(entries, TODAY)[-1]

    assert today.parts == ((2, "$primary"), (1, "$secondary"))


def test_totals_compare_weeks_and_add_up_savings():
    entries = [
        _entry("video", details={"input_size": 1000, "output_size": 400}),
        _entry("pdf", details={"original_size": 500, "new_size": 300}),
        _entry("audio", output_files=["a.mp3", "b.mp3"]),
        _entry("video", day=TODAY - timedelta(days=8)),  # last week
        _entry("video", status="failed"),
    ]

    totals = home_stats.totals(entries, TODAY)

    assert (totals.this_week, totals.last_week) == (4, 1)
    assert totals.finished == 5 and totals.failed == 1
    assert totals.saved_bytes == 800 and totals.saving_actions == 2
    assert totals.files_made == 2


def test_a_streak_survives_a_day_not_over_yet():
    yesterday = [_entry("video", day=TODAY - timedelta(days=n)) for n in (1, 2, 3)]
    with_gap = [*yesterday, _entry("video", day=TODAY - timedelta(days=5))]

    assert home_stats.streak(yesterday, TODAY) == 3
    assert home_stats.streak([*with_gap, _entry("audio")], TODAY) == 4


def test_recent_rows_say_what_ran_on_what_and_what_came_out():
    entries = [
        _entry(
            "video",
            "compress",
            hour=9,
            args={"target": "C:/clips/trip.mp4"},
            via="ai",
            details={"input_size": 1000, "output_size": 300},
        ),
        _entry("ai", "agent", hour=14, prompt="shrink   the videos", tokens=4200),
        _entry(
            "audio",
            "compress",
            day=TODAY - timedelta(days=1),
            status="failed",
            args={"target": "song, live.wav"},  # a comma in a name stays
            error="Unsupported codec",
        ),
        _entry("video", status="running"),  # not finished: not shown
    ]

    rows = home_stats.recent_rows(entries, NOW)

    assert [row.when for row in rows] == ["14:00", "09:00", "yesterday"]
    ai, video, audio = rows
    assert (ai.kind, ai.what, ai.subject, ai.result) == (
        "AI",
        "request",
        '"shrink the videos"',
        "4.2k tokens",
    )
    assert (video.subject, video.via_ai) == ("trip.mp4", True)
    assert video.result.startswith("-70%")
    assert (audio.ok, audio.subject, audio.result) == (
        False,
        "song, live.wav",
        "Unsupported codec",
    )


def test_top_actions_are_the_ones_used_most():
    entries = [
        _entry("pdf", "merge"),
        _entry("video", "compress"),
        _entry("video", "compress"),
        _entry("grab", "download"),
        _entry("ai", "agent"),  # not an action the dashboard opens
    ]
    known = {"pdf.merge", "video.compress", "grab.download"}

    top = home_stats.top_actions(entries, known)

    assert top == ["video.compress", "pdf.merge", "grab.download"]


def test_durations_read_like_a_clock():
    assert home_stats.duration(0) == ""
    assert home_stats.duration(42_000) == "42s"
    assert home_stats.duration(212_000) == "3m 32s"
    assert home_stats.duration(3_900_000) == "1h 05m"
