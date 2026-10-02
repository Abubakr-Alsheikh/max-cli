"""common/settings_file.py: read and update ~/.max_config.env."""

import pytest

from max_cli.common.settings_file import (
    read_settings_file,
    settings_file_path,
    update_settings_file,
)


def test_path_follows_the_home_folder(isolated_home):
    assert settings_file_path() == isolated_home / ".max_config.env"


def test_no_file_reads_as_empty():
    assert read_settings_file() == {}


def test_update_changes_only_the_given_keys_and_keeps_comments(tmp_path):
    path = tmp_path / "settings.env"
    path.write_text(
        "# my notes\nGRAB_QUALITY=h\nAI_MODEL=gpt-5-nano\n\nVERBOSE=true\n",
        encoding="utf-8",
    )

    update_settings_file({"GRAB_QUALITY": "m", "MAX_WORKERS": "8"}, path)

    assert path.read_text(encoding="utf-8").splitlines() == [
        "# my notes",
        "GRAB_QUALITY=m",
        "AI_MODEL=gpt-5-nano",
        "",
        "VERBOSE=true",
        "MAX_WORKERS=8",
    ]


def test_none_removes_a_key_and_duplicates_collapse(tmp_path):
    path = tmp_path / "settings.env"
    path.write_text(
        "OPENAI_API_KEY=a\nGRAB_QUALITY=h\nGRAB_QUALITY=x\n", encoding="utf-8"
    )

    update_settings_file({"OPENAI_API_KEY": None, "GRAB_QUALITY": "s"}, path)

    assert read_settings_file(path) == {"GRAB_QUALITY": "s"}


def test_values_that_need_quotes_read_back_unchanged(tmp_path):
    path = tmp_path / "settings.env"
    tricky = {
        "GRAB_DEFAULT_PATH": "D:\\Videos # mine",
        "AI_MODEL": ' spaced "name" ',
        "OLLAMA_MODEL": "plain",
    }

    update_settings_file(tricky, path)

    assert read_settings_file(path) == tricky


def test_quoted_values_load_into_settings(tmp_path, monkeypatch):
    """The .env parser pydantic uses must read what we write."""
    from max_cli.config import Settings

    path = tmp_path / "settings.env"
    update_settings_file({"GRAB_DEFAULT_PATH": "D:\\My Videos # 2026"}, path)
    monkeypatch.chdir(tmp_path)  # keep the repo's own .env out of it

    loaded = Settings(_env_file=str(path))  # type: ignore[call-arg]  # pydantic-settings option

    assert str(loaded.GRAB_DEFAULT_PATH) == "D:\\My Videos # 2026"


def test_a_bad_setting_value_names_the_setting(monkeypatch):
    from max_cli.common.exceptions import ConfigurationError
    from max_cli.config import load_settings

    monkeypatch.setenv("DOWNLOAD_TIMEOUT", "5")

    with pytest.raises(ConfigurationError, match="DOWNLOAD_TIMEOUT"):
        load_settings()


def test_a_big_timeout_or_retry_count_still_loads(monkeypatch):
    """Both settings existed without an upper limit before Max read them."""
    from max_cli.config import load_settings

    monkeypatch.setenv("DOWNLOAD_TIMEOUT", "900")
    monkeypatch.setenv("MAX_RETRIES", "30")

    loaded = load_settings()

    assert (loaded.DOWNLOAD_TIMEOUT, loaded.MAX_RETRIES) == (900, 30)
