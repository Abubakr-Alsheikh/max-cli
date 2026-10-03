"""What the Home page shows, worked out from the activity log.

Every number and chart on Home reads the same entries over the same window,
so the tiles, the activity chart and BY TYPE can't disagree. Only finished
entries count (success or failed): a request that is still running, or a
job that was only queued, isn't something Max did yet.

Plain functions over `ActivityEntry` lists, so tests can feed them entries
without a running app.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from max_cli.common.activity_log import CATEGORY_ALIASES, ActivityEntry
from max_cli.common.utils import format_size
from max_cli.interface.tui.widgets.charts import Stack

WINDOW_DAYS = 14  # the activity chart, BY TYPE and the tiles look this far back
WEEK_DAYS = 7
FINISHED = ("success", "failed")
VIA_AI = "ai"
AI_GROUP = "ai"
AGENT_ACTIONS = ("agent", "chat", "ask")
RECENT_ROWS = 8
TOP_ACTIONS = 4


@dataclass(frozen=True)
class TypeLook:
    label: str
    style: str  # a theme colour: types are told apart by colour on Home


# Activity category (a command group) -> its name and colour on Home. $error
# stays free for failures.
TYPE_LOOK: dict[str, TypeLook] = {
    "video": TypeLook("Video", "$primary"),
    "audio": TypeLook("Audio", "$secondary"),
    "download": TypeLook("Downloads", "$success"),
    "ai": TypeLook("AI", "$accent"),
    "pdf": TypeLook("PDF", "$warning"),
    "images": TypeLook("Images", "$primary-darken-2"),
    "files": TypeLook("Files", "$accent-lighten-2"),
    "tools": TypeLook("Tools", "$foreground"),
}
# Categories older Max versions logged, and what they are today.
OLD_CATEGORIES = {"command": "tools", "file_op": "files", "task": "tools"}
OTHER = TypeLook("Other", "$text-muted")


def kind_of(entry: ActivityEntry) -> str:
    """The entry's category as Home groups it (grab is download, ...)."""
    category = CATEGORY_ALIASES.get(entry.category, entry.category)
    return OLD_CATEGORIES.get(category, category)


def look(kind: str) -> TypeLook:
    return TYPE_LOOK.get(kind, OTHER)


def day_of(entry: ActivityEntry) -> Optional[date]:
    try:
        return datetime.fromisoformat(entry.timestamp).date()
    except (TypeError, ValueError):
        return None


def finished(entries: list[ActivityEntry]) -> list[ActivityEntry]:
    return [entry for entry in entries if entry.status in FINISHED]


def within(
    entries: list[ActivityEntry], today: date, days: int = WINDOW_DAYS
) -> list[ActivityEntry]:
    """The entries of the last `days` days, today included."""
    first = today - timedelta(days=days - 1)
    return [
        entry
        for entry in entries
        if (day := day_of(entry)) is not None and first <= day <= today
    ]


# --- charts ---------------------------------------------------------------------


def daily_stacks(
    entries: list[ActivityEntry], today: date, days: int = WINDOW_DAYS
) -> list[Stack]:
    """Finished actions per day, oldest first, split by kind; today marked."""
    order = [kind for kind, _count in type_counts(entries, today, days)]
    per_day: dict[date, Counter[str]] = {}
    for entry in within(finished(entries), today, days):
        day = day_of(entry)
        if day is not None:
            per_day.setdefault(day, Counter())[kind_of(entry)] += 1
    stacks = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        counts = per_day.get(day, Counter())
        parts = tuple(
            (counts[kind], look(kind).style) for kind in order if counts[kind]
        )
        label = "now" if offset == 0 else day.strftime("%d")
        stacks.append(Stack(label, parts, highlight=offset == 0))
    return stacks


def type_counts(
    entries: list[ActivityEntry], today: date, days: int = WINDOW_DAYS
) -> list[tuple[str, int]]:
    """(kind, finished actions) in the window, most first. AI counts the
    requests you made; the actions the agent ran count in their own kinds."""
    counts = Counter(kind_of(entry) for entry in within(finished(entries), today, days))
    return counts.most_common()


# --- tiles ------------------------------------------------------------------------


@dataclass(frozen=True)
class Totals:
    this_week: int
    last_week: int
    finished: int  # in the window
    failed: int
    saved_bytes: int
    saving_actions: int  # actions that made something smaller
    files_made: int
    streak: int  # days in a row, up to today or yesterday, with something done


def totals(entries: list[ActivityEntry], today: date) -> Totals:
    done = finished(entries)
    window = within(done, today)
    this_week = within(done, today, WEEK_DAYS)
    last_week = within(done, today - timedelta(days=WEEK_DAYS), WEEK_DAYS)
    saved = [saved_bytes(entry) for entry in window if entry.status == "success"]
    return Totals(
        this_week=len(this_week),
        last_week=len(last_week),
        finished=len(window),
        failed=sum(entry.status == "failed" for entry in window),
        saved_bytes=sum(saved),
        saving_actions=sum(1 for amount in saved if amount > 0),
        files_made=sum(
            len(output_files(entry)) for entry in window if entry.status == "success"
        ),
        streak=streak(done, today),
    )


def streak(entries: list[ActivityEntry], today: date) -> int:
    """Days in a row with a finished action, ending today, or yesterday when
    nothing ran yet today (the streak isn't broken before the day ends)."""
    days = {day for entry in entries if (day := day_of(entry)) is not None}
    current = today if today in days else today - timedelta(days=1)
    count = 0
    while current in days:
        count += 1
        current -= timedelta(days=1)
    return count


def result_details(entry: ActivityEntry) -> dict[str, Any]:
    """The action result's own details: actions log them under "details"."""
    details = entry.details or {}
    inner = details.get("details")
    return inner if isinstance(inner, dict) else details


def saved_bytes(entry: ActivityEntry) -> int:
    """Bytes an action took off: compressing, optimizing ... 0 if it grew."""
    found = result_details(entry)
    if isinstance(found.get("saved_bytes"), (int, float)):
        return max(0, int(found["saved_bytes"]))
    for before_key, after_key in (
        ("input_size", "output_size"),
        ("original_size", "new_size"),
    ):
        before, after = found.get(before_key), found.get(after_key)
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            return max(0, int(before - after))
    return 0


def output_files(entry: ActivityEntry) -> list[str]:
    files = (entry.details or {}).get("output_files") or []
    return [str(item) for item in files] if isinstance(files, list) else []


# --- recent -----------------------------------------------------------------------


@dataclass(frozen=True)
class RecentRow:
    when: str  # 14:02, yesterday, 01 Oct
    ok: bool
    kind: str
    what: str  # the action: "audio-convert", "asked"
    subject: str  # a file name, a prompt, a link
    result: str  # what came out: a file, "3 files", "-42%", an error
    took: str  # 1m 12s
    via_ai: bool
    style: str = field(default="$primary")


def recent_rows(
    entries: list[ActivityEntry], now: datetime, limit: int = RECENT_ROWS
) -> list[RecentRow]:
    """The newest finished entries, each with what it ran on and what it made."""
    rows = []
    newest = sorted(finished(entries), key=lambda entry: entry.timestamp, reverse=True)
    for entry in newest[:limit]:
        kind = kind_of(entry)
        details = entry.details or {}
        ok = entry.status == "success"
        rows.append(
            RecentRow(
                when=when(entry, now),
                ok=ok,
                kind=look(kind).label,
                what=_what(entry, kind),
                subject=subject(entry),
                result=_result(entry, ok),
                took=duration(entry.duration_ms),
                via_ai=details.get("via") == VIA_AI,
                style=look(kind).style,
            )
        )
    return rows


def when(entry: ActivityEntry, now: datetime) -> str:
    try:
        moment = datetime.fromisoformat(entry.timestamp)
    except (TypeError, ValueError):
        return ""
    if moment.date() == now.date():
        return moment.strftime("%H:%M")
    if moment.date() == now.date() - timedelta(days=1):
        return "yesterday"
    return moment.strftime("%d %b")


def _what(entry: ActivityEntry, kind: str) -> str:
    if kind == AI_GROUP and entry.action in AGENT_ACTIONS:
        return "request"
    return entry.action


def subject(entry: ActivityEntry) -> str:
    """What the entry was about: a prompt, a file, files, a link, a title."""
    details = entry.details or {}
    prompt = details.get("prompt")
    if prompt:
        return f'"{" ".join(str(prompt).split())}"'
    for key in ("title", "url"):
        if details.get(key):
            return str(details[key])
    args = details.get("args") or details.get("params") or {}
    if isinstance(args, dict):
        for key in ("target", "targets", "inputs", "url", "folder", "path"):
            value = args.get(key)
            if value:
                return _names(value)
    return ""


def _names(value: Any) -> str:
    """A path's name, or "a.mp3 +2 more" for a list. Text stays whole: a
    file name may hold commas."""
    if isinstance(value, (list, tuple)):
        names = [Path(str(item)).name or str(item) for item in value if item]
        if len(names) > 1:
            return f"{names[0]} +{len(names) - 1} more"
        return names[0] if names else ""
    return Path(str(value)).name or str(value)


def _result(entry: ActivityEntry, ok: bool) -> str:
    details = entry.details or {}
    if not ok:
        return str(details.get("error") or details.get("message") or "failed")
    saved = saved_bytes(entry)
    found = result_details(entry)
    before = found.get("input_size") or found.get("original_size")
    if saved and isinstance(before, (int, float)) and before:
        return f"-{saved * 100 // int(before)}% · {format_size(saved)} saved"
    files = output_files(entry)
    if len(files) == 1:
        return f"→ {Path(files[0]).name}"
    if files:
        return f"→ {len(files)} files"
    if details.get("tokens"):
        return f"{int(details['tokens']) / 1000:.1f}k tokens"
    return ""


def duration(milliseconds: int) -> str:
    seconds = int(milliseconds or 0) // 1000
    if seconds <= 0:
        return ""
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds:02}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02}m"


# --- pick up again ------------------------------------------------------------------


def top_actions(
    entries: list[ActivityEntry], known: set[str], limit: int = TOP_ACTIONS
) -> list[str]:
    """The catalog actions you ran most, newest first among equals; only ids
    in `known` (actions the dashboard can open)."""
    counts: Counter[str] = Counter()
    newest: dict[str, int] = {}
    for position, entry in enumerate(finished(entries)):
        action_id = f"{kind_of(entry)}.{entry.action}"
        if kind_of(entry) == "download":
            action_id = "grab.download"
        if action_id in known:
            counts[action_id] += 1
            newest.setdefault(action_id, position)
    return sorted(
        counts, key=lambda action_id: (-counts[action_id], newest[action_id])
    )[:limit]
