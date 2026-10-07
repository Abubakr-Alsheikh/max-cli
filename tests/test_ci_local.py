"""scripts/ci_local.py: the local copy of CI, and the guard that asks for it before a PR."""

import importlib.util
import json
import re
import subprocess
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

    def test_same_pytest_launcher(self):
        """GitHub runs the `pytest` script; `python -m pytest` also puts the
        working folder on sys.path, which hid a broken `tests.` import."""
        assert re.search(r"^\s+pytest ", self.workflow, re.MULTILINE)
        source = Path(ci_local.__file__).read_text(encoding="utf-8")
        assert '"-m", "pytest"' not in source
        assert '"-m",\n            "pytest"' not in source


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
    monkeypatch.setattr(ci_local, "check", lambda mode: checks.append(mode) or 0)
    monkeypatch.setattr(ci_local, "pushes_package_changes", lambda lines: True)
    return stamp, checks


def _push_line(sha: str) -> str:
    return f"refs/heads/topic {sha} refs/heads/topic {ci_local.ZERO_SHA}"


class TestPrePush:
    def test_skips_a_push_that_leaves_the_package_alone(self, fake_repo, monkeypatch):
        _, checks = fake_repo
        monkeypatch.setattr(ci_local, "pushes_package_changes", lambda lines: False)

        assert ci_local.pre_push([_push_line(HEAD_SHA)]) == 0
        assert checks == []

    def test_skips_a_commit_that_already_passed(self, fake_repo):
        stamp, checks = fake_repo
        stamp.write_text(
            json.dumps({"head": HEAD_SHA, "mode": "quick"}), encoding="utf-8"
        )

        assert ci_local.pre_push([_push_line(HEAD_SHA)]) == 0
        assert checks == []

    def test_runs_the_changed_check_on_a_new_commit(self, fake_repo):
        _, checks = fake_repo

        assert ci_local.pre_push([_push_line(HEAD_SHA)]) == 0
        assert checks == ["changed"]

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


class TestGuardNeedsTheLocalRunOnlyForThePackage:
    """The full local run takes 10-20 minutes; GitHub CI tests every PR."""

    def _commit(self, repo, name: str, text: str = "x") -> str:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        subprocess.run(["git", "add", name], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", name], cwd=repo, check=True)
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    def _stamp(self, repo, head: str) -> None:
        (repo / ".git" / guard.CI_LOCAL_STAMP).write_text(
            json.dumps({"head": head, "mode": "full"}), encoding="utf-8"
        )

    @pytest.fixture
    def repo(self, tmp_path, monkeypatch):
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        for key, value in (("user.email", "t@t"), ("user.name", "t")):
            subprocess.run(["git", "config", key, value], cwd=tmp_path, check=True)
        base = self._commit(tmp_path, "README.md")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(guard, "BASE_BRANCH", base)
        return tmp_path

    def test_docs_and_tests_need_no_local_run(self, repo):
        self._commit(repo, "docs/usage.md")
        self._commit(repo, "tests/test_x.py")

        assert guard.head_passed_local_ci()

    def test_a_package_change_needs_a_full_pass(self, repo):
        self._commit(repo, "src/max_cli/x.py")

        assert not guard.head_passed_local_ci()

    def test_docs_after_a_full_pass_need_no_new_run(self, repo):
        passed = self._commit(repo, "src/max_cli/x.py")
        self._stamp(repo, passed)
        self._commit(repo, "CHANGELOG.md")

        assert guard.head_passed_local_ci()

    def test_code_after_a_full_pass_needs_a_new_run(self, repo):
        passed = self._commit(repo, "src/max_cli/x.py")
        self._stamp(repo, passed)
        self._commit(repo, "pyproject.toml")

        assert not guard.head_passed_local_ci()


def test_an_annotated_tag_on_the_checked_out_commit_runs_the_check(
    fake_repo, monkeypatch
):
    """`git push origin v1.0.0` was refused: an annotated tag is its own
    object, and the hook compared that object with HEAD."""
    _, checks = fake_repo
    tag_object = "c" * 40
    answers = {
        ("rev-parse", "HEAD"): HEAD_SHA,
        ("rev-parse", f"{tag_object}^{{commit}}"): HEAD_SHA,
    }
    monkeypatch.setattr(ci_local, "git", lambda *args: answers.get(args, ""))
    line = f"refs/tags/v1.0.0 {tag_object} refs/tags/v1.0.0 {ci_local.ZERO_SHA}"

    assert ci_local.pre_push([line]) == 0
    assert checks == ["changed"]


class TestChangedCheck:
    def _steps(self, monkeypatch, changed: list) -> list:
        ran: list = []
        monkeypatch.setattr(ci_local, "changed_files", lambda: changed)
        monkeypatch.setattr(
            ci_local,
            "run_step",
            lambda name, command, env=None: ran.append((name, command))
            or ci_local.StepResult(name, True, 0.0, ""),
        )
        monkeypatch.setattr(ci_local, "announce", lambda result: result)
        ci_local.changed_steps()
        return ran

    def test_runs_only_the_tests_of_what_changed(self, monkeypatch):
        ran = self._steps(monkeypatch, ["src/max_cli/core/agent/memory.py"])

        name, command = ran[-1]
        assert "related files" in name
        assert "tests/test_agent_memory.py" in command

    def test_a_conftest_or_pyproject_change_runs_everything(self, monkeypatch):
        ran = self._steps(monkeypatch, ["tests/conftest.py"])

        name, command = ran[-1]
        assert "whole suite" in name
        assert not any(part.startswith("tests/") for part in command)

    def test_docs_alone_run_no_tests(self, monkeypatch):
        ran = self._steps(monkeypatch, ["README.md"])

        assert not any(name.startswith("pytest") for name, _ in ran)


def test_a_lighter_pass_keeps_a_stronger_one(fake_repo):
    stamp, _ = fake_repo
    stamp.write_text(json.dumps({"head": HEAD_SHA, "mode": "quick"}), encoding="utf-8")

    ci_local.record_pass("changed")

    assert json.loads(stamp.read_text(encoding="utf-8"))["mode"] == "quick"


def test_the_guard_accepts_the_changed_check(tmp_path, monkeypatch):
    stamp = tmp_path / guard.CI_LOCAL_STAMP
    stamp.write_text(json.dumps({"head": "abc", "mode": "changed"}), encoding="utf-8")
    answers = {
        ("merge-base", guard.BASE_BRANCH, "HEAD"): "base",
        ("rev-parse", "--git-path", guard.CI_LOCAL_STAMP): str(stamp),
    }
    monkeypatch.setattr(guard, "_git", lambda *args: answers.get(args, ""))
    monkeypatch.setattr(guard, "changes_package", lambda since: since == "base")

    class Done:
        returncode = 0

    monkeypatch.setattr(guard.subprocess, "run", lambda *args, **kwargs: Done())

    assert guard.head_passed_local_ci()
