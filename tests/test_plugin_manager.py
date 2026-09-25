"""Plugin discovery locations (hardening 1.7, decision D2) and manager lifecycle."""

import json
import sys
from pathlib import Path
from typing import Optional

import pytest
import typer

from max_cli.plugins.base import PluginContext, PluginValidationError
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


@pytest.fixture(autouse=True)
def forget_plugin_modules():
    """Drop modules the manager imported so tests cannot see each other's plugins."""
    yield
    for module_name in [m for m in sys.modules if m.startswith("max_cli_plugins.")]:
        del sys.modules[module_name]


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


# --- Discovery, loading and lifecycle ----------------------------------------
# Plugin sources reach CLIPlugin through the `base` module, so the module
# namespace holds only the concrete class (see the xfail at the end).

PLUGIN_TEMPLATE = """
from max_cli.plugins import base


class {class_name}(base.CLIPlugin):
    def __init__(self):
        super().__init__(name={name!r}, version="1.2.3", description="demo",
                         author="me", tags=["t"])
        self.events = []

    @property
    def priority(self):
        return {priority}

    def validate(self):
        return {valid!r}, {error!r}

    def on_load(self, context):
        self.events.append(("load", context.plugin_dir))

    def on_unload(self):
        self.events.append(("unload", None))

    def register(self, app):
        if {fail_register!r}:
            raise RuntimeError("register boom")
        self.events.append(("register", app))

    def unregister(self, app):
        self.events.append(("unregister", app))
"""


def _write_plugin(
    directory: Path,
    file_stem: str,
    class_name: str,
    name: str,
    priority: int = 100,
    valid: bool = True,
    error: Optional[str] = None,
    fail_register: bool = False,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    plugin_file = directory / f"{file_stem}.py"
    plugin_file.write_text(
        PLUGIN_TEMPLATE.format(
            class_name=class_name,
            name=name,
            priority=priority,
            valid=valid,
            error=error,
            fail_register=fail_register,
        ),
        encoding="utf-8",
    )
    return plugin_file


@pytest.fixture
def plugin_dir(tmp_path) -> Path:
    directory = tmp_path / "plugins"
    directory.mkdir()
    return directory


@pytest.fixture
def config_dir(tmp_path) -> Path:
    directory = tmp_path / "config"
    directory.mkdir()
    return directory


def _manager(plugin_dir: Path, config_dir: Path) -> PluginManager:
    return PluginManager(plugin_dirs=[plugin_dir], config_dir=config_dir)


def _context() -> PluginContext:
    return PluginContext(app=typer.Typer())


def test_discovery_skips_private_files_and_survives_broken_ones(
    plugin_dir, config_dir, caplog
):
    _write_plugin(plugin_dir, "alpha", "AlphaPlugin", "alpha")
    _write_plugin(plugin_dir, "_private", "PrivatePlugin", "private")
    (plugin_dir / "broken.py").write_text(
        "raise ImportError('nope')\n", encoding="utf-8"
    )
    (plugin_dir / "notes.txt").write_text("ignored", encoding="utf-8")

    with caplog.at_level("WARNING", logger="max_cli.plugins.manager"):
        names = _discovered_names(_manager(plugin_dir, config_dir))

    assert names == ["AlphaPlugin"]
    assert any("broken.py" in record.getMessage() for record in caplog.records)


def test_discovery_ignores_missing_directory(tmp_path, config_dir):
    manager = PluginManager(plugin_dirs=[tmp_path / "absent"], config_dir=config_dir)

    assert manager.discover_plugins() == []


def test_default_plugin_dirs_skip_missing_and_bad_config_entries(fake_home, tmp_path):
    config_dir = fake_home / ".max_cli"
    config_dir.mkdir()
    real_extra = tmp_path / "extra"
    real_extra.mkdir()
    (config_dir / "plugins.json").write_text(
        json.dumps({"plugin_dirs": [str(real_extra), str(tmp_path / "gone"), 42]}),
        encoding="utf-8",
    )

    assert PluginManager()._plugin_dirs == [real_extra]


def test_default_config_dir_is_created_under_home(fake_home):
    PluginManager()

    assert (fake_home / ".max_cli").is_dir()


def test_load_all_calls_on_load_and_register_all_registers(plugin_dir, config_dir):
    _write_plugin(plugin_dir, "late", "LatePlugin", "late", priority=50)
    _write_plugin(plugin_dir, "early", "EarlyPlugin", "early", priority=10)
    manager = _manager(plugin_dir, config_dir)
    context = _context()

    manager.load_all(context)

    assert sorted(manager.list_plugins()) == ["early", "late"]
    early = manager.get_plugin("early")
    assert early.events == [("load", plugin_dir)]

    manager.register_all(context.app)

    assert manager.app is context.app
    assert early.events[-1] == ("register", context.app)
    assert manager.get_plugin("late").events[-1] == ("register", context.app)


def test_register_all_follows_priority(plugin_dir, config_dir, monkeypatch):
    _write_plugin(plugin_dir, "late", "LatePlugin", "late", priority=50)
    _write_plugin(plugin_dir, "early", "EarlyPlugin", "early", priority=10)
    manager = _manager(plugin_dir, config_dir)
    manager.load_all()
    registered = []
    for name in ["late", "early"]:
        plugin = manager.get_plugin(name)
        monkeypatch.setattr(
            plugin, "register", lambda app, name=name: registered.append(name)
        )

    manager.register_all(_context().app)

    assert registered == ["early", "late"]


def test_load_all_records_validation_failure(plugin_dir, config_dir):
    _write_plugin(
        plugin_dir, "invalid", "InvalidPlugin", "invalid", valid=False, error="bad"
    )
    manager = _manager(plugin_dir, config_dir)

    manager.load_all()

    loaded = manager.get_all_plugins()["invalid"]
    assert loaded.plugin is None
    assert loaded.enabled is False
    assert "bad" in loaded.error
    assert manager.list_plugins() == []
    assert manager.get_plugin_info("invalid") is None


def test_load_plugin_raises_validation_error(plugin_dir, config_dir):
    _write_plugin(plugin_dir, "nope", "NopePlugin", "nope", valid=False, error="x")
    manager = _manager(plugin_dir, config_dir)
    (plugin_class,) = manager.discover_plugins()

    with pytest.raises(PluginValidationError, match="x"):
        manager.load_plugin(plugin_class)


def test_register_failure_disables_plugin(plugin_dir, config_dir):
    _write_plugin(plugin_dir, "fails", "FailsPlugin", "fails", fail_register=True)
    manager = _manager(plugin_dir, config_dir)
    manager.load_all()

    manager.register_all(_context().app)

    loaded = manager.get_all_plugins()["fails"]
    assert loaded.enabled is False
    assert loaded.error == "register boom"


def test_disabled_plugin_is_not_loaded_or_registered(plugin_dir, config_dir):
    _write_plugin(plugin_dir, "quiet", "QuietPlugin", "quiet")
    (config_dir / "plugins.json").write_text(
        json.dumps({"enabled": {"quiet": False}}), encoding="utf-8"
    )
    manager = _manager(plugin_dir, config_dir)

    manager.load_all(_context())
    manager.register_all(_context().app)

    assert manager.is_plugin_enabled("quiet") is False
    assert manager.get_plugin("quiet").events == []
    assert manager.list_plugins() == []
    assert manager.list_plugins(include_disabled=True) == ["quiet"]


def test_unregister_all_calls_unregister_and_on_unload(plugin_dir, config_dir):
    _write_plugin(plugin_dir, "bye", "ByePlugin", "bye")
    manager = _manager(plugin_dir, config_dir)
    manager.load_all()
    app = _context().app

    manager.unregister_all(app)

    assert manager.get_plugin("bye").events == [
        ("unregister", app),
        ("unload", None),
    ]


def test_enable_and_disable_persist_to_config(plugin_dir, config_dir):
    _write_plugin(plugin_dir, "toggle", "TogglePlugin", "toggle")
    manager = _manager(plugin_dir, config_dir)
    manager.load_all()
    config_file = config_dir / "plugins.json"

    assert manager.disable_plugin("toggle") is True
    assert manager.is_plugin_enabled("toggle") is False
    assert json.loads(config_file.read_text(encoding="utf-8")) == {
        "enabled": {"toggle": False}
    }

    reloaded = _manager(plugin_dir, config_dir)
    reloaded.load_all()
    assert reloaded.is_plugin_enabled("toggle") is False

    assert reloaded.enable_plugin("toggle") is True
    assert json.loads(config_file.read_text(encoding="utf-8")) == {
        "enabled": {"toggle": True}
    }


def test_enable_and_disable_unknown_plugin(plugin_dir, config_dir):
    manager = _manager(plugin_dir, config_dir)

    assert manager.enable_plugin("ghost") is False
    assert manager.disable_plugin("ghost") is False
    assert not (config_dir / "plugins.json").exists()


@pytest.mark.xfail(
    strict=True,
    reason="is_plugin_enabled falls back to LoadedPlugin(plugin=None), whose "
    "enabled field defaults to True, so unknown plugins report as enabled",
)
def test_unknown_plugin_is_not_enabled(plugin_dir, config_dir):
    assert _manager(plugin_dir, config_dir).is_plugin_enabled("ghost") is False


@pytest.mark.parametrize(
    "raw_config",
    ["{not json", "[1, 2]", json.dumps({"enabled": ["not", "a", "dict"]})],
    ids=["invalid-json", "not-a-dict", "enabled-not-a-dict"],
)
def test_bad_config_falls_back_to_defaults(plugin_dir, config_dir, raw_config):
    (config_dir / "plugins.json").write_text(raw_config, encoding="utf-8")

    manager = _manager(plugin_dir, config_dir)

    assert manager._enabled_plugins == {}


def test_register_plugin_and_info(plugin_dir, config_dir):
    _write_plugin(plugin_dir, "manual", "ManualPlugin", "manual")
    manager = _manager(plugin_dir, config_dir)
    (plugin_class,) = manager.discover_plugins()
    plugin = plugin_class()

    manager.register_plugin(plugin)

    assert manager.get_plugin("manual") is plugin
    assert manager.get_plugin_info("manual") == {
        "name": "manual",
        "version": "1.2.3",
        "description": "demo",
        "author": "me",
        "author_email": "",
        "url": "",
        "license": "",
        "tags": ["t"],
        "dependencies": [],
        "enabled": True,
        "error": None,
    }

    manager.unregister_plugin("manual")
    manager.unregister_plugin("manual")

    assert manager.get_plugin("manual") is None
    assert manager.get_all_plugins() == {}


@pytest.mark.xfail(
    strict=True,
    reason="discover_plugins also returns CLIPlugin imported into the plugin "
    "module; load_all instantiates it and raises TypeError (abstract class), "
    "so a plugin written like examples/plugins/hello_world.py breaks startup",
)
def test_load_all_with_example_plugin(plugin_dir, config_dir):
    _install_example_plugin(plugin_dir)
    manager = _manager(plugin_dir, config_dir)

    manager.load_all(_context())

    assert manager.list_plugins() == ["hello-world"]


@pytest.mark.xfail(
    strict=True,
    reason="_find_plugin_dir matches the plugin name against the file stem, so "
    "'hello-world' never matches hello_world.py and on_load gets plugin_dir=None",
)
def test_on_load_gets_plugin_dir_for_hyphenated_name(plugin_dir, config_dir):
    _write_plugin(plugin_dir, "hello_world", "HelloPlugin", "hello-world")
    manager = _manager(plugin_dir, config_dir)

    manager.load_all(_context())

    assert manager.get_plugin("hello-world").events == [("load", plugin_dir)]
