"""core/catalog/batch.py: one action over many files, skipping finished work."""

import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from max_cli.common.exceptions import ValidationError
from max_cli.core.catalog import batch, get_action, load_group, runner
from max_cli.core.catalog.batch import expand_each, output_for, run_each
from max_cli.core.catalog.runner import run_action
from max_cli.core.operations.result import ActionResult

# What each kind of input is called in the name-template check.
SAMPLE_INPUT = {"video": "clip.mov", "audio": "song.m4a", "pdf": "doc.pdf"}
REQUIRED = {"pdf.lock": {"password": "secret"}}
TEMPLATED = [
    action
    for group in ("video", "audio", "pdf")
    for action in load_group(group).actions
    if action.output_name
]


@pytest.mark.parametrize("action", TEMPLATED, ids=[a.id for a in TEMPLATED])
def test_each_name_template_matches_what_the_operation_writes(action, tmp_path):
    """A wrong template would redo finished files, or skip unfinished ones."""
    source = tmp_path / SAMPLE_INPUT[action.each_param().kinds[0]]
    source.write_bytes(b"\0")
    args = {"target": str(source), **REQUIRED.get(action.id, {})}

    engine = MagicMock()
    # optimize reads the new file's size afterwards.
    engine.optimize_pdf.side_effect = lambda source, output, **kw: output.touch()

    result = run_action(action, args, engine=engine)

    assert result.output_files, result.message
    assert Path(result.output_files[0]) == output_for(action, source, args)


def _files(folder: Path, *names: str) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    paths = [folder / name for name in names]
    for path in paths:
        path.write_bytes(b"\0")
    return paths


AUDIO_CONVERT = get_action("video.audio-convert")
VIDEO_COMPRESS = get_action("video.compress")


def test_a_folder_gives_its_files_of_the_actions_kinds(tmp_path):
    _files(tmp_path, "a.m4a", "b.wav", "notes.txt", ".hidden.m4a")

    found = expand_each(AUDIO_CONVERT, {"target": str(tmp_path), "format": "mp3"})

    assert [path.name for path in found.files] == ["a.m4a", "b.wav"]
    assert found.many


def test_a_folder_skips_finished_files_and_maxs_own_outputs(tmp_path):
    _files(tmp_path, "a.mp4", "a_compressed.mp4", "b.mp4", "c.mp4")

    found = expand_each(VIDEO_COMPRESS, {"target": str(tmp_path)})

    assert [path.name for path in found.files] == ["b.mp4", "c.mp4"]
    assert [path.name for path in found.done_already] == ["a.mp4"]
    assert found.total == 3


def test_redo_runs_finished_files_again(tmp_path):
    _files(tmp_path, "a.mp4", "a_compressed.mp4")

    found = expand_each(VIDEO_COMPRESS, {"target": str(tmp_path)}, redo=True)

    assert [path.name for path in found.files] == ["a.mp4"]


def test_the_conversion_that_redid_ten_files(tmp_path):
    """The user's case: 11 M4A files, 10 of them converted already."""
    _files(tmp_path, *(f"song{n}.m4a" for n in range(11)))
    _files(tmp_path, *(f"song{n}.mp3" for n in range(10)))

    found = expand_each(AUDIO_CONVERT, {"target": str(tmp_path / "*.m4a")})

    assert [path.name for path in found.files] == ["song10.m4a"]
    assert len(found.done_already) == 10


def test_files_named_one_by_one_always_run(tmp_path):
    done, fresh = _files(tmp_path, "a.mp4", "b.mp4")
    _files(tmp_path, "a_compressed.mp4")

    found = expand_each(VIDEO_COMPRESS, {"target": [str(done), str(fresh)]})

    assert found.files == [done, fresh]
    assert found.done_already == []


def test_recursive_reaches_subfolders(tmp_path):
    _files(tmp_path, "top.mp4")
    _files(tmp_path / "trip", "deep.mp4")

    flat = expand_each(VIDEO_COMPRESS, {"target": str(tmp_path)})
    deep = expand_each(VIDEO_COMPRESS, {"target": str(tmp_path)}, recursive=True)

    assert [path.name for path in flat.files] == ["top.mp4"]
    assert sorted(path.name for path in deep.files) == ["deep.mp4", "top.mp4"]


def test_one_output_name_cannot_hold_many_results(tmp_path):
    _files(tmp_path, "a.mp4", "b.mp4")

    with pytest.raises(ValidationError, match="'output' names one file"):
        expand_each(VIDEO_COMPRESS, {"target": str(tmp_path), "output": "x.mp4"})


def test_one_output_folder_cannot_hold_many_pdfs_images(tmp_path):
    # Each PDF names its images page1_img1.png...: they'd overwrite each other.
    _files(tmp_path, "a.pdf", "b.pdf")
    rip = get_action("pdf.rip")

    with pytest.raises(ValidationError, match="'output_dir' names one"):
        expand_each(rip, {"target": str(tmp_path), "output_dir": "imgs"})


def test_nothing_found_says_where_it_looked(tmp_path):
    with pytest.raises(ValidationError, match="no matching files"):
        expand_each(VIDEO_COMPRESS, {"target": str(tmp_path / "*.mp4")})


def _fake_runs(monkeypatch, barrier: Any = None) -> list:
    ran: list = []

    def fake(action, args, **kwargs):
        target = Path(args["target"])
        if barrier is not None:
            barrier.wait()
        ran.append(target.name)
        if target.name.startswith("bad"):
            return ActionResult(False, "broken file")
        return ActionResult(True, "ok", [target.with_suffix(".out")])

    monkeypatch.setattr(runner, "run_action", fake)
    return ran


def test_run_each_runs_side_by_side_and_sums_up(tmp_path, monkeypatch):
    _files(tmp_path, "a.mp4", "b.mp4", "bad.mp4", "a2.mp4")
    _files(tmp_path, "a2_compressed.mp4")
    ran = _fake_runs(monkeypatch, threading.Barrier(3, timeout=5))
    heard = []

    result = run_each(
        VIDEO_COMPRESS,
        {"target": str(tmp_path)},
        on_file=lambda path, outcome, error: heard.append((path.name, error)),
    )

    assert sorted(ran) == ["a.mp4", "b.mp4", "bad.mp4"]
    assert not result.ok
    assert result.message == (
        "video compress: 2 of 4 files done, 1 had their result already, 1 failed."
    )
    assert result.details["failed"] == [
        {"file": str(tmp_path / "bad.mp4"), "error": "broken file"}
    ]
    assert len(result.output_files) == 2
    assert sorted(heard) == [("a.mp4", ""), ("b.mp4", ""), ("bad.mp4", "broken file")]


def test_one_plain_file_runs_as_before(tmp_path, monkeypatch):
    (single,) = _files(tmp_path, "a.mp4")
    _files(tmp_path, "a_compressed.mp4")  # named files run even when done
    monkeypatch.setattr(
        runner, "run_action", lambda action, args: ActionResult(True, "one")
    )

    assert run_each(VIDEO_COMPRESS, {"target": str(single)}).message == "one"


def test_everything_done_already_is_not_a_failure(tmp_path, monkeypatch):
    _files(tmp_path, "a.mp4", "a_compressed.mp4")
    ran = _fake_runs(monkeypatch)

    result = run_each(VIDEO_COMPRESS, {"target": str(tmp_path)})

    assert ran == []
    assert result.ok
    assert result.message == "Nothing to do: all 1 files have their result already."


def test_enqueue_each_queues_one_task_per_file(tmp_path):
    from max_cli.core.engines.task_manager import get_task_manager

    _files(tmp_path, "a.mp4", "b.mp4")

    tasks, found = batch.enqueue_each(VIDEO_COMPRESS, {"target": str(tmp_path)})

    assert len(tasks) == 2 and found.total == 2
    queued = [task.payload["args"]["target"] for task in get_task_manager().get_all()]
    assert sorted(Path(target).name for target in queued) == ["a.mp4", "b.mp4"]
