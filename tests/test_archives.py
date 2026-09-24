"""Safe tar extraction (hardening 1.9 and 1.12)."""

import io
import tarfile
from pathlib import Path

import pytest

from max_cli.common.archives import UnsafeArchiveError, safe_extract_tar


def _tar_with(entries) -> tarfile.TarFile:
    """Build an in-memory tar. entries: (name, bytes | None, symlink target | None)."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, payload, link_target in entries:
            info = tarfile.TarInfo(name=name)
            if link_target is not None:
                info.type = tarfile.SYMTYPE
                info.linkname = link_target
                archive.addfile(info)
            else:
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
    buffer.seek(0)
    return tarfile.open(fileobj=buffer, mode="r")


def test_extracts_regular_members(tmp_path):
    dest = tmp_path / "out"
    dest.mkdir()
    archive = _tar_with([("pkg/bin/tool", b"binary", None)])

    safe_extract_tar(archive, dest)

    assert (dest / "pkg" / "bin" / "tool").read_bytes() == b"binary"


@pytest.mark.parametrize("evil_name", ["../escaped.txt", "a/../../escaped.txt"])
def test_rejects_parent_traversal(tmp_path, evil_name):
    dest = tmp_path / "out"
    dest.mkdir()
    archive = _tar_with([(evil_name, b"x", None)])

    with pytest.raises(UnsafeArchiveError):
        safe_extract_tar(archive, dest)

    assert not (tmp_path / "escaped.txt").exists()


def test_rejects_absolute_member(tmp_path):
    dest = tmp_path / "out"
    dest.mkdir()
    outside = tmp_path / "abs.txt"
    archive = _tar_with([(str(outside), b"x", None)])

    with pytest.raises(UnsafeArchiveError):
        safe_extract_tar(archive, dest)

    assert not outside.exists()


def test_rejects_symlink_pointing_outside(tmp_path):
    dest = tmp_path / "out"
    dest.mkdir()
    archive = _tar_with([("link", None, "../../etc")])

    with pytest.raises(UnsafeArchiveError):
        safe_extract_tar(archive, dest)


def test_nothing_is_extracted_when_any_member_is_unsafe(tmp_path):
    dest = tmp_path / "out"
    dest.mkdir()
    archive = _tar_with([("good.txt", b"ok", None), ("../bad.txt", b"x", None)])

    with pytest.raises(UnsafeArchiveError):
        safe_extract_tar(archive, dest)

    assert list(dest.iterdir()) == []


def test_extracts_only_selected_members(tmp_path):
    dest = tmp_path / "out"
    dest.mkdir()
    archive = _tar_with([("keep.txt", b"k", None), ("skip.txt", b"s", None)])
    selected = [archive.getmember("keep.txt")]

    safe_extract_tar(archive, dest, members=selected)

    assert sorted(p.name for p in dest.iterdir()) == ["keep.txt"]


def test_symlink_inside_destination_is_allowed(tmp_path):
    dest = tmp_path / "out"
    dest.mkdir()
    archive = _tar_with(
        [("lib/libx.so.1", b"so", None), ("lib/libx.so", None, "libx.so.1")]
    )

    safe_extract_tar(archive, dest)

    assert (dest / "lib" / "libx.so.1").exists()


def test_fallback_without_stdlib_data_filter(tmp_path, monkeypatch):
    """Older Python 3.9 builds lack tarfile.data_filter; validation still applies."""
    monkeypatch.delattr(tarfile, "data_filter", raising=False)
    dest = tmp_path / "out"
    dest.mkdir()

    safe_extract_tar(_tar_with([("ok.txt", b"ok", None)]), dest)
    with pytest.raises(UnsafeArchiveError):
        safe_extract_tar(_tar_with([("../bad.txt", b"x", None)]), dest)

    assert (dest / "ok.txt").read_bytes() == b"ok"
    assert not (tmp_path / "bad.txt").exists()


def test_accepts_path_objects(tmp_path):
    dest = Path(tmp_path) / "out"
    dest.mkdir()

    safe_extract_tar(_tar_with([("a.txt", b"a", None)]), dest)

    assert (dest / "a.txt").exists()
