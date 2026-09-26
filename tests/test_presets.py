"""Shared presets and the TUI parameter mapping that uses them (Phase 4)."""

from pathlib import Path

import pytest

from max_cli.core import presets
from max_cli.core.engines.pdf_engine import find_pdfs
from max_cli.core.engines.video_engine import resolve_concat_inputs
from max_cli.interface.tui.command_executor import CommandExecutor
from max_cli.interface.tui.command_registry import CommandRegistry


def _map(category, command, params):
    schema = CommandRegistry.get_command(category, command)
    return CommandExecutor()._map_engine_params(category, command, params, schema)


class TestPresetHelpers:
    @pytest.mark.parametrize(
        "level, crf", [("high", 23), ("BALANCED", 28), ("max", 35), ("bogus", 28)]
    )
    def test_crf_for_level(self, level, crf):
        assert presets.crf_for_level(level) == crf

    def test_bitrate_uses_first_letter_and_falls_back(self):
        table = presets.VIDEO_TO_AUDIO_BITRATES
        assert presets.bitrate_for_quality(table, "xtreme", "h") == "320k"
        assert presets.bitrate_for_quality(table, "?", "h") == "192k"

    def test_sibling_path(self):
        clip = Path("videos/clip.mov")
        assert presets.sibling_path(clip, "_compressed", "mp4") == Path(
            "videos/clip_compressed.mp4"
        )
        assert presets.sibling_path(clip, "_cut") == Path("videos/clip_cut.mov")


class TestEngineHelpers:
    def test_concat_txt_list(self, tmp_path):
        listing = tmp_path / "list.txt"
        listing.write_text("file 'one.mp4'\ntwo.mp4\n\n", encoding="utf-8")
        assert resolve_concat_inputs(listing) == [Path("one.mp4"), Path("two.mp4")]

    def test_concat_rejects_other_targets(self, tmp_path):
        with pytest.raises(ValueError):
            resolve_concat_inputs(tmp_path / "clip.mp4")

    def test_find_pdfs_skips_hidden_and_temp(self, tmp_path):
        for name in [".hidden.pdf", "_tmp.pdf", "a.PDF"]:
            (tmp_path / name).write_bytes(b"")
        assert [p.name for p in find_pdfs(tmp_path)] == ["a.PDF"]


def test_dashboard_organizes_music_by_artist_and_album():
    """Maintainer's choice: the TUI default stays "artist-album"."""
    schema = CommandRegistry.get_command("audio", "organize")
    pattern = next(f for f in schema["fields"] if f["name"] == "pattern")
    assert pattern["default"] == "artist-album"


def test_tui_shred_passes_the_path_the_engine_expects(tmp_path):
    """The dashboard sent `target=`, which secure_delete doesn't accept."""
    params = _map("files", "shred", {"target": tmp_path / "secret.txt", "passes": 3})
    assert params == {"path": tmp_path / "secret.txt", "passes": 3}
