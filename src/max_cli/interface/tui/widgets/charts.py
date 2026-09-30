"""Small terminal charts drawn with block characters, in theme colours.

Both charts redraw only when their data changes (`set_data` compares), so a
2-second page refresh with the same numbers costs nothing.
"""

from typing import NamedTuple

from textual.content import Content
from textual.geometry import Size
from textual.widget import Widget

# One cell split into eighths, from empty to full.
EIGHTHS = " ▁▂▃▄▅▆▇█"
FULL_BLOCK = "█"
BASELINE = "▁"


class Bar(NamedTuple):
    label: str
    value: int
    highlight: bool = False


class BarChart(Widget):
    """Vertical bars with a label under each, e.g. actions per day.

    The last row holds the labels; the row above the bars shows the peak.
    """

    DEFAULT_CSS = """
    BarChart {
        height: 10;
        width: 1fr;
    }
    """

    def __init__(self, *, id: str) -> None:
        super().__init__(id=id)
        self._bars: list[Bar] = []

    def set_data(self, bars: list[Bar]) -> None:
        if bars != self._bars:
            self._bars = bars
            self.refresh()

    def render(self) -> Content:
        width, height = self.content_size.width, self.content_size.height
        bars = self._bars
        if width <= 0 or height < 3:
            return Content("")
        if not any(bar.value for bar in bars):
            blank = "\n" * max(0, height // 2 - 1)
            return Content.styled(
                f"{blank}No activity yet. Downloads and tools you run show up here.",
                "$text-muted",
            )
        slot = max(1, width // len(bars))
        bar_width = max(1, slot - 1)
        # Centre the bars: the width rarely divides evenly by the bar count.
        indent = (" " * ((width - slot * len(bars) + 1) // 2), "")
        peak = max((bar.value for bar in bars), default=0)
        rows = height - 2  # one row for the peak note, one for labels
        levels = rows * 8
        lines: list[Content] = [Content.styled(f"peak {peak}", "dim")]
        for row in range(rows):
            cells: list[tuple[str, str]] = [indent]
            floor = (rows - row - 1) * 8
            for bar in bars:
                filled = round(bar.value / peak * levels) if peak else 0
                if bar.value and filled == 0:
                    filled = 1  # a small non-zero day stays visible
                part = min(8, max(0, filled - floor))
                style = "bold $secondary" if bar.highlight else "$primary"
                if part == 0 and row == rows - 1:
                    cells.append((BASELINE * bar_width + " ", "$boost"))
                else:
                    cells.append((EIGHTHS[part] * bar_width + " ", style))
            lines.append(Content.assemble(*cells))
        labels = [
            indent,
            *(
                (
                    bar.label[:slot].center(slot),
                    "bold $secondary" if bar.highlight else "dim",
                )
                for bar in bars
            ),
        ]
        lines.append(Content.assemble(*labels))
        return Content("\n").join(lines)


class HBar(NamedTuple):
    label: str
    value: int
    style: str = "$primary"


class HBarChart(Widget):
    """Horizontal bars, one per row: label, bar, count."""

    DEFAULT_CSS = """
    HBarChart {
        height: auto;
        width: 1fr;
    }
    """

    LABEL_WIDTH = 10
    COUNT_WIDTH = 5

    def __init__(self, *, id: str) -> None:
        super().__init__(id=id)
        self._bars: list[HBar] = []

    def set_data(self, bars: list[HBar]) -> None:
        if bars != self._bars:
            self._bars = bars
            self.refresh(layout=True)

    def get_content_height(self, container: Size, viewport: Size, width: int) -> int:
        return max(1, len(self._bars))

    def render(self) -> Content:
        if not self._bars:
            return Content.styled("Nothing yet", "dim")
        track = max(
            4, self.content_size.width - self.LABEL_WIDTH - self.COUNT_WIDTH - 2
        )
        peak = max(bar.value for bar in self._bars) or 1
        lines = []
        for bar in self._bars:
            eighths = round(bar.value / peak * track * 8)
            full, part = divmod(eighths, 8)
            filled = FULL_BLOCK * full + (EIGHTHS_H[part] if part else "")
            lines.append(
                Content.assemble(
                    (
                        f"{bar.label[: self.LABEL_WIDTH]:<{self.LABEL_WIDTH}} ",
                        "$text-muted",
                    ),
                    (filled, f"{bar.style} on $boost"),
                    (" " * (track - len(filled)), "on $boost"),
                    (f" {bar.value:>{self.COUNT_WIDTH}}", "bold"),
                )
            )
        return Content("\n").join(lines)


# Left-aligned partial blocks, for horizontal bars.
EIGHTHS_H = " ▏▎▍▌▋▊▉█"


class Spark(Widget):
    """A percentage over time on a fixed 0-100 scale, newest on the right.

    Textual's Sparkline scales to its own data, so a steady 30% filled the
    whole height; here 30% is always 30%.
    """

    DEFAULT_CSS = """
    Spark {
        height: 2;
        width: 1fr;
    }
    """

    def __init__(self, *, classes: str = "") -> None:
        super().__init__(classes=classes)
        self._values: list[float] = []
        self._style = "$primary"

    def set_data(self, values: list[float], style: str = "$primary") -> None:
        if values != self._values or style != self._style:
            self._values, self._style = values, style
            self.refresh()

    def render(self) -> Content:
        width, rows = self.content_size.width, self.content_size.height
        if width <= 0 or rows <= 0:
            return Content("")
        values = self._values[-width:]
        padded = [0.0] * (width - len(values)) + values
        levels = rows * 8
        lines = []
        for row in range(rows):
            floor = (rows - row - 1) * 8
            cells = []
            for value in padded:
                filled = round(min(100.0, max(0.0, value)) / 100 * levels)
                part = min(8, max(0, filled - floor))
                cells.append(
                    EIGHTHS[part] if part else (BASELINE if row == rows - 1 else " ")
                )
            text = "".join(cells)
            lines.append(
                Content.styled(
                    text, self._style if row < rows - 1 else f"{self._style}"
                )
            )
        return Content("\n").join(lines)


class Meter(Widget):
    """How full something is, as one bar: used in colour, free as a track."""

    DEFAULT_CSS = """
    Meter {
        height: 1;
        width: 1fr;
    }
    """

    def __init__(self, *, classes: str = "") -> None:
        super().__init__(classes=classes)
        self._percent = 0.0
        self._style = "$primary"

    def set_value(self, percent: float, style: str = "$primary") -> None:
        if (percent, style) != (self._percent, self._style):
            self._percent, self._style = percent, style
            self.refresh()

    def render(self) -> Content:
        width = self.content_size.width
        eighths = round(min(100.0, max(0.0, self._percent)) / 100 * width * 8)
        full, part = divmod(eighths, 8)
        filled = FULL_BLOCK * full + (EIGHTHS_H[part] if part else "")
        return Content.assemble(
            (filled, self._style),
            # A drawn track in $border: an "on $boost" background vanished on
            # cards and rows whose own background is close to $boost.
            (FULL_BLOCK * max(0, width - len(filled)), "$border"),
        )
