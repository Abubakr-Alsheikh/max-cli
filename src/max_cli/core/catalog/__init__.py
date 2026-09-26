"""One catalog of actions for the CLI, the dashboard and the AI agent.

See PLANS/active/command-catalog.md. Each group lives in its own module under
`groups/` and loads on first use, so reading one group never imports another.
Catalog modules import no engines; an action's operation is imported only
when it runs (`core/catalog/runner.py`).
"""

import importlib
from functools import cache

from max_cli.core.catalog.spec import Action, Group, Surface

# Group name -> module holding its GROUP. Add a group here when you port it.
GROUP_MODULES: dict[str, str] = {
    "video": "max_cli.core.catalog.groups.video",
    "grab": "max_cli.core.catalog.groups.grab",
    "images": "max_cli.core.catalog.groups.images",
}


def group_names() -> tuple[str, ...]:
    return tuple(GROUP_MODULES)


@cache
def load_group(name: str) -> Group:
    if name not in GROUP_MODULES:
        raise KeyError(f"Unknown catalog group '{name}'")
    group: Group = importlib.import_module(GROUP_MODULES[name]).GROUP
    return group


def get_action(action_id: str) -> Action:
    """An action by its id, e.g. "video.compress"."""
    group_name, _, action_name = action_id.partition(".")
    return load_group(group_name).action(action_name)


def actions_for(group_name: str, surface: Surface) -> tuple[Action, ...]:
    """The group's actions that `surface` may offer."""
    return tuple(
        action
        for action in load_group(group_name).actions
        if surface in action.surfaces
    )
