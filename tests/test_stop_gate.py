""".claude/hooks/stop_gate.py: which tests run before a turn ends."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load() -> ModuleType:
    path = REPO_ROOT / ".claude" / "hooks" / "stop_gate.py"
    spec = importlib.util.spec_from_file_location("stop_gate", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["stop_gate"] = module
    spec.loader.exec_module(module)
    return module


stop_gate = _load()


def _repo(tmp_path: Path) -> Path:
    files = {
        "tests/test_video.py": "from max_cli.core.operations import video\n",
        "tests/test_pages.py": "import max_cli.interface.tui.widgets.ai_panel\n",
        "tests/test_other.py": "x = 1\n",
        "tests/sub/test_deep.py": "from max_cli.core.agent import context\n",
    }
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_tests_follow_the_edited_files(tmp_path):
    repo = _repo(tmp_path)

    found = stop_gate.related_tests(
        [
            "src/max_cli/core/operations/video.py",  # by name and by import
            "src/max_cli/interface/tui/widgets/ai_panel.py",  # by dotted import
            "src/max_cli/core/agent/context.py",  # by from-import
            "tests/test_other.py",  # an edited test runs itself
        ],
        repo,
    )

    assert found == [
        "tests/sub/test_deep.py",
        "tests/test_other.py",
        "tests/test_pages.py",
        "tests/test_video.py",
    ]


def test_files_without_tests_run_none(tmp_path):
    repo = _repo(tmp_path)

    assert stop_gate.related_tests(["src/max_cli/config.py", "README.md"], repo) == []
