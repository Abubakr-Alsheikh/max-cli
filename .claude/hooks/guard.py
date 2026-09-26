"""PreToolUse hook: stop risky shell commands and gated file edits before they run.

Bash/PowerShell:
- deny: skipping git hooks (--no-verify), force-pushing, committing .env files
- deny: `gh pr create` until HEAD passed `python scripts/ci_local.py --full`
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
    "Run `python scripts/ci_local.py --full` on a clean tree first; "
    "it runs the GitHub CI checks locally and records HEAD when they pass."
)
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


def head_passed_local_ci() -> bool:
    """True when scripts/ci_local.py --full passed for the checked-out commit."""
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        stamp_file = subprocess.run(
            ["git", "rev-parse", "--git-path", CI_LOCAL_STAMP],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        stamp = json.loads(Path(stamp_file).read_text(encoding="utf-8"))
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return False
    return stamp == {"head": head, "mode": "full"}


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
