"""PreToolUse hook: stop risky shell commands and gated file edits before they run.

Bash/PowerShell:
- deny: skipping git hooks (--no-verify), force-pushing, committing .env files
- deny: `gh pr create` for a branch that changes the package (src/,
        pyproject.toml) until `python scripts/ci_local.py` passed for it
        (the default check of what changed takes 1-3 minutes; --quick and
        --full count too). Docs, tests, scripts and skills don't need it:
        GitHub CI tests every PR.
- ask:  installing packages (AGENTS.md: ask before adding dependencies),
        git reset --hard / git clean -f (destroys uncommitted work)
Write/Edit:
- deny: .env files (secrets)
- ask:  pyproject.toml (dependencies and entry points are "ask first" in AGENTS.md)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path, PurePath

DENY_COMMAND_PATTERNS = [
    (r"--no-verify\b", "Skipping git hooks is not allowed. Fix the hook failure."),
    (
        r"\bgit\s+push\b.*(\s--force\b|\s-f\b|\s--force-with-lease\b)",
        "Force-push rewrites shared history. Ask the user to do it manually.",
    ),
    (r"\bgit\s+add\b.*\.env\b", "Never commit .env files."),
]
ASK_COMMAND_PATTERNS = [
    (
        r"\b(pip|pip3|uv\s+pip|poetry)\s+(install|add)\b(?!.*\s-e\s+\.)(?!.*\s-r\s)",
        "AGENTS.md: ask before adding third-party dependencies.",
    ),
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard discards uncommitted work."),
    (r"\bgit\s+clean\s+-\w*f", "git clean -f deletes untracked files."),
]
PR_CREATE = re.compile(r"\bgh\s+pr\s+create\b")
CI_LOCAL_STAMP = "ci-local.json"
CI_LOCAL_REASON = (
    "This branch changes the package (src/ or pyproject.toml): run "
    "`python scripts/ci_local.py` on a clean tree first (1-3 minutes: lint, "
    "types, the tests of what changed); it records HEAD when it passes."
)
# Changes under these need the full local run before a PR.
PACKAGE_PATHS = ("src/", "pyproject.toml")
BASE_BRANCH = "origin/main"
PASSING_MODES = ("changed", "quick", "full")  # scripts/ci_local.py's checks
ASK_EDIT_FILES = {
    "pyproject.toml": "AGENTS.md: ask before changing dependencies or entry points.",
}


def decision(kind: str, reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": kind,
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


HEREDOC_BODY = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n.*?^\s*\1\s*$", re.S | re.M)
QUOTED_STRING = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")


def strip_literals(command: str) -> str:
    """Drop heredoc bodies and quoted strings (commit messages, echo text).

    Flags only count when they are real arguments, so a commit message that
    mentions `--no-verify` does not trip the guard.
    """
    without_heredocs = HEREDOC_BODY.sub("<<HEREDOC", command)
    return QUOTED_STRING.sub("''", without_heredocs)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def changes_package(since: str) -> bool:
    """True when a commit after `since` touched src/ or pyproject.toml."""
    changed = _git("diff", "--name-only", f"{since}..HEAD").splitlines()
    return any(name.startswith(PACKAGE_PATHS) for name in changed)


def head_passed_local_ci() -> bool:
    """True when the PR may open without another local run.

    That is: the branch leaves the package alone, or the full run passed
    for HEAD, or for an earlier commit with only docs, tests or scripts
    after it.
    """
    try:
        if not changes_package(_git("merge-base", BASE_BRANCH, "HEAD")):
            return True
        stamp_file = _git("rev-parse", "--git-path", CI_LOCAL_STAMP)
        stamp = json.loads(Path(stamp_file).read_text(encoding="utf-8"))
        if stamp.get("mode") not in PASSING_MODES:
            return False
        passed = stamp.get("head", "")
        is_ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", passed, "HEAD"],
            capture_output=True,
        )
        return is_ancestor.returncode == 0 and not changes_package(passed)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return False


def check_command(command: str) -> None:
    command = strip_literals(command)
    for pattern, reason in DENY_COMMAND_PATTERNS:
        if re.search(pattern, command):
            decision("deny", reason)
            return
    if PR_CREATE.search(command) and not head_passed_local_ci():
        decision("deny", CI_LOCAL_REASON)
        return
    for pattern, reason in ASK_COMMAND_PATTERNS:
        if re.search(pattern, command):
            decision("ask", reason)
            return


def check_edit(file_path: str) -> None:
    name = PurePath(file_path.replace("\\", "/")).name
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        decision("deny", "Never edit .env files; they hold secrets. Use .env.example.")
        return
    if name in ASK_EDIT_FILES:
        decision("ask", ASK_EDIT_FILES[name])


def main() -> int:
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input") or {}
    tool_name = payload.get("tool_name", "")
    if tool_name in ("Bash", "PowerShell"):
        check_command(tool_input.get("command", ""))
    elif tool_input.get("file_path"):
        check_edit(tool_input["file_path"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
