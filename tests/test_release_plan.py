"""scripts/release_plan.py: which version a release should get, and why."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load() -> ModuleType:
    path = REPO_ROOT / "scripts" / "release_plan.py"
    spec = importlib.util.spec_from_file_location("release_plan", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["release_plan"] = module  # dataclasses look the module up by name
    spec.loader.exec_module(module)
    return module


plan = _load()


@pytest.mark.parametrize(
    ("subject", "body", "level"),
    [
        ("feat(video): max video trim", "", "minor"),
        ("fix(undo): keep the order", "", "patch"),
        ("perf(cli): load groups lazily", "", "patch"),
        ("docs: README", "", "none"),
        ("test(agent): budget", "", "none"),
        ("refactor(core): split", "", "none"),
        ("chore: bump", "", "none"),
        ("Update readme", "", "none"),  # not a Conventional Commit
        ("feat(cli)!: rename max grab to max get", "", "major"),
        ("fix(config): new setting name", "BREAKING CHANGE: OLD_NAME is gone", "major"),
    ],
)
def test_a_commit_calls_for_the_release_its_type_says(subject, body, level):
    assert plan.Commit("abc1234", subject, body).level == level


@pytest.mark.parametrize(
    ("level", "expected"),
    [("major", "2.0.0"), ("minor", "1.3.0"), ("patch", "1.2.4"), ("none", "1.2.3")],
)
def test_a_bump_resets_the_parts_after_it(level, expected):
    assert plan.bump((1, 2, 3), level) == expected


def test_the_biggest_change_decides():
    commits = [
        plan.Commit("a", "fix: one"),
        plan.Commit("b", "feat: two"),
        plan.Commit("c", "docs: three"),
    ]

    release = plan.Plan((1, 0, 0), "v1.0.0", commits)

    assert release.level == "minor"
    assert release.next_version == "1.1.0"


def test_only_docs_and_tests_need_no_release():
    commits = [plan.Commit("a", "docs: one"), plan.Commit("b", "test: two")]

    assert plan.Plan((1, 0, 0), "v1.0.0", commits).level == "none"


def test_a_breaking_change_in_the_diff_makes_it_major():
    signals = plan.diff_signals(
        'requires-python = ">=3.9"\n',
        'requires-python = ">=3.10"\n',
        'REMOVED_SETTINGS = (\n    "APP_NAME",\n)\n',
        'REMOVED_SETTINGS = (\n    "APP_NAME",\n    "VERBOSE",\n)\n',
    )

    assert signals == [
        "requires-python changed from >=3.9 to >=3.10",
        "settings removed: VERBOSE",
    ]
    release = plan.Plan((1, 4, 2), "v1.4.2", [plan.Commit("a", "fix: x")], signals)
    assert release.next_version == "2.0.0"


def test_the_log_is_read_without_merge_commits():
    sep, end = plan.FIELD_SEP, plan.RECORD_SEP
    log = (
        f"aaa{sep}feat: one{sep}{end}\n"
        f"bbb{sep}Merge pull request #9 from x/y{sep}{end}\n"
        f"ccc{sep}fix: two{sep}BREAKING CHANGE: gone{end}\n"
    )

    commits = plan.parse_log(log)

    assert [commit.sha for commit in commits] == ["aaa", "ccc"]
    assert commits[1].level == "major"


def test_the_report_names_the_commits_behind_the_suggestion():
    commits = [plan.Commit("1234567890", "feat(images): convert SVG")]

    text = plan.report(plan.Plan((1, 0, 0), "v1.0.0", commits))

    assert "Suggested: MINOR -> 1.1.0" in text
    assert "1234567 feat(images): convert SVG" in text
