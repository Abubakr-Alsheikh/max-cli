"""Every ported CLI group matches its catalog entries (PLANS/active/command-catalog.md, Q1).

The Typer commands stay hand-written. These tests fail when a command and its
catalog action disagree on options, spellings, defaults or queue support, or
when an action's operation takes different arguments.
"""

import importlib
import inspect
from pathlib import Path
from typing import Any

import pytest
import typer

from max_cli.core.catalog import GROUP_MODULES, load_group
from max_cli.core.catalog.runner import _operation
from max_cli.core.catalog.spec import Action, Setting
from max_cli.core.cli.registry import _GROUPS

QUEUE_OPTION = "queue"
# Groups whose Typer commands call their operations. `grab` joins in
# grab-page-redesign.md phase G5; until then only its operations are checked.
CLI_CHECKED_GROUPS = ("video",)


def _cli_commands(group_name: str) -> dict[str, Any]:
    module = importlib.import_module(_GROUPS[group_name].module)
    click_group = typer.main.get_command(module.app)
    return {
        name: command
        for name, command in click_group.commands.items()
        if not command.hidden
    }


def _normalize(value: Any) -> Any:
    return str(value) if isinstance(value, Path) else value


CASES = [
    (group_name, action)
    for group_name in GROUP_MODULES
    for action in load_group(group_name).actions
]
CLI_CASES = [case for case in CASES if case[0] in CLI_CHECKED_GROUPS]


@pytest.mark.parametrize("group_name", CLI_CHECKED_GROUPS)
def test_every_visible_command_has_an_action(group_name):
    commands = set(_cli_commands(group_name))
    actions = {action.name for action in load_group(group_name).actions}
    assert commands == actions


@pytest.mark.parametrize(
    "group_name, action", CLI_CASES, ids=[action.id for _, action in CLI_CASES]
)
def test_cli_options_match_the_catalog(group_name: str, action: Action):
    command = _cli_commands(group_name)[action.name]
    cli_params = {param.name: param for param in command.params}

    has_queue = cli_params.pop(QUEUE_OPTION, None) is not None
    assert has_queue == action.queueable
    assert list(cli_params) == [param.name for param in action.params]

    for param in action.params:
        cli_param = cli_params[param.name]
        assert cli_param.required == param.required, param.name
        if not param.required:
            assert _normalize(cli_param.default) == param.default, param.name
        if param.cli:
            assert set(cli_param.opts) == set(param.cli), param.name
        else:
            assert cli_param.param_type_name == "argument", param.name


@pytest.mark.parametrize(
    "group_name, action", CASES, ids=[action.id for _, action in CASES]
)
def test_operation_arguments_match_the_catalog(group_name: str, action: Action):
    signature = inspect.signature(_operation(action))
    op_params = {
        name: param
        for name, param in signature.parameters.items()
        if param.kind is not inspect.Parameter.KEYWORD_ONLY
    }
    assert list(op_params) == [param.name for param in action.params]
    for param in action.params:
        op_default = op_params[param.name].default
        if param.required:
            assert op_default is inspect.Parameter.empty, param.name
        elif isinstance(param.default, Setting):
            # The operation reads the setting itself when given None.
            assert op_default is None, param.name
        else:
            assert _normalize(op_default) == param.default, param.name
