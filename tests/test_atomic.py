"""Atomic state-file writes (hardening Phase 2)."""

import json
from pathlib import Path

import pytest

from max_cli.common.atomic import atomic_write_json, atomic_write_text


def _leftovers(folder: Path, keep: Path) -> list:
    return [p.name for p in folder.iterdir() if p != keep]


def test_writes_text_with_utf8(tmp_path):
    target = tmp_path / "state.txt"

    atomic_write_text(target, "héllo ✓ 日本")

    assert target.read_text(encoding="utf-8") == "héllo ✓ 日本"
    assert _leftovers(tmp_path, target) == []


def test_writes_json(tmp_path):
    target = tmp_path / "state.json"

    atomic_write_json(target, {"items": [1, 2], "name": "✓"})

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "items": [1, 2],
        "name": "✓",
    }


def test_json_default_serializer_is_used(tmp_path):
    target = tmp_path / "state.json"

    atomic_write_json(target, {"when": Path("a/b")}, default=str)

    assert json.loads(target.read_text(encoding="utf-8"))["when"] == str(Path("a/b"))


def test_creates_missing_parent_folders(tmp_path):
    target = tmp_path / "nested" / "deeper" / "state.json"

    atomic_write_json(target, [])

    assert json.loads(target.read_text(encoding="utf-8")) == []


def test_failed_replace_keeps_original_and_cleans_temp(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    target.write_text('{"version": 1}', encoding="utf-8")

    def crash(self, destination):
        raise OSError("disk full at the worst moment")

    monkeypatch.setattr(Path, "replace", crash)

    with pytest.raises(OSError):
        atomic_write_json(target, {"version": 2})

    assert json.loads(target.read_text(encoding="utf-8")) == {"version": 1}
    assert _leftovers(tmp_path, target) == []


def test_unserializable_data_never_touches_the_file(tmp_path):
    target = tmp_path / "state.json"
    target.write_text('{"version": 1}', encoding="utf-8")

    with pytest.raises(TypeError):
        atomic_write_json(target, {"bad": object()})

    assert json.loads(target.read_text(encoding="utf-8")) == {"version": 1}
    assert _leftovers(tmp_path, target) == []


def test_overwrites_existing_file(tmp_path):
    target = tmp_path / "state.txt"
    target.write_text("old", encoding="utf-8")

    atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "new"
