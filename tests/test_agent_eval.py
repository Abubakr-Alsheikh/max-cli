"""scripts/agent_eval.py: the scoring, with a scripted model (no network)."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load() -> ModuleType:
    path = REPO_ROOT / "scripts" / "agent_eval.py"
    spec = importlib.util.spec_from_file_location("agent_eval", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["agent_eval"] = module  # dataclasses look the module up by name
    spec.loader.exec_module(module)
    return module


agent_eval = _load()


def _answer(content: str = "", calls: tuple = ()) -> Any:
    message = SimpleNamespace(content=content, tool_calls=list(calls) or None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(total_tokens=50),
    )


def _call(name: str, arguments: dict, call_id: str) -> Any:
    return SimpleNamespace(
        id=call_id, function=SimpleNamespace(name=name, arguments=json.dumps(arguments))
    )


class Scripted:
    def __init__(self, *responses: Any) -> None:
        self._responses = list(responses)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **request: Any) -> Any:
        return self._responses.pop(0)


def _convert(target: str, call_id: str) -> Any:
    return _call(
        "run_action",
        {
            "action": "video.audio-convert",
            "arguments": {"target": target, "format": "mp3"},
        },
        call_id,
    )


def _batch_scenario() -> Any:
    return next(s for s in agent_eval.SCENARIOS if s.name == "batch")


def test_one_batch_call_passes(tmp_path):
    scenario = _batch_scenario()
    model = Scripted(
        _answer(calls=(_call("load_group", {"name": "video"}, "1"),)),
        _answer(calls=(_convert("music", "2"),)),
        _answer("Planned it."),
    )

    run = agent_eval.run_scenario(scenario, model, "test-model", tmp_path / "work")

    assert agent_eval.score(scenario, run) == []
    assert [name for name, _ in run.calls] == ["load_group", "run_action"]
    assert run.tokens == 150


def test_a_call_per_file_fails(tmp_path):
    scenario = _batch_scenario()
    model = Scripted(
        _answer(calls=(_call("load_group", {"name": "video"}, "1"),)),
        _answer(
            calls=(
                _convert("music/a.m4a", "2"),
                _convert("music/b.m4a", "3"),
                _convert("music/live/c.m4a", "4"),
            )
        ),
        _answer("Planned them."),
    )

    run = agent_eval.run_scenario(scenario, model, "test-model", tmp_path / "work")

    assert agent_eval.score(scenario, run) == [
        "3 video.audio-convert calls; one batch call expected"
    ]


def test_the_scenarios_keep_their_checks():
    names = [scenario.name for scenario in agent_eval.SCENARIOS]

    assert names == ["batch", "plan", "look-first", "memory"]
    assert all(scenario.checks for scenario in agent_eval.SCENARIOS)
