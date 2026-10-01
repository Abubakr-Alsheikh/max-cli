"""main(): output that the console's code page can't encode."""

import io
import sys

from max_cli.main import tolerate_unencodable_output

SPINNER_FRAME = "⠋"


def test_an_unencodable_character_prints_as_a_question_mark(monkeypatch):
    """A spinner frame crashed `max audio organize` when its output went to a
    file on a Windows machine with code page cp1256."""
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1256")
    monkeypatch.setattr(sys, "stdout", stream)

    tolerate_unencodable_output()
    sys.stdout.write(f"{SPINNER_FRAME} Organizing")
    sys.stdout.flush()

    assert raw.getvalue() == b"? Organizing"


def test_utf8_output_is_left_alone(monkeypatch):
    stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", errors="strict")
    monkeypatch.setattr(sys, "stdout", stream)

    tolerate_unencodable_output()

    assert stream.errors == "strict"
