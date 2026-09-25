# Active Plans

Plans being worked on. Finished plans move to `../completed/` and parked ones to `../deferred/`. The workflow lives in `.claude/skills/max-plans/SKILL.md`.

Reconciled against the code on 2026-09-25 (hardening Phase 6).

## Current Active Plans

| Plan | Status | Priority | What's left |
|------|--------|----------|-------------|
| [tui-bugfix-and-ux-improvements.md](./tui-bugfix-and-ux-improvements.md) | In Progress | P0 | Config search crash, chat blocks the UI, files filter, grab/download category mismatch |
| [dashboard-home-analytics-redesign.md](./dashboard-home-analytics-redesign.md) | In Progress | P1 | Downloads stat card reads 0, panel tests, docs |
| [interactive-tui-expansion.md](./interactive-tui-expansion.md) | In Progress | P1 | Unwired System buttons, blocking Chat/Files actions, registry/executor tests, dashboard docs |
| [global-task-queue.md](./global-task-queue.md) | In Progress | P1 | `--queue` on the commands that already have executors; `audio_convert` and `ai_batch` executors |
| [file-undo-transaction-log.md](./file-undo-transaction-log.md) | In Progress | P2 | 11 mypy errors in `common/transaction_log.py` |
| [user-workflows-aliases.md](./user-workflows-aliases.md) | Draft | P1 | Not started |
| [dashboard-first-ai-agent.md](./dashboard-first-ai-agent.md) | In Progress | P1 | Roadmap: bare `max` opens the dashboard, `max "<request>"` goes to an AI agent. D1-D5 answered; Step 1 done |
| [command-catalog.md](./command-catalog.md) | In Progress | P1 | Roadmap Step 2: one catalog in core feeds the CLI, dashboard forms and agent tools. `video` and the Tools page done; `grab` next |
| [dashboard-ui-redesign.md](./dashboard-ui-redesign.md) | Draft (idea) | P1 | Scrolling on every page, a TUI design standard, full command options in forms |
| [cli-dashboard-sync.md](./cli-dashboard-sync.md) | Draft (idea) | P1 | CLI and dashboard share one live activity record |
| [paths-from-anywhere.md](./paths-from-anywhere.md) | Draft (idea) | P1 | Run commands on any file or folder; file picker in the dashboard |
| [feature-packs.md](./feature-packs.md) | Draft (idea) | P2 | Choose which features and dashboard pages you get |
| [plugin_commands_migration.md](./plugin_commands_migration.md) | Draft | P2 | Not started; plugins are out of focus for now |

## Creating a New Plan

```markdown
# Plan: <Feature Name>

**Status:** Draft | In Progress | Completed | Deferred
**Priority:** P0 | P1 | P2
**Updated:** YYYY-MM-DD

## Goal
One paragraph: the user-visible outcome.

## Tasks
- [ ] Engine: ...
- [ ] Interface: ...
- [ ] Tests: ...
- [ ] Docs: README.md, docs/commands/<group>.md

## Decisions
- <decision> (why)
```
