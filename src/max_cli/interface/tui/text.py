"""Safe dashboard text: markup for our styling, plain text for anything else.

Error messages, video titles and AI replies can contain square brackets that
Textual's markup parser rejects, even after `escape()` (a yt-dlp error quoting
a command line crashed the Download page). Pass such values as `$name`
variables; Textual inserts them as plain text.
"""

from textual.content import Content


def markup(template: str, **values: object) -> Content:
    """`template` is our markup; each `$name` is filled with `values[name]` as plain text."""
    return Content.from_markup(
        template, **{name: str(value) for name, value in values.items()}
    )
