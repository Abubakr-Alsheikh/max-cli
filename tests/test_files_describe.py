"""files.describe: what a file or a folder's own files are, for the Files page."""

import os
import time

import pytest

from max_cli.common.exceptions import ResourceNotFoundError
from max_cli.core.operations import files


def test_a_folder_counts_its_own_files_by_kind(tmp_path):
    for name, size in (("a.jpg", 10), ("b.png", 30), ("scan.pdf", 50), ("x.bin", 5)):
        (tmp_path / name).write_bytes(b"x" * size)
    (tmp_path / "inner").mkdir()
    (tmp_path / "inner" / "deep.mp4").write_bytes(b"x" * 999)

    facts = files.describe(tmp_path)

    assert facts.is_folder
    assert (facts.file_count, facts.folder_count, facts.size_bytes) == (4, 1, 95)
    assert facts.kinds == {"image": 2, "pdf": 1, "other": 1}
    assert (facts.biggest, facts.biggest_bytes) == (tmp_path / "scan.pdf", 50)
    assert facts.note == files.ORGANIZE_NOTE


def test_a_folder_with_only_subfolders(tmp_path):
    (tmp_path / "inner").mkdir()

    facts = files.describe(tmp_path)

    assert (facts.file_count, facts.folder_count) == (0, 1)
    assert facts.biggest is None
    assert facts.note == files.EMPTY_FOLDER_NOTE


def test_a_file_gives_its_kind_size_and_date(tmp_path):
    clip = tmp_path / "Clip.MP4"
    clip.write_bytes(b"x" * 7)
    stamp = time.mktime((2024, 5, 1, 9, 30, 0, 0, 0, -1))
    os.utime(clip, (stamp, stamp))

    facts = files.describe(clip)

    assert (facts.kind, facts.size_bytes, facts.is_folder) == ("video", 7, False)
    assert facts.modified is not None
    assert facts.modified.strftime("%Y-%m-%d %H:%M") == "2024-05-01 09:30"


def test_a_missing_path_is_an_error(tmp_path):
    with pytest.raises(ResourceNotFoundError):
        files.describe(tmp_path / "gone")
