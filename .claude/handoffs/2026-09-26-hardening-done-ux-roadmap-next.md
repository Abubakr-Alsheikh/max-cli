# Session Handoff: Hardening complete, dashboard-first + AI agent roadmap drafted

**Date:** 2026-09-26 **Project:** `D:\GitHub\Personal\max-cli` **Session duration:** 2026-09-25 to 2026-09-26 (continued from the Phases 0-2 handoff)

**Goal (user's words):** "make a handover because I am compressing this session and then commit and merge it with main branch."

## Current State

- **Task:** The codebase hardening plan is complete. The next body of work is the maintainer's UX roadmap: bare `max` opens the dashboard, and `max <text>` goes to an AI agent.
- **Phase:** The roadmap is planned only (Draft plans). No roadmap code has been written.
- **Progress:** Hardening Phases 0-6, D1-D5, exit codes and the ruff widening are all merged. The roadmap has not started.

## Repository State

- **Branch:** `main`. This handoff is committed on `docs/plans-ux-roadmap` and merged through PR #15 at the end of this session.
- **Merged this session:** PRs #4 to #15. Each passed 14 CI jobs (pytest on 3.9-3.12 × Ubuntu, macOS and Windows, plus typecheck and build).
  - #4 Phase 3 architecture.
  - #5 Phase 4 presets.
  - #6 Phase 5 tests.
  - #7 Phase 5b bug fixes.
  - #8 Phase 6 docs and plans.
  - #9 CLI audit fixes (config export key leak, shred backup).
  - #10 D5 lazy command groups.
  - #11 exit codes.
  - #12 / #13 / #14 ruff `I` / `B` / `UP`.
  - #15 roadmap plans.
- **Uncommitted:** none. The maintainer's former TUI WIP (download panel) was committed in Phase 3 (`d956390`).
- **Stash:** `stash@{0}: WIP on main: 5378faa` belongs to the maintainer and predates this work. Leave it alone.
- **Maintainer's `~/.max_cli`** (don't touch without asking):
  - `grab_history.json.migrated` and `grab_queue.json.migrated`: a smoke test ran the D1 migration on the real data. The entries now live in `tasks/history.json` and `tasks/queue.json`.
  - `tasks/queue.json.bak`: the 23 junk "Test" tasks. `queue.json` itself was emptied on request.
  - `backups/` may hold copies from shreds run before the shred fix. The maintainer hasn't decided whether to delete them.

## Plan Status

- **Completed:** [`PLANS/completed/codebase-hardening.md`](../../PLANS/completed/codebase-hardening.md) records every phase, decision and result. Deferred ruff families (with reasons there): `BLE`, `FA`, `DTZ`.
- **Next, Draft:** [`PLANS/active/dashboard-first-ai-agent.md`](../../PLANS/active/dashboard-first-ai-agent.md). Steps:
  1. Fix dashboard bugs.
  2. One command catalog feeding the CLI, the dashboard forms and the agent tools.
  3. Bare `max` opens the dashboard; `max <text>` goes to the agent.
  4. Agent v2: tool calling, plan and confirm, undo, on-demand command loading.
  5. Onboarding and packaging.
  - **Open decisions, needed before Step 3:**
    - D1: the routing rule for `max <text>`.
    - D2: open the dashboard only at an interactive terminal.
    - D3: textual becomes a core dependency (a `pyproject.toml` change needs approval).
    - D4: which folders the agent may touch.
    - D5: model support.
- **Idea drafts to plan later** (the maintainer's own requests):
  - [`dashboard-ui-redesign.md`](../../PLANS/active/dashboard-ui-redesign.md): 5 of 9 pages can't scroll, a TUI design standard, full options in forms.
  - [`cli-dashboard-sync.md`](../../PLANS/active/cli-dashboard-sync.md): one live activity record for the CLI and the dashboard.
  - [`paths-from-anywhere.md`](../../PLANS/active/paths-from-anywhere.md): any path, and a file picker.
  - [`feature-packs.md`](../../PLANS/active/feature-packs.md): turn features and pages on and off, arrow-key select menus for `max features` and `max config setup`, and a menu library to pick (a new dependency needs approval).
- **Other in-progress plans:** see [`PLANS/active/README.md`](../../PLANS/active/README.md), especially `tui-bugfix-and-ux-improvements.md` (P0), which is Step 1 of the roadmap.

## Quality Gates (on `main`, 2026-09-26)

- **pytest:** 830 passed, 1 skipped, 3 xfailed. The 3 xfails are strict tests for the deferred plugin bugs.
- **ruff:** clean with `select = ["E4","E7","E9","F","I","B","UP"]`. `.agents/` and `.claude/skills/` are excluded (vendored).
- **mypy:** 41, which matches `mypy-baseline.txt`. The CI-like venv (typer 0.27, click 8.5, textual 8.2.8) also reports 41.
- **Rule audit** (`python .claude/hooks/check_rules.py --audit src/max_cli`): 6 (type-ignore-reason 5, atomic-write 1).
- **Startup:** `import max_cli.main` takes about 80-100 ms. `tests/test_startup_time.py` asserts under 200 ms.
- **Coverage:** CI fails below 70% (72% locally).

## What We Did

- Finished hardening Phases 3-6:
  - One task store.
  - `TaskManager` (it was DaemonManager).
  - No UI in core.
  - Shared presets.
  - Tests for every CLI group.
  - 15 bugs found and 12 fixed.
  - Docs and plans reconciled with the code.
- Fixed the CLI issues the docs audit found:
  - Security: `config export` no longer writes the API key, and `shred` keeps no backup.
  - Wrong help examples, the `-f` conflict in `queue clear`, and missing confirmations.
- D5: lazy command groups took startup from 430 ms to about 90 ms. Commands exit 1 after `log_error`. Ruff now has the `I`, `B` and `UP` families.
- Drafted the maintainer's UX roadmap and four idea plans.

## Decisions Made

- **The CLI value wins preset conflicts** (Phase 4), except the dashboard's `artist-album` organize pattern. The maintainer chose that to fix a real problem, and it is `presets.TUI_AUDIO_ORGANIZE_PATTERN`.
- **Plugins are out of focus.** Three plugin bugs stay as strict xfails, and `plugin_commands_migration.md` stays Draft.
- **Lazy groups are built from Typer's own classes** (`TyperCommand`, `Any` for context types). Typer 0.27 bundles click as `typer._click`.
- **Exit codes use one flag** (`common/exit_status.py`) set by `log_error` and read in `main()`, so the ~100 error handlers needed no changes. Usage errors keep exit code 2.
- **`queue clear --failed` lost its `-f` short flag, and `-f` was not reused** for `--force`, so an old script errors instead of clearing without a prompt.
- **`max net` stays as a hidden alias** of `max grab`.
- **The agent loads commands on demand** (the maintainer's note): it starts with the parent groups only and loads a group's child commands when a request needs them. It sees only enabled features.

## Blockers / Issues

- None blocking. The roadmap needs D1-D5 answered before Step 3.
- **Known open bugs** (`tui-bugfix-and-ux-improvements.md`):
  - The Config search crashes, because `Label.renderable` is gone in Textual 8.
  - The Files filter does nothing (`Row.visible`).
  - The Downloads card and filter read 0, because of a `grab`/`download` category mismatch.
  - Chat blocks the UI.
- **mypy:** 11 errors in `common/transaction_log.py`, from `Optional[Path]` used without a check in `undo()`.

## Context to Remember

- **Platform:** Windows 11, Python 3.11.6, Git Bash. `python3` is a broken stub, so use `python`. The hooks launch through `.claude/hooks/run.sh`.
- **Tooling pitfalls from this session:**
  - Gate commits on the tool's own exit code. `cmd | tail` hides failures; it happened twice. Use `cmd > file; echo $?`.
  - Bash heredocs collapse `\\` and `\n` escapes. Write scripts that contain backslashes with the Write tool, or use Edit.
  - Don't run commands that start a `TaskManager` (`max queue ...`, `max grab ...`) against the real home folder. Tests are isolated by the autouse `isolated_home` and `isolated_task_store` fixtures in `tests/conftest.py`.
  - A CI-like venv lives at `C:\Users\ASUS\.claude\jobs\35a4c597\tmp\venv-ci`. It is temporary, and useful when CI and local results disagree.
- **User preferences:**
  - Replies are terse (caveman style). Commits, PRs, docs and plans use plain English with the stop-slop rules: no em dashes, active voice, no filler.
  - Ask before editing `pyproject.toml` dependencies (the guard hook prompts).
  - One branch and one PR per piece of work. The maintainer usually asks for the merge; merge only when they say so.
  - AGENTS.md section 19: after two failed fixes, stop and report `[HALT]`.

## Next Steps

1. [ ] Confirm `main` includes PR #15 and this handoff (`git log --oneline -3`).
2. [ ] Ask the maintainer for decisions D1-D5 in `PLANS/active/dashboard-first-ai-agent.md`.
3. [ ] Start roadmap Step 1 on a new branch: fix the P0 dashboard bugs in `tui-bugfix-and-ux-improvements.md`. Write a failing test first for each bug.
4. [ ] Then plan Step 2, the command catalog, in detail. It's the biggest architecture change, so propose the design before writing code (AGENTS.md section 8).
5. [ ] Quick wins whenever useful:
   - Add `--queue` to the six commands that already have executors (`global-task-queue.md`).
   - Fix the 11 mypy errors in `transaction_log.py`, then run `mypy_baseline.py --update`.

## Files to Review on Resume

- `PLANS/active/README.md` and `PLANS/active/dashboard-first-ai-agent.md`: what's next.
- `PLANS/completed/codebase-hardening.md`: the full history and decisions.
- `AGENTS.md`: the rules, lazy command groups, exit codes, presets, the task store.
- `src/max_cli/core/cli/registry.py` and `lazy_group.py`: where `max <text>` routing will go.
- `src/max_cli/interface/tui/command_registry.py`: the seed of the command catalog.
- `src/max_cli/core/engines/ai_engine.py` and `interface/cli_ai.py`: the current AI flow, which agent v2 replaces.
