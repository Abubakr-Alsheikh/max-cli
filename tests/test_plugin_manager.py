"""Plugin discovery locations (hardening 1.7, decision D2)."""

import json
from pathlib import Path

import pytest

from max_cli.plugins.manager import PluginManager

EXAMPLE_PLUGIN = (
    Path(__file__).resolve().parent.parent / "examples" / "plugins" / "hello_world.py"
)


@pytest.fixture
def fake_home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    return home


def _install_example_plugin(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "hello_world.py").write_text(
        EXAMPLE_PLUGIN.read_text(encoding="utf-8"), encoding="utf-8"
    )


def _discovered_names(manager: PluginManager) -> list:
    return [plugin_class.__name__ for plugin_class in manager.discover_plugins()]


def test_plugins_folder_in_current_directory_is_not_executed(
    fake_home, tmp_path, monkeypatch
):
    cloned_repo = tmp_path / "cloned_repo"
    (cloned_repo / "plugins").mkdir(parents=True)
    marker = tmp_path / "executed.txt"
    (cloned_repo / "plugins" / "untrusted.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(cloned_repo)

    PluginManager().discover_plugins()

    assert not marker.exists()


def test_home_plugins_folder_is_discovered(fake_home):
    _install_example_plugin(fake_home / ".max_cli" / "plugins")

    assert "HelloWorldPlugin" in _discovered_names(PluginManager())


def test_extra_plugin_dirs_come_from_user_config(fake_home, tmp_path):
    extra_dir = tmp_path / "my_plugins"
    _install_example_plugin(extra_dir)
    config_dir = fake_home / ".max_cli"
    config_dir.mkdir()
    (config_dir / "plugins.json").write_text(
        json.dumps({"enabled": {}, "plugin_dirs": [str(extra_dir)]}),
        encoding="utf-8",
    )

    assert "HelloWorldPlugin" in _discovered_names(PluginManager())


def test_saving_config_keeps_plugin_dirs(fake_home, tmp_path):
    config_dir = fake_home / ".max_cli"
    config_dir.mkdir()
    config_file = config_dir / "plugins.json"
    config_file.write_text(
        json.dumps({"enabled": {}, "plugin_dirs": [str(tmp_path / "extra")]}),
        encoding="utf-8",
    )

    PluginManager()._save_config()

    saved = json.loads(config_file.read_text(encoding="utf-8"))
    assert saved["plugin_dirs"] == [str(tmp_path / "extra")]
