"""`max doctor`: each check, a check that breaks, and the CLI's summary."""

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from max_cli.config import settings
from max_cli.core.engines import updates
from max_cli.core.operations import doctor
from max_cli.interface.cli_doctor import app as doctor_app

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(updates, "current_version", lambda: "1.1.0")
    monkeypatch.setattr(updates, "install_method", lambda: updates.UV)
    monkeypatch.setattr(updates, "fetch_latest", lambda: "1.1.0")


def _by_name(results):
    return {result.name: result for result in results}


def test_every_check_reports():
    results = _by_name(doctor.run())

    assert list(results) == [name for name, _check in doctor.checks()]
    assert results["Max"].state == doctor.OK
    assert "installed with uv" in results["Max"].detail
    assert results["Python"].state == doctor.OK


def test_a_newer_max_is_a_warning_with_the_fix(monkeypatch):
    monkeypatch.setattr(updates, "fetch_latest", lambda: "1.2.0")

    max_check = _by_name(doctor.run())["Max"]

    assert max_check.state == doctor.WARN
    assert "1.2.0 is out" in max_check.detail
    assert max_check.fix == "max update"


def test_missing_ffmpeg_points_to_setup():
    with patch(
        "max_cli.core.engines.ffmpeg_base.FFmpegEngine.__init__",
        side_effect=RuntimeError("FFmpeg is not installed"),
    ):
        ffmpeg = _by_name(doctor.run(online=False))["FFmpeg"]

    assert ffmpeg.state == doctor.WARN
    assert ffmpeg.fix == "max config setup-ffmpeg"


def test_no_ai_points_to_setup(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

    ai = _by_name(doctor.run(online=False))["AI"]

    assert ai.state == doctor.WARN
    assert "max config setup" in ai.fix


def test_unwritable_folders_fail(monkeypatch):
    monkeypatch.setattr(doctor, "_writable", lambda folder: False)

    folders = _by_name(doctor.run(online=False))["Folders"]

    assert folders.state == doctor.FAIL


def test_a_broken_check_doesnt_stop_the_rest(monkeypatch):
    def broken():
        raise OSError("disk on fire")

    names = [name for name, _check in doctor.checks()]
    monkeypatch.setattr(
        doctor,
        "checks",
        lambda online=True: [("Broken", broken), ("Python", doctor._python)],
    )

    results = doctor.run()

    assert [result.name for result in results] == ["Broken", "Python"]
    assert results[0].state == doctor.WARN
    assert "disk on fire" in results[0].detail
    assert "Python" in names


def test_cli_lists_checks_and_fixes(monkeypatch):
    monkeypatch.setattr(updates, "fetch_latest", lambda: "1.2.0")

    result = runner.invoke(doctor_app, [])

    assert result.exit_code == 0, result.output
    assert "Max" in result.output and "FFmpeg" in result.output
    assert "Fix: max update" in result.output


def test_cli_fails_when_a_check_fails(monkeypatch):
    monkeypatch.setattr(doctor, "_writable", lambda folder: False)

    result = runner.invoke(doctor_app, ["--offline"])

    assert "Fix these first: Folders" in result.output
