"""The command catalog: loading, argument checking, JSON Schema and the queue path."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from max_cli.common.exceptions import ValidationError
from max_cli.core.catalog import actions_for, get_action, load_group
from max_cli.core.catalog.runner import (
    _action_executor,
    coerce_args,
    enqueue_action,
    run_action,
)
from max_cli.core.catalog.schema import action_schema
from max_cli.core.catalog.spec import Surface
from max_cli.core.engines.task_manager import get_task_manager
from max_cli.core.engines.task_queue import TaskType, get_executor
from max_cli.core.presets import DEFAULT_VIDEO_PRESET, VIDEO_CRF_BY_LEVEL


def test_unknown_group_and_action_raise_key_error():
    with pytest.raises(KeyError):
        load_group("nope")
    with pytest.raises(KeyError):
        get_action("video.nope")


def test_live_commands_stay_out_of_the_dashboard_and_agent():
    agent_actions = {action.name for action in actions_for("video", Surface.AGENT)}
    assert "compress" in agent_actions
    assert not agent_actions & {"record", "stream", "preview"}


def test_loading_the_catalog_imports_no_engine():
    code = (
        "import sys; from max_cli.core.catalog import load_group; "
        "load_group('video'); "
        "print([m for m in sys.modules if m.startswith('max_cli.core.engines')])"
    )
    output = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert output == "[]"


class TestCoerceArgs:
    def test_strings_become_typed_values_and_blanks_use_defaults(self):
        args = coerce_args(
            get_action("video.gif"),
            {"target": "~/clip.mp4", "width": "320", "fps": "", "output": None},
        )
        assert args == {
            "target": Path("~/clip.mp4").expanduser(),
            "output": None,
            "width": 320,
            "fps": 15,
        }

    def test_bool_words(self):
        action = get_action("video.record")
        assert coerce_args(action, {"audio": "yes"})["audio"] is True
        assert coerce_args(action, {"audio": "off"})["audio"] is False
        with pytest.raises(ValidationError, match="expects bool"):
            coerce_args(action, {"audio": "maybe"})

    def test_missing_required_value(self):
        with pytest.raises(ValidationError, match="'start' is required"):
            coerce_args(get_action("video.cut"), {"target": "a.mp4"})

    def test_unknown_option(self):
        with pytest.raises(ValidationError, match="unknown option"):
            coerce_args(get_action("video.mute"), {"target": "a.mp4", "crf": 20})

    def test_choice_outside_the_list(self):
        with pytest.raises(ValidationError, match="must be one of"):
            coerce_args(
                get_action("video.compress"), {"target": "a.mp4", "level": "ultra"}
            )

    def test_bad_number(self):
        with pytest.raises(ValidationError, match="expects int"):
            coerce_args(get_action("video.gif"), {"target": "a.mp4", "fps": "fast"})


def test_action_schema_is_a_json_tool_definition():
    schema = action_schema(get_action("video.cut"))

    assert schema["name"] == "video.cut"
    assert "danger: writes_new" in schema["description"]
    assert schema["parameters"]["required"] == ["target", "start"]
    assert schema["parameters"]["properties"]["target"]["type"] == "string"
    json.dumps(schema)


def test_choice_params_list_their_values():
    schema = action_schema(get_action("video.compress"))
    level = schema["parameters"]["properties"]["level"]
    assert level["enum"] == ["high", "balanced", "max"]
    assert level["default"] == "balanced"


def test_run_action_passes_typed_args_to_the_operation(dummy_video):
    engine = MagicMock()

    result = run_action(
        get_action("video.snap"), {"target": str(dummy_video)}, engine=engine
    )

    output_path = dummy_video.parent / "test_thumb.jpg"
    engine.get_thumbnail.assert_called_once_with(dummy_video, output_path, "00:00:05")
    assert result.ok
    assert result.output_files == [output_path]


@pytest.mark.parametrize("level, crf", list(VIDEO_CRF_BY_LEVEL.items()))
def test_dashboard_compress_uses_the_cli_crf_and_naming(tmp_path, level, crf):
    """Moved from the old TUI executor tests: same CRF and file name as the CLI."""
    source = tmp_path / "clip.mov"
    source.write_bytes(b"x")
    engine = MagicMock()

    run_action(
        get_action("video.compress"),
        {"target": str(source), "level": level},
        engine=engine,
    )

    engine.compress_video.assert_called_once_with(
        source, tmp_path / "clip_compressed.mp4", crf=crf, preset=DEFAULT_VIDEO_PRESET
    )


def test_dashboard_concat_accepts_a_glob_like_the_cli(tmp_path):
    for name in ["b.mp4", "a.mp4"]:
        (tmp_path / name).write_bytes(b"")
    engine = MagicMock()

    run_action(
        get_action("video.concat"),
        {"target": str(tmp_path / "*.mp4"), "method": "fast"},
        engine=engine,
    )

    inputs = engine.concatenate_videos.call_args.args[0]
    assert [path.name for path in inputs] == ["a.mp4", "b.mp4"]
    assert engine.concatenate_videos.call_args.kwargs["method"] == "concat"


class TestQueue:
    def test_non_queueable_action_is_refused(self, dummy_video):
        with pytest.raises(ValidationError, match="can't be queued"):
            enqueue_action(get_action("video.mute"), {"target": str(dummy_video)})

    def test_bad_arguments_fail_before_queueing(self):
        with pytest.raises(ValidationError):
            enqueue_action(get_action("video.compress"), {"level": "max"})
        assert get_task_manager().get_all() == []

    def test_queued_action_runs_through_the_executor(self, dummy_video):
        task = enqueue_action(
            get_action("video.compress"), {"target": dummy_video, "level": "high"}
        )
        assert task.title == "video compress test.mp4"
        assert get_executor(TaskType.ACTION) is _action_executor

        engine = MagicMock()
        with patch(
            "max_cli.core.engines.media_engine.MediaEngine", return_value=engine
        ):
            result = _action_executor(task)

        output_path = dummy_video.parent / "test_compressed.mp4"
        assert engine.compress_video.call_args.args[:2] == (dummy_video, output_path)
        assert engine.compress_video.call_args.kwargs["crf"] == 23
        assert result["output_files"] == [str(output_path)]
