# Session Handoff: Max CLI hardening, Phases 0-2 done, Phase 3 next

**Date:** 2026-09-25 **Project:** `D:\GitHub\Personal\max-cli` **Session duration:** about two days, 2026-09-24 to 2026-09-25

**Goal (user's words):** "write a handover because I want to compress the session." The next session continues the hardening plan with Phase 3.

## Current State

- **Task:** hardening the codebase from the September 2026 review, following `PLANS/active/codebase-hardening.md`.
- **Phase:** Phases 0, 1 and 2 are merged into `main`. Phase 3 (architecture consolidation) waits on three user decisions.
- **Progress:** 3 of 7 phases done.

## Repository State

- **Branch:** `main` at `7566f45` (merge of PR #3), in sync with `origin/main`.
- **Merged PRs:**
  - [#1](https://github.com/Abubakr-Alsheikh/max-cli/pull/1): Claude tooling and Phase 0.
  - [#2](https://github.com/Abubakr-Alsheikh/max-cli/pull/2): Phase 1, 13 bug fixes.
  - [#3](https://github.com/Abubakr-Alsheikh/max-cli/pull/3): Phase 2, atomic writes, utf-8 and LF.
- **Uncommitted, the user's own work in progress. Do not stage, format or edit it without asking:**
  - `src/max_cli/interface/tui/app.py` (modified)
  - `src/max_cli/interface/tui/widgets/download_panel.py` (modified)
  - `src/max_cli/common/download_history.py` (untracked)
- **Committed on `main` after PR #3:** the handoff skill (`.claude/skills/handoff/`), its `THIRD_PARTY.md` entry, the `AGENTS.md` mention and this handoff file.
- **Stash:** `stash@{0}: WIP on main: 5378faa`. It is the user's and predates this session. Leave it alone.

## Plan Status

- **Plan:** [`PLANS/active/codebase-hardening.md`](../../PLANS/active/codebase-hardening.md). It holds the per-phase checklists, results and the decisions log. Read it instead of trusting this summary.
- **Done:** Phase 0 (safety net), Phase 1 (13 critical bugs), Phase 2 (data integrity).
- **Deferred from Phase 2:** widening the ruff rules one family per PR (`I`, then `BLE`, `B`, `UP`/`FA`, `DTZ`). Import sorting would rewrite the user's uncommitted TUI files, so this waits until that work is committed.
- **Open decisions, needed before Phase 3:**
  - [ ] **D1:** merge the `max grab` queue (`QueueManager`, `grab_history.json`) and the WIP `download_history.py` into `DaemonManager` plus `task_queue`. Recommendation: yes.
  - [ ] **D3:** the "daemon" is a thread that dies when the CLI exits. Rename it honestly (option A) or build a real detached process (option B). Recommendation: A.
  - [ ] **D4:** keep the 200 ms startup target by switching the `common/events.py` pydantic models to dataclasses. Recommendation: yes.
- **Decided:**
  - D2: plugins load only from `~/.max_cli/plugins` plus `"plugin_dirs"` in `~/.max_cli/plugins.json`.
  - mypy targets Python 3.10.

## Quality Gates (on `main`, 2026-09-25)

- `pytest`: 308 passed, 1 skipped, 3 xfailed.
- `ruff check .`: clean. The rule set is pinned to `E4,E7,E9,F`, and ruff is capped `<0.17`.
- `python scripts/mypy_baseline.py`: 45 errors, which matches `mypy-baseline.txt`. A fresh CI-like venv also reports 45.
- `python .claude/hooks/check_rules.py --audit src/max_cli`: 25 violations, down from 84 at the start. What remains: silent-except 8, no-ui-in-core 5, type-ignore-reason 5, lazy-import 2, no-print-in-core 2, engine-at-import 2, atomic-write 1 (`pdf_engine` OCR output, intentional).
- CI: all 12 test jobs (Python 3.9 to 3.12 on Ubuntu, macOS and Windows), typecheck and build passed on PR #3.

## What We Did

1. Reviewed the whole codebase.
2. Added Claude Code tooling:
   - Hooks: a rule checker after edits, a guard before commands, and a stop gate that runs tests.
   - 4 project skills.
   - 10 vetted third-party skills, including this handoff skill.
3. Wrote a 7-phase hardening plan and shipped three phases as PRs, each with regression tests that fail on the old code.

Details live in the plan's per-phase sections and the commit messages on `main`.

## Decisions Made

- **Hooks flag only new violations.** They compare against HEAD, so existing debt doesn't block edits.
- **Vendor skills instead of installing plugins.** The files are markdown only, get read before installing, and carry an override block. Sources and licenses are recorded in `.claude/skills/THIRD_PARTY.md`.
- **mypy ratchet.** `scripts/mypy_baseline.py` fails when the count rises, and when it drops without `--update`. A blocking mypy error counts as a failure. Measure the baseline in a clean worktree so the user's WIP doesn't skew it.
- **Pin the tools that decide CI.** Unpinned ruff 0.16 and mypy 2.x each broke CI once.
- **mypy `python_version = 3.10`.** click 8.5 uses `match`, which aborted a run targeting 3.9. The user chose this. The CI 3.9 test jobs and the rule hook still guard 3.9 support.
- **Startup target test is a non-strict xfail.** Timing varies by machine. The segno and pyperclip import checks stay strict xfails.
- **One branch and one PR per phase**, one commit per bug.

## Blockers / Issues

- **D1, D3 and D4 are unanswered.** Phase 3 cannot start without them.
- **`download_history.py` (WIP) will fail checks when committed:**
  - `list[str] | None` annotations crash on Python 3.9. Add `from __future__ import annotations`.
  - It uses a direct `write_text`. Use `atomic_write_json`.
  - It adds 4 mypy errors.
- **23 junk "Test" tasks sit in the user's real `~/.max_cli/tasks/queue.json`**, left by the old test suite. The tests are isolated now. The user hasn't decided whether to clean the file; do not touch it without asking.

## Context to Remember

- **Platform:** Windows 11. Python 3.11.6 locally. `python3` is a broken Microsoft Store stub, so the hooks launch through `.claude/hooks/run.sh`. Git Bash is the shell.
- **Tooling pitfalls from this session:**
  - Bash heredocs collapse `\\` to `\`. Write scripts or tests that contain backslashes with the Write or Edit tool.
  - `Path.write_text` on Windows writes CRLF. It corrupted 14 files once; they are fixed, and `.gitattributes` enforces LF. Keep line endings when scripting edits (`newline=""` or bytes).
  - The PostToolUse hook reports undefined names after partial multi-step edits. That's expected; F401 is unfixable in the hook, so imports are not deleted.
  - Gate commits on pytest's own exit code, never `| tail`. One bad commit slipped through that way and was amended before it was pushed.
- **User preferences:**
  - Replies in terse "caveman" style.
  - Persisted prose (commits, PRs, docs, handoffs) in plain English with the stop-slop rules: no em dashes, active voice, no filler.
  - AGENTS.md section 19: after two failed fixes, stop and report `[HALT]`.
  - Ask before editing `pyproject.toml` (the guard hook asks automatically).
  - The user merges PRs or asks me to. Create a branch per phase.
- **Environment:** a CI-like fresh venv exists at `C:\Users\ASUS\.claude\jobs\35a4c597\tmp\venv-ci`. It's temporary and removed with the job. Rebuild it with `python -m venv <dir>` and `pip install -e .[dev,tui]` if needed.

## Next Steps

1. [x] Commit this session's leftovers (`.claude/skills/handoff/`, `.claude/skills/THIRD_PARTY.md`, `AGENTS.md`, this handoff). Done directly on `main`, at the user's request. Check `git status` for whether it has been pushed.
2. [ ] Ask the user for D1, D3 and D4. Record the answers in the plan's decisions section.
3. [ ] Start Phase 3 on branch `refactor/hardening-p3-architecture`, following the plan's Phase 3 checklist:
   - Merge the queue stores (D1).
   - Remove the Rich `console` from core.
   - Move the FFmpeg prompt to the interface.
   - Fix lazy loading: empty the eager `core/engines/__init__.py`; replace `cli_tools`/`cli_queue` module-level engines with `_get_engine()`; lazy-load `segno`/`pyperclip`.
   - Make the event models dataclasses (D4).
   - Split `media_engine.py`.
   - Move business logic out of `cli_ai`, `cli_pdf` and `cli_network`.
   - Narrow the silent broad excepts.
4. [ ] When Phase 3 makes the startup leaks pass, remove the strict xfail markers in `tests/test_startup_time.py`, and turn the 200 ms target into a plain assert.
5. [ ] Later phases:
   - Phase 4: shared TUI/CLI presets.
   - Phase 5: CLI tests for 8 command groups.
   - Phase 6: docs and PLANS cleanup, plus the ruff widening PRs.

## Files to Review on Resume

- `PLANS/active/codebase-hardening.md`: the source of truth for phases, results and decisions.
- `AGENTS.md`: project rules, the hooks and skills section (5), and the `common/` helpers (`archives.py`, `atomic.py`).
- `.claude/settings.json` and `.claude/hooks/`: what the hooks enforce and block.
- `scripts/mypy_baseline.py` and `mypy-baseline.txt`: the type-check ratchet.
- `src/max_cli/core/engines/daemon_manager.py` and `queue_manager.py`: the Phase 3 D1 targets.
- `src/max_cli/common/events.py`: the Phase 3 D4 target.
