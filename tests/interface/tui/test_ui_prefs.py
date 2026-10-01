"""ui_prefs: small dashboard choices that survive a restart."""

from unittest.mock import patch

from max_cli.interface.tui import ui_prefs


def test_a_locked_prefs_file_is_retried_then_skipped():
    """Windows refused the replace while another process held the file, and
    the PermissionError closed the dashboard on a page change."""
    with patch.object(ui_prefs, "atomic_write_json", side_effect=PermissionError):
        ui_prefs.save_pref("last_page", "files")  # must not raise

    assert ui_prefs.load_prefs() == {}


def test_a_brief_lock_still_saves():
    real_write = ui_prefs.atomic_write_json
    calls = []

    def locked_once(path, data):
        calls.append(path)
        if len(calls) == 1:
            raise PermissionError
        real_write(path, data)

    with patch.object(ui_prefs, "atomic_write_json", side_effect=locked_once):
        ui_prefs.save_pref("last_page", "files")

    assert ui_prefs.load_prefs() == {"last_page": "files"}
    assert len(calls) == 2
