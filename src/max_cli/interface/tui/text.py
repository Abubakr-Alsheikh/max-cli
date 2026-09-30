"""Safe dashboard text: markup for our styling, plain text for anything else.

Error messages, video titles and AI replies can contain square brackets that
Textual's markup parser rejects, even after `escape()` (a yt-dlp error quoting
a command line crashed the Download page). Pass such values as `$name`
variables; Textual inserts them as plain text.
"""

from datetime import datetime

from textual.content import Content


def markup(template: str, **values: object) -> Content:
    """`template` is our markup; each `$name` is filled with `values[name]` as plain text."""
    return Content.from_markup(
        template, **{name: str(value) for name, value in values.items()}
    )


def relative_time(timestamp_raw: "str | None") -> str:
    """An ISO timestamp as "just now", "5m ago", "3h ago" or "2d ago"."""
    try:
        seconds = (
            datetime.now() - datetime.fromisoformat(timestamp_raw or "")
        ).total_seconds()
    except (ValueError, TypeError):
        return ""
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"
