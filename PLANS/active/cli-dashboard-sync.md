# Plan: CLI and Dashboard as One App

**Status:** Draft (idea captured; plan it later)
**Priority:** P1
**Updated:** 2026-09-26

## Goal

Whatever you do in the CLI shows up in the dashboard, and whatever you do in the dashboard shows up in the CLI. They feel like one app with two faces.

## The idea (maintainer, 2026-09-26)

"If you run a command it will show in the user interface, and if you do something in the user interface it will show also in the command." The two stay connected, so you see the same state in both places.

## What we know today

- **Shared already:** the task store in `~/.max_cli/tasks/` (hardening D1), used by `max queue`, `max grab` and the dashboard's Queue page. The dashboard sees other processes' tasks through `TaskManager.refresh()`.
- **Not shared:**
  - The dashboard's activity log (`~/.max_cli/activity_log.json`, `interface/tui/activity_log.py`) records only actions started in the dashboard. CLI commands never write to it.
  - `max files history` reads the transaction log, which the dashboard shows only partly.
- **Not live:** the dashboard refreshes on a timer or on key press. There's no notification when the CLI changes something.

## Ideas to plan later

- [ ] One activity record in core, which every command writes whether it ran from the CLI, the dashboard or the agent. Candidates: extend the task store's history, or a core `activity` module on atomic JSON. Decide on one store and don't add a third (AGENTS.md).
- [ ] `max history` in the CLI and the dashboard History page read the same records.
- [ ] Live updates: the dashboard watches the store (file mtime polling or a small change counter) and refreshes the page you're on.
- [ ] Commands started in the CLI appear in the dashboard's Queue/History as running, with progress, when they're queued.
- [ ] Decide whether the dashboard can hand work to a running CLI process or the other way round. This is probably not needed if both read the same store.

## Related

- `dashboard-first-ai-agent.md` (the agent should write the same records).
- The `global-task-queue.md` open items.
