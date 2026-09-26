"""scripts/ci_local.py: the local copy of CI, and the guard that asks for it before a PR."""

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
HEAD_SHA = "a" * 40
OTHER_SHA = "b" * 40


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look the module up by name
    spec.loader.exec_module(module)
    return module


ci_local = _load("ci_local", REPO_ROOT / "scripts" / "ci_local.py")
guard = _load("guard", REPO_ROOT / ".claude" / "hooks" / "guard.py")


class TestMatchesCiWorkflow:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    def test_same_python_versions(self):
        matrix = re.search(r"python-version:\s*\[([^\]]+)\]", self.workflow)
        assert matrix is not None
        versions = tuple(re.findall(r"'([\d.]+)'", matrix.group(1)))
        assert versions == ci_local.PYTHON_VERSIONS

    def test_same_coverage_floor(self):
        floor = re.search(r"--cov-fail-under=(\d+)", self.workflow)
        assert floor is not None
        assert int(floor.group(1)) == ci_local.COVERAGE_MIN

    def test_same_typecheck_python(self):
        typecheck_job = self.workflow.split("typecheck:")[1].split("build:")[0]
        assert f"python-version: '{ci_local.TYPECHECK_PYTHON}'" in typecheck_job

    def test_same_install_extras(self):
        assert f"pip install -e {ci_local.PACKAGE_EXTRAS}" in self.workflow


@pytest.fixture
def fake_repo(monkeypatch, tmp_path):
    """HEAD is HEAD_SHA, the tree is clean, and the stamp lives in tmp_path."""
    stamp = tmp_path / "ci-local.json"
    monkeypatch.setattr(ci_local, "stamp_path", lambda: stamp)
    monkeypatch.setattr(ci_local, "tree_is_clean", lambda: True)
    monkeypatch.setattr(
        ci_local, "git", lambda *args: HEAD_SHA if args == ("rev-parse", "HEAD") else ""
    )
    checks: list[bool] = []
    monkeypatch.setattr(ci_local, "check", lambda full: checks.append(full) or 0)
    return stamp, checks


def _push_line(sha: str) -> str:
    return f"refs/heads/topic {sha} refs/heads/topic {ci_local.ZERO_SHA}"


class TestPrePush:
    def test_skips_a_commit_that_already_passed(self, fake_repo):
        stamp, checks = fake_repo
        stamp.write_text(
            json.dumps({"head": HEAD_SHA, "mode": "quick"}), encoding="utf-8"
        )

        assert ci_local.pre_push([_push_line(HEAD_SHA)]) == 0
        assert checks == []

    def test_runs_the_quick_check_on_a_new_commit(self, fake_repo):
        _, checks = fake_repo

        assert ci_local.pre_push([_push_line(HEAD_SHA)]) == 0
        assert checks == [False]

    def test_refuses_a_commit_that_is_not_checked_out(self, fake_repo):
        _, checks = fake_repo

        assert ci_local.pre_push([_push_line(OTHER_SHA)]) == 1
        assert checks == []

    def test_refuses_uncommitted_changes(self, fake_repo, monkeypatch):
        _, checks = fake_repo
        monkeypatch.setattr(ci_local, "tree_is_clean", lambda: False)

        assert ci_local.pre_push([_push_line(HEAD_SHA)]) == 1
        assert checks == []

    def test_branch_delete_needs_no_check(self, fake_repo):
        _, checks = fake_repo
        delete = f"(delete) {ci_local.ZERO_SHA} refs/heads/topic {OTHER_SHA}"

        assert ci_local.pre_push([delete]) == 0
        assert checks == []


class TestRecordPass:
    def test_quick_pass_keeps_an_earlier_full_pass(self, fake_repo):
        stamp, _ = fake_repo
        full = {"head": HEAD_SHA, "mode": "full"}
        stamp.write_text(json.dumps(full), encoding="utf-8")

        ci_local.record_pass("quick")

        assert json.loads(stamp.read_text(encoding="utf-8")) == full

    def test_dirty_tree_records_nothing(self, fake_repo, monkeypatch):
        stamp, _ = fake_repo
        monkeypatch.setattr(ci_local, "tree_is_clean", lambda: False)

        ci_local.record_pass("full")

        assert not stamp.exists()


class TestGuardPrCreate:
    def _decision(self, capsys, command: str) -> str:
        guard.check_command(command)
        output = capsys.readouterr().out
        if not output:
            return "allow"
        return json.loads(output)["hookSpecificOutput"]["permissionDecision"]

    def test_denied_until_local_ci_passed(self, capsys, monkeypatch):
        monkeypatch.setattr(guard, "head_passed_local_ci", lambda: False)
        assert self._decision(capsys, 'gh pr create --title "x" --body "y"') == "deny"

    def test_allowed_after_a_full_pass(self, capsys, monkeypatch):
        monkeypatch.setattr(guard, "head_passed_local_ci", lambda: True)
        assert self._decision(capsys, "gh pr create --fill") == "allow"

    def test_other_gh_commands_are_not_affected(self, capsys, monkeypatch):
        monkeypatch.setattr(guard, "head_passed_local_ci", lambda: False)
        assert self._decision(capsys, "gh pr view 23") == "allow"
