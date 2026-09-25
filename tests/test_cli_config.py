"""CliRunner tests for `max config` (src/max_cli/interface/cli_config.py).

The autouse fixture points every GLOBAL_CONFIG_PATH at tmp_path and moves the
working directory there, so no test reads or writes ~/.max_config.env or a
real .env file.

Every command sits directly under `max config` (`max config show`), as the
README documents. It used to need a nested form, `max config show show`.
"""

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from max_cli.common.exceptions import MaxError
from max_cli.interface.cli_config import app as config_app
from max_cli.interface.config import grab as grab_wizard_module
from max_cli.interface.config import manage as manage_module
from max_cli.interface.config import setup as wizard_module

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})

RESOLVER_CLASS_PATH = "max_cli.common.ffmpeg_resolver.FFmpegResolver"
RESOLVE_FFMPEG_PATH = "max_cli.common.ffmpeg_resolver.resolve_ffmpeg"

# The shared Rich console is built at import time, so it may still emit ANSI
# styles inside CliRunner. Strip them before substring checks.
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

MANAGE_GROUPS = ["show", "save", "reset", "validate", "export", "import"]


def _plain(result) -> str:
    return ANSI_ESCAPE.sub("", result.output)


@pytest.fixture(autouse=True)
def isolated_config(tmp_path: Path, monkeypatch) -> Path:
    """Redirect the global config file and the cwd-relative .env into tmp_path."""
    global_config = tmp_path / "home" / ".max_config.env"
    global_config.parent.mkdir()
    for module in (manage_module, wizard_module, grab_wizard_module):
        monkeypatch.setattr(module, "GLOBAL_CONFIG_PATH", global_config)
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    monkeypatch.chdir(work_dir)
    return global_config


def test_group_help_lists_commands() -> None:
    result = runner.invoke(config_app, ["--help"])

    assert result.exit_code == 0
    for command in ["setup", "grab", "setup-ffmpeg", *MANAGE_GROUPS]:
        assert command in result.stdout


@pytest.mark.parametrize(
    "args",
    [["setup", "--help"], ["grab", "--help"], ["setup-ffmpeg", "--help"]]
    + [[group, "--help"] for group in MANAGE_GROUPS],
)
def test_subgroup_help(args) -> None:
    result = runner.invoke(config_app, args)

    assert result.exit_code == 0, result.output
    assert "Usage" in result.stdout


@pytest.mark.parametrize("command", ["show", "validate"])
def test_documented_single_word_command_runs(command: str) -> None:
    result = runner.invoke(config_app, [command])

    assert result.exit_code == 0, result.output


class TestShow:
    def test_reports_missing_global_config(self) -> None:
        result = runner.invoke(config_app, ["show"])

        assert result.exit_code == 0, result.output
        output = _plain(result)
        assert "Global Config Missing" in output
        assert "Active Configuration:" in output

    def test_reports_global_and_local_config(self, isolated_config: Path) -> None:
        isolated_config.write_text("AI_MODEL=x\n", encoding="utf-8")
        Path(".env").write_text("AI_MODEL=y\n", encoding="utf-8")

        result = runner.invoke(config_app, ["show"])

        assert result.exit_code == 0, result.output
        output = _plain(result)
        assert "Global Config Found:" in output
        assert "Local Override Found:" in output


class TestSave:
    def test_copies_local_env_to_global(self, isolated_config: Path) -> None:
        Path(".env").write_text("AI_MODEL=gpt-4o\n", encoding="utf-8")

        result = runner.invoke(config_app, ["save"])

        assert result.exit_code == 0, result.output
        assert isolated_config.read_text(encoding="utf-8") == "AI_MODEL=gpt-4o\n"
        assert "saved as Global Configuration" in _plain(result)

    def test_declined_overwrite_keeps_global(self, isolated_config: Path) -> None:
        isolated_config.write_text("OLD=1\n", encoding="utf-8")
        Path(".env").write_text("NEW=1\n", encoding="utf-8")
        with patch.object(manage_module.Confirm, "ask", return_value=False):
            result = runner.invoke(config_app, ["save"])

        assert result.exit_code == 1
        assert isolated_config.read_text(encoding="utf-8") == "OLD=1\n"
        assert "Aborted." in _plain(result)

    def test_force_overwrites_global(self, isolated_config: Path) -> None:
        isolated_config.write_text("OLD=1\n", encoding="utf-8")
        Path(".env").write_text("NEW=1\n", encoding="utf-8")

        result = runner.invoke(config_app, ["save", "--force"])

        assert result.exit_code == 0, result.output
        assert isolated_config.read_text(encoding="utf-8") == "NEW=1\n"

    def test_missing_local_env_exits_1(self) -> None:
        result = runner.invoke(config_app, ["save"])

        assert result.exit_code == 1
        assert "No .env file found" in _plain(result)


class TestReset:
    def test_confirmed_reset_deletes_both_files(self, isolated_config: Path) -> None:
        isolated_config.write_text("A=1\n", encoding="utf-8")
        Path(".env").write_text("B=1\n", encoding="utf-8")
        with patch.object(manage_module.Confirm, "ask", return_value=True):
            result = runner.invoke(config_app, ["reset"])

        assert result.exit_code == 0, result.output
        assert not isolated_config.exists()
        assert not Path(".env").exists()

    def test_local_only_leaves_global(self, isolated_config: Path) -> None:
        isolated_config.write_text("A=1\n", encoding="utf-8")
        Path(".env").write_text("B=1\n", encoding="utf-8")
        with patch.object(manage_module.Confirm, "ask", return_value=True):
            result = runner.invoke(config_app, ["reset", "--local"])

        assert result.exit_code == 0, result.output
        assert isolated_config.exists()
        assert not Path(".env").exists()


class TestValidate:
    def test_prints_validation_table(self) -> None:
        result = runner.invoke(config_app, ["validate"])

        assert result.exit_code == 0, result.output
        output = _plain(result)
        assert "Configuration Validation" in output
        assert output.count("MAX_WORKERS") == 1  # the row used to appear twice


class TestExportImport:
    def test_export_leaves_out_api_key_by_default(self, tmp_path: Path) -> None:
        """The key used to land in max-config.json in plain text."""
        output = tmp_path / "exported.json"
        with patch.object(manage_module.settings, "OPENAI_API_KEY", "sk-secret"):
            result = runner.invoke(config_app, ["export", "-o", str(output)])

        assert result.exit_code == 0, result.output
        assert "sk-secret" not in output.read_text(encoding="utf-8")

    def test_export_include_secrets_writes_key_and_warns(self, tmp_path: Path) -> None:
        output = tmp_path / "exported.json"
        with patch.object(manage_module.settings, "OPENAI_API_KEY", "sk-secret"):
            result = runner.invoke(
                config_app, ["export", "-o", str(output), "--include-secrets"]
            )

        assert result.exit_code == 0, result.output
        assert json.loads(output.read_text(encoding="utf-8"))["OPENAI_API_KEY"] == (
            "sk-secret"
        )
        assert "API key" in _plain(result)

    def test_export_with_defaults(self, tmp_path: Path) -> None:
        output = tmp_path / "exported.json"

        result = runner.invoke(
            config_app, ["export", "-o", str(output), "--include-defaults"]
        )

        assert result.exit_code == 0, result.output
        exported = json.loads(output.read_text(encoding="utf-8"))
        assert "MAX_WORKERS" in exported
        assert "APP_NAME" in exported
        assert "Config exported to" in _plain(result)

    def test_import_to_local_env(self, tmp_path: Path) -> None:
        source = tmp_path / "in.json"
        source.write_text(
            json.dumps({"AI_MODEL": "gpt-4o", "SKIPPED": None}), encoding="utf-8"
        )

        result = runner.invoke(config_app, ["import", str(source), "--local"])

        assert result.exit_code == 0, result.output
        env_text = Path(".env").read_text(encoding="utf-8")
        assert "AI_MODEL=gpt-4o" in env_text
        assert "SKIPPED" not in env_text

    def test_import_to_global(self, tmp_path: Path, isolated_config: Path) -> None:
        source = tmp_path / "in.json"
        source.write_text(json.dumps({"AI_MODEL": "gpt-4o"}), encoding="utf-8")

        result = runner.invoke(config_app, ["import", str(source)])

        assert result.exit_code == 0, result.output
        assert "AI_MODEL=gpt-4o" in isolated_config.read_text(encoding="utf-8")

    def test_import_invalid_json_exits_1(self, tmp_path: Path) -> None:
        source = tmp_path / "bad.json"
        source.write_text("{not json", encoding="utf-8")

        result = runner.invoke(config_app, ["import", str(source)])

        assert result.exit_code == 1
        assert "Invalid JSON" in _plain(result)

    def test_import_missing_file_exits_1(self, tmp_path: Path) -> None:
        result = runner.invoke(
            config_app, ["import", str(tmp_path / "none.json")]
        )

        assert result.exit_code == 1
        assert "File not found" in _plain(result)


class TestWizards:
    def test_setup_openai_writes_global_config(self, isolated_config: Path) -> None:
        with patch.object(
            wizard_module.Prompt, "ask", side_effect=["openai", "gpt-4o", "dall-e-3"]
        ):
            result = runner.invoke(config_app, ["setup"])

        assert result.exit_code == 0, result.output
        config_text = isolated_config.read_text(encoding="utf-8")
        assert "AI_MODEL=gpt-4o" in config_text
        assert "AI_IMAGE_MODEL=dall-e-3" in config_text
        assert "OLLAMA_ENABLED=false" in config_text
        assert "Configuration updated successfully!" in _plain(result)

    def test_grab_replaces_existing_grab_keys(
        self, isolated_config: Path, tmp_path: Path
    ) -> None:
        isolated_config.write_text("AI_MODEL=keep\nGRAB_QUALITY=s\n", encoding="utf-8")
        with (
            patch.object(
                grab_wizard_module.Prompt,
                "ask",
                side_effect=["x", "audio", str(tmp_path)],
            ),
            patch.object(
                grab_wizard_module.Confirm, "ask", side_effect=[True, False, True]
            ),
        ):
            result = runner.invoke(config_app, ["grab"])

        assert result.exit_code == 0, result.output
        lines = isolated_config.read_text(encoding="utf-8").splitlines()
        assert "AI_MODEL=keep" in lines
        assert "GRAB_QUALITY=s" not in lines
        assert "GRAB_QUALITY=x" in lines
        assert "GRAB_DEFAULT_TYPE=audio" in lines
        assert "GRAB_INCLUDE_METADATA=False" in lines
        assert "Downloader settings saved!" in _plain(result)


class TestSetupFfmpeg:
    def test_reports_resolved_path(self, tmp_path: Path) -> None:
        resolver = MagicMock()
        resolver.local_path.exists.return_value = False
        binary = tmp_path / "ffmpeg.exe"
        with (
            patch(RESOLVER_CLASS_PATH, return_value=resolver),
            patch(RESOLVE_FFMPEG_PATH, return_value=binary) as resolve_mock,
        ):
            result = runner.invoke(config_app, ["setup-ffmpeg"])

        assert result.exit_code == 0, result.output
        assert resolve_mock.call_args.kwargs["auto_download"] is True
        assert "FFmpeg ready at:" in _plain(result)

    def test_force_removes_existing_binary(self, tmp_path: Path) -> None:
        resolver = MagicMock()
        resolver.local_path.exists.return_value = True
        with (
            patch(RESOLVER_CLASS_PATH, return_value=resolver),
            patch(RESOLVE_FFMPEG_PATH, return_value=tmp_path / "ffmpeg.exe"),
        ):
            result = runner.invoke(config_app, ["setup-ffmpeg", "--force"])

        assert result.exit_code == 0, result.output
        resolver.local_path.unlink.assert_called_once_with()
        assert "Removed existing FFmpeg binary." in _plain(result)

    def test_resolver_error_exits_1(self) -> None:
        resolver = MagicMock()
        resolver.local_path.exists.return_value = False
        with (
            patch(RESOLVER_CLASS_PATH, return_value=resolver),
            patch(RESOLVE_FFMPEG_PATH, side_effect=MaxError("download blocked")),
        ):
            result = runner.invoke(config_app, ["setup-ffmpeg"])

        assert result.exit_code == 1
        assert not isinstance(result.exception, MaxError)
        assert "download blocked" in _plain(result)
