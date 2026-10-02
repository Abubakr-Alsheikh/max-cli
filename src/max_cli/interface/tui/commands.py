"""Ctrl+P: find any dashboard action or page by typing part of its name.

Textual's command palette lists what this provider gives it next to its
own commands (themes, quit). Each action comes from the catalog, so a new
action shows up here without a change. Picking one opens its page with its
form shown (`MaxDashboardApp.open_action`).
"""

from functools import partial
from typing import TYPE_CHECKING, cast

from textual.command import DiscoveryHit, Hit, Hits, Provider

from max_cli.core.catalog import actions_for, group_names
from max_cli.core.catalog.spec import Surface
from max_cli.interface.tui.tool_pages import TOOL_PAGES
from max_cli.interface.tui.widgets.sidebar import SECTION_KEYS, SECTIONS

if TYPE_CHECKING:
    from max_cli.interface.tui.app import MaxDashboardApp

# The page each catalog group's actions are on.
GROUP_PAGES = {
    **{spec.group: spec.page_id for spec in TOOL_PAGES},
    "grab": "download",
    "tools": "extras",
}
PAGE_LABELS = {section_id: label for section_id, _icon, label in SECTIONS}


def palette_entries() -> list[tuple[str, str, str]]:
    """(text to match, help line, target) for every page and action.

    A target is "page:<id>" or "action:<group>.<name>".
    """
    entries = [
        (
            f"{label} page",
            f"Open it. Key {SECTION_KEYS[section_id]}",
            f"page:{section_id}",
        )
        for section_id, _icon, label in SECTIONS
    ]
    for group in group_names():
        page_label = PAGE_LABELS[GROUP_PAGES[group]]
        for action in actions_for(group, Surface.DASHBOARD):
            entries.append(
                (
                    f"{page_label}: {action.name}",
                    action.summary,
                    f"action:{action.id}",
                )
            )
    return entries


class ActionCommands(Provider):
    """Every page and every dashboard action."""

    async def startup(self) -> None:
        self._entries = palette_entries()

    def _run(self, target: str) -> None:
        kind, _, name = target.partition(":")
        app = cast("MaxDashboardApp", self.app)
        if kind == "page":
            app.navigate(name)
        else:
            app.open_action(name)

    async def discover(self) -> Hits:
        for text, help_text, target in self._entries:
            yield DiscoveryHit(text, partial(self._run, target), help=help_text)

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for text, help_text, target in self._entries:
            score = matcher.match(text)
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(text),
                    partial(self._run, target),
                    text=text,
                    help=help_text,
                )
