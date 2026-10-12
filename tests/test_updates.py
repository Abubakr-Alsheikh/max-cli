"""Updates: the PyPI check, how Max was installed, `max update` and the notice.

No network: `fetch_latest` or `requests.get` is mocked. No installer runs:
`run_update`, `hand_off` and `subprocess.Popen` are mocked.
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from max_cli.common.exceptions import NetworkError
from max_cli.config import settings
from max_cli.core.engines import updates
from max_cli.interface import cli_update, update_notice

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})


@pytest.fixture
def version(monkeypatch):
    """This Max reports 1.1.0, whatever the developer's install says."""
    monkeypatch.setattr(updates, "current_version", lambda: "1.1.0")


def _saved(latest: str, hours_ago: float = 1) -> None:
    state = Path.home() / ".max_cli" / updates.STATE_NAME
    state.parent.mkdir(parents=True, exist_ok=True)
    checked = datetime.now() - timedelta(hours=hours_ago)
    state.write_text(
        json.dumps({"latest": latest, "checked_at": checked.isoformat()}),
        encoding="utf-8",
    )


class TestVersions:
    @pytest.mark.parametrize(
        "latest, current, newer",
        [
            ("1.2.0", "1.1.0", True),
            ("1.10.0", "1.9.9", True),
            ("2.0", "1.9.9", True),
            ("1.1.0", "1.1.0", False),
            ("1.1", "1.1.0", False),
            ("1.0.9", "1.1.0", False),
            ("1.2.0rc1", "1.1.0", False),  # pre-releases never count
            (None, "1.1.0", False),
            ("1.2.0", "0+local", False),
        ],
    )
    def test_is_newer(self, latest, current, newer):
        assert updates.is_newer(latest, current) is newer


class TestCheck:
    def test_asks_pypi_and_saves_the_answer(self, version):
        with patch.object(updates, "fetch_latest", return_value="1.2.0") as fetch:
            status = updates.check()

        fetch.assert_called_once()
        assert status.available
        assert updates.cached_status().latest == "1.2.0"
        assert not updates.check_due()

    def test_asks_at_most_once_a_day(self, version):
        _saved("1.1.0", hours_ago=2)

        with patch.object(updates, "fetch_latest") as fetch:
            status = updates.check()

        fetch.assert_not_called()
        assert status.latest == "1.1.0"
        assert not status.available

    def test_a_day_later_it_asks_again(self, version):
        _saved("1.1.0", hours_ago=25)

        with patch.object(updates, "fetch_latest", return_value="1.2.0") as fetch:
            assert updates.check().available

        fetch.assert_called_once()

    def test_a_failed_check_keeps_the_last_answer(self, version):
        _saved("1.2.0", hours_ago=30)

        with patch.object(updates, "fetch_latest", side_effect=NetworkError("offline")):
            status = updates.check()

        assert status.latest == "1.2.0"
        assert status.error == "offline"

    def test_fetch_reads_pypis_version(self):
        reply = MagicMock()
        reply.json.return_value = {"info": {"version": "1.2.0"}}

        with patch("requests.get", return_value=reply) as get:
            assert updates.fetch_latest() == "1.2.0"

        assert get.call_args.args[0] == updates.PYPI_URL

    def test_fetch_failure_is_a_network_error(self):
        import requests

        with patch("requests.get", side_effect=requests.ConnectionError("down")):
            with pytest.raises(NetworkError, match="PyPI"):
                updates.fetch_latest()

    def test_an_unreadable_state_file_means_never_checked(self, version):
        state = Path.home() / ".max_cli" / updates.STATE_NAME
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text("not json", encoding="utf-8")

        assert updates.cached_status().checked_at is None
        assert updates.check_due()


RECEIPT = """[tool]
requirements = [
    { name = "max-cli", extras = ["ocr"], specifier = "==1.0.0" },
    { name = "pytesseract", specifier = ">=0.3" },
]
entrypoints = [
    { name = "max", install-path = "C:/x/max.exe", from = "max-cli" },
]
"""


class TestInstallMethod:
    @pytest.fixture(autouse=True)
    def not_editable(self, monkeypatch):
        monkeypatch.setattr(updates, "_is_editable", lambda: False)

    def test_uv(self, tmp_path):
        (tmp_path / updates.UV_RECEIPT).write_text(RECEIPT, encoding="utf-8")

        assert updates.install_method(tmp_path) == updates.UV

    def test_pipx(self, tmp_path):
        (tmp_path / updates.PIPX_METADATA).write_text("{}", encoding="utf-8")

        assert updates.install_method(tmp_path) == updates.PIPX

    def test_pip(self, tmp_path):
        assert updates.install_method(tmp_path) == updates.PIP

    def test_source(self, tmp_path, monkeypatch):
        monkeypatch.setattr(updates, "_is_editable", lambda: True)

        assert updates.install_method(tmp_path) == updates.SOURCE

    def test_uv_keeps_extras_and_added_packages_but_not_the_pin(self, tmp_path):
        (tmp_path / updates.UV_RECEIPT).write_text(RECEIPT, encoding="utf-8")

        assert updates.uv_requirements(tmp_path) == (
            "max-cli[ocr]",
            ["pytesseract>=0.3"],
        )

    def test_uv_command(self, tmp_path, monkeypatch):
        (tmp_path / updates.UV_RECEIPT).write_text(RECEIPT, encoding="utf-8")
        monkeypatch.setattr(sys, "prefix", str(tmp_path))

        command = updates.update_command(updates.UV)

        assert command[1:] == [
            "tool",
            "install",
            "--upgrade",
            "max-cli[ocr]",
            "--with",
            "pytesseract>=0.3",
        ]

    def test_other_commands(self):
        assert updates.update_command(updates.PIPX)[1:] == ["upgrade", "max-cli"]
        assert updates.update_command(updates.PIP) == [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "max-cli",
        ]
        assert updates.update_command(updates.SOURCE) is None


class TestHandOff:
    def test_script_waits_then_updates(self):
        script = updates.hand_off_script(
            [r"C:\Program Files\uv's\uv.exe", "tool", "upgrade", "max-cli"], [11, 22]
        )

        assert "Wait-Process -Id 11,22" in script
        assert r"& 'C:\Program Files\uv''s\uv.exe' 'tool' 'upgrade' 'max-cli'" in script
        assert script.index("Wait-Process") < script.index("& '")
        assert "Read-Host" in script

    def test_opens_its_own_window(self):
        with patch("subprocess.Popen") as popen:
            updates.hand_off(["uv", "tool", "upgrade", "max-cli"])

        arguments = popen.call_args.args[0]
        assert arguments[-2] == "-Command"
        flags = popen.call_args.kwargs["creationflags"]
        assert flags == getattr(subprocess, "CREATE_NEW_CONSOLE", 0)


class TestUpdateCommand:
    @pytest.fixture(autouse=True)
    def uv_install(self, monkeypatch, version):
        monkeypatch.setattr(updates, "install_method", lambda: updates.UV)
        monkeypatch.setattr(
            updates, "update_command", lambda method: ["uv", "tool", "upgrade"]
        )

    def test_says_when_max_is_newest(self):
        with patch.object(updates, "fetch_latest", return_value="1.1.0"):
            result = runner.invoke(cli_update.app, [])

        assert result.exit_code == 0, result.output
        assert "Max 1.1.0 is the newest version" in result.output

    def test_check_only_reports(self):
        with (
            patch.object(updates, "fetch_latest", return_value="1.2.0"),
            patch.object(updates, "run_update") as run,
            patch.object(updates, "hand_off") as hand_off,
        ):
            result = runner.invoke(cli_update.app, ["--check"])

        assert "Max 1.2.0 is out" in result.output
        run.assert_not_called()
        hand_off.assert_not_called()

    def test_windows_hands_off_to_a_window(self, monkeypatch):
        monkeypatch.setattr(updates, "needs_hand_off", lambda: True)

        with (
            patch.object(updates, "fetch_latest", return_value="1.2.0"),
            patch.object(updates, "hand_off") as hand_off,
        ):
            result = runner.invoke(cli_update.app, ["--yes"])

        assert result.exit_code == 0, result.output
        hand_off.assert_called_once_with(["uv", "tool", "upgrade"])
        assert "update window opened" in result.output

    def test_elsewhere_it_updates_in_place(self, monkeypatch):
        monkeypatch.setattr(updates, "needs_hand_off", lambda: False)

        with (
            patch.object(updates, "fetch_latest", return_value="1.2.0"),
            patch.object(updates, "run_update", return_value=0) as run,
        ):
            result = runner.invoke(cli_update.app, [], input="y\n")

        run.assert_called_once()
        assert "Max is up to date" in result.output

    def test_no_means_no(self, monkeypatch):
        monkeypatch.setattr(updates, "needs_hand_off", lambda: False)

        with (
            patch.object(updates, "fetch_latest", return_value="1.2.0"),
            patch.object(updates, "run_update") as run,
        ):
            runner.invoke(cli_update.app, [], input="n\n")

        run.assert_not_called()

    def test_source_installs_get_the_git_hint(self, monkeypatch):
        monkeypatch.setattr(updates, "update_command", lambda method: None)

        with patch.object(updates, "fetch_latest", return_value="1.2.0"):
            result = runner.invoke(cli_update.app, ["--yes"])

        assert "git pull" in result.output

    def test_offline_exits_1(self):
        with patch.object(
            updates, "fetch_latest", side_effect=NetworkError("Couldn't ask PyPI")
        ):
            result = runner.invoke(cli_update.app, [])

        assert result.exit_code == 1
        assert "Couldn't ask PyPI" in result.output


class TestNotice:
    @pytest.fixture(autouse=True)
    def checks_on(self, monkeypatch):
        monkeypatch.setattr(settings, "UPDATE_CHECK", True)
        monkeypatch.setattr(update_notice, "_is_terminal", lambda: True)

    def test_quiet_for_scripts_the_dashboard_and_update(self, monkeypatch):
        assert update_notice.start(["video", "compress", "a.mp4"]) is not None
        assert update_notice.start([]) is None  # a bare max: the dashboard
        assert update_notice.start(["update"]) is None
        assert update_notice.start(["dashboard"]) is None
        assert update_notice.start(["--version"]) is None
        monkeypatch.setattr(update_notice, "_is_terminal", lambda: False)
        assert update_notice.start(["video"]) is None
        monkeypatch.setattr(settings, "UPDATE_CHECK", False)
        assert update_notice.start(["video"]) is None

    def test_no_network_when_a_check_isnt_due(self, version):
        _saved("1.1.0")

        with patch.object(updates, "fetch_latest") as fetch:
            thread = update_notice.start(["video"])

        assert thread is not None and not thread.is_alive()
        fetch.assert_not_called()

    def test_prints_one_line_when_newer(self, version, monkeypatch):
        from max_cli.common import logger

        _saved("1.2.0")
        printed = MagicMock()
        monkeypatch.setattr(logger.console, "print", printed)

        update_notice.finish(update_notice.start(["video"]))

        (line,) = printed.call_args.args
        assert "Max 1.2.0 is out (you have 1.1.0)" in line
        assert "max update" in line

    def test_silent_when_current(self, version, monkeypatch):
        from max_cli.common import logger

        _saved("1.1.0")
        printed = MagicMock()
        monkeypatch.setattr(logger.console, "print", printed)

        update_notice.finish(update_notice.start(["video"]))

        printed.assert_not_called()


def test_python_dash_m_runs_max():
    result = subprocess.run(
        [sys.executable, "-m", "max_cli", "--version"],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("max ")
