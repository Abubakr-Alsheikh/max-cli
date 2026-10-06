"""Suggest the next version: major, minor or patch, and why.

    python scripts/release_plan.py            # since the last tag
    python scripts/release_plan.py --since v1.0.0

It reads the commits since the last release tag and sorts them by their
Conventional Commits type, then checks the diff for changes that break users
whatever the commits say. The rules are in docs/contributing.md
("Versions and releases"); the max-release skill walks through a release.

    major  a commit marked breaking (`feat!:`, `BREAKING CHANGE:`), a Python
           version dropped, or a setting removed
    minor  a `feat` commit: a new command, option, page, setting or format
    patch  only `fix` and `perf` commits
    none   only docs, tests, refactors and chores: no release needed

It prints a suggestion; the person releasing decides.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
CONFIG_FILE = "src/max_cli/config.py"

LEVELS = ("none", "patch", "minor", "major")
# Conventional Commits types and the release each one calls for.
TYPE_LEVELS = {"feat": "minor", "fix": "patch", "perf": "patch"}
SUBJECT = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?: ")
BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGE:", re.MULTILINE)
VERSION_LINE = re.compile(r'^version = "(\d+)\.(\d+)\.(\d+)"', re.MULTILINE)
REQUIRES_PYTHON = re.compile(r'^requires-python = "([^"]*)"', re.MULTILINE)
# config.REMOVED_SETTINGS: a tuple today; a list or a set reads the same.
REMOVED_SETTINGS = re.compile(
    r"^REMOVED_SETTINGS[^=]*=\s*[\(\[\{](.*?)[\)\]\}]", re.DOTALL | re.MULTILINE
)
FIELD_SEP, RECORD_SEP = "\x1f", "\x1e"


@dataclass
class Commit:
    sha: str
    subject: str
    body: str = ""

    @property
    def kind(self) -> str:
        found = SUBJECT.match(self.subject)
        return found.group("type") if found else "other"

    @property
    def breaking(self) -> bool:
        found = SUBJECT.match(self.subject)
        return bool(found and found.group("bang")) or bool(
            BREAKING_FOOTER.search(self.body)
        )

    @property
    def level(self) -> str:
        if self.breaking:
            return "major"
        return TYPE_LEVELS.get(self.kind, "none")


@dataclass
class Plan:
    current: tuple[int, int, int]
    since: str
    commits: list[Commit]
    signals: list[str] = field(default_factory=list)  # breaking changes in the diff

    @property
    def level(self) -> str:
        levels = [commit.level for commit in self.commits]
        if self.signals:
            levels.append("major")
        return max(levels, key=LEVELS.index, default="none")

    @property
    def next_version(self) -> str:
        return bump(self.current, self.level)


def bump(current: tuple[int, int, int], level: str) -> str:
    major, minor, patch = current
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    if level == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return f"{major}.{minor}.{patch}"


def parse_log(text: str) -> list[Commit]:
    """`git log --format=%H<US>%s<US>%b<RS>` output as commits, merges left out."""
    commits = []
    for record in text.split(RECORD_SEP):
        parts = record.strip("\n").split(FIELD_SEP)
        if len(parts) < 2 or not parts[0]:
            continue
        commit = Commit(parts[0], parts[1], parts[2] if len(parts) > 2 else "")
        if not commit.subject.startswith("Merge "):
            commits.append(commit)
    return commits


def removed_settings(text: str) -> set[str]:
    found = REMOVED_SETTINGS.search(text)
    return set(re.findall(r'"([A-Z_]+)"', found.group(1))) if found else set()


def diff_signals(
    old_pyproject: str, new_pyproject: str, old_config: str, new_config: str
) -> list[str]:
    """Changes that break users whatever the commit messages say."""
    signals = []
    old_python = REQUIRES_PYTHON.search(old_pyproject)
    new_python = REQUIRES_PYTHON.search(new_pyproject)
    if old_python and new_python and old_python.group(1) != new_python.group(1):
        signals.append(
            f"requires-python changed from {old_python.group(1)} to {new_python.group(1)}"
        )
    dropped = sorted(removed_settings(new_config) - removed_settings(old_config))
    if dropped:
        signals.append(f"settings removed: {', '.join(dropped)}")
    return signals


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _file_at(ref: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout if result.returncode == 0 else ""


def current_version(text: str) -> tuple[int, int, int]:
    found = VERSION_LINE.search(text)
    if found is None:
        raise SystemExit("No version line in pyproject.toml")
    major, minor, patch = (int(part) for part in found.groups())
    return major, minor, patch


def build_plan(since: str) -> Plan:
    log = _git(
        "log", f"--format=%H{FIELD_SEP}%s{FIELD_SEP}%b{RECORD_SEP}", f"{since}..HEAD"
    )
    pyproject = PYPROJECT.read_text(encoding="utf-8")
    released = _file_at(since, "pyproject.toml")
    signals = diff_signals(
        released,
        pyproject,
        _file_at(since, CONFIG_FILE),
        (REPO_ROOT / CONFIG_FILE).read_text(encoding="utf-8"),
    )
    # Count from the version released at `since`: pyproject.toml may be
    # bumped already.
    base = current_version(released if VERSION_LINE.search(released) else pyproject)
    return Plan(base, since, parse_log(log), signals)


def report(plan: Plan) -> str:
    current = ".".join(str(part) for part in plan.current)
    lines = [f"Since {plan.since} ({current}): {len(plan.commits)} commits."]
    if plan.level == "none":
        lines.append("Suggested: no release. Only docs, tests, refactors and chores.")
    else:
        lines.append(f"Suggested: {plan.level.upper()} -> {plan.next_version}")
    for level in ("major", "minor", "patch"):
        why = [commit for commit in plan.commits if commit.level == level]
        if level == "major":
            for signal in plan.signals:
                lines.append(f"  major  {signal}")
        for commit in why:
            lines.append(f"  {level:<6} {commit.sha[:7]} {commit.subject}")
    others = [commit for commit in plan.commits if commit.level == "none"]
    if others:
        kinds = sorted({commit.kind for commit in others})
        lines.append(
            f"  also   {len(others)} commits with no release of their own ({', '.join(kinds)})"
        )
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--since", help="tag or commit to start from (default: the last tag)"
    )
    options = parser.parse_args(argv)
    since = options.since or _git("describe", "--tags", "--abbrev=0").strip()
    print(report(build_plan(since)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
