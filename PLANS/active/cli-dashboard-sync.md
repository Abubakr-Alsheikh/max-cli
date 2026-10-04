# Plan: CLI and Dashboard as One App

**Status:** In Progress
**Priority:** P1
**Updated:** 2026-10-04

## Goal

Whatever you do in the CLI shows up in the dashboard, and whatever you do in the dashboard shows up in the CLI. They feel like one app with two faces.

## The idea (maintainer, 2026-09-26)

"If you run a command it will show in the user interface, and if you do something in the user interface it will show also in the command." The two stay connected, so you see the same state in both places.

## What we know today (checked 2026-10-04)

- **Shared:** the task store in `~/.max_cli/tasks/`, safe across processes since 2026-10-03 (`queue.lock`, `worker.lock`). `max queue`, `max grab`, `--queue` on CLI commands, the agent and the dashboard all use it, and the background worker (`max queue worker`) runs queued work after the command returns. The dashboard reloads it every 2 seconds, so a task queued from the CLI shows on Activity's Queue tab with its progress.
- **The activity log moved to core:** `common/activity_log.py`. Writers today:
  - dashboard forms (`interface/tui/widgets/action_form.py:463`);
  - the agent, from the CLI and the AI page (`core/agent/agent.py:353`, `:964`).
- **Not written to the activity log (the 1.0 bug):**
  - The Download page. Its rows call `catalog.runner.run_action` directly (`interface/tui/widgets/download_panel.py:1180`) and log nothing. The page lost its logging when the redesign dropped `CommandExecutor` (commit 133f6d8).
  - CLI commands (`max video compress ...`, `max grab download ...`): no `interface/cli_*.py` writes to it.
  - Queued tasks when they finish: `catalog/runner.py` and the worker don't log.

  Home counts only activity-log entries (`interface/tui/home_stats.py`), so its Downloads kind, This week, Success % and Recent leave all of these out. Activity's History tab offers a Downloads filter that only agent downloads fill. The agent's `recent_activity` look misses them too.

## Tasks

- [x] **Before 1.0:** downloads from the Download page, CLI commands and batches, and queued tasks the worker finishes write an entry (`core/catalog/activity.py`, 2026-10-04). Cancelled downloads aren't logged. The activity log locks and merges each save, so several processes can write it.
- [ ] One activity record that every command writes, whether it ran from the CLI, the dashboard, the queue or the agent. Simplest: log in `catalog.runner.run_action` (or `run_each`) and in the queue's action executor, then drop the per-caller logging. Keep one store (AGENTS.md).
- [ ] `max history` in the CLI reads the same records as the History tab. Today only `max files history` (the undo log) and `max grab history` (the task store) exist.
- [x] Live updates: the dashboard refreshes the open page every 2 seconds and reloads the task store from disk (`TaskManager.refresh`). Polling, no change counter; good enough so far.
- [x] Commands started in the CLI appear in the dashboard's Queue as running, with progress, when they're queued (`--queue`, the worker saves progress every `PROGRESS_SAVE_SECONDS`).
- [x] Decided: no hand-off between processes. Both sides read the same store, and the background worker runs queued work.

## Related

- `dashboard-first-ai-agent.md` (the agent should write the same records).
- The `global-task-queue.md` open items.
