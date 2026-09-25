# Active Plans

Plans being worked on. Finished plans move to `../completed/` and parked ones to `../deferred/`. The workflow lives in `.claude/skills/max-plans/SKILL.md`.

Reconciled against the code on 2026-09-25 (hardening Phase 6).

## Current Active Plans

| Plan | Status | Priority | What's left |
|------|--------|----------|-------------|
| [codebase-hardening.md](./codebase-hardening.md) | In Progress | P0 | D5 (startup under 200 ms), exit-code decision, ruff widening |
| [tui-bugfix-and-ux-improvements.md](./tui-bugfix-and-ux-improvements.md) | In Progress | P0 | Config search crash, chat blocks the UI, files filter, grab/download category mismatch |
| [dashboard-home-analytics-redesign.md](./dashboard-home-analytics-redesign.md) | In Progress | P1 | Downloads stat card reads 0, panel tests, docs |
| [interactive-tui-expansion.md](./interactive-tui-expansion.md) | In Progress | P1 | Unwired System buttons, blocking Chat/Files actions, registry/executor tests, dashboard docs |
| [global-task-queue.md](./global-task-queue.md) | In Progress | P1 | `--queue` on the commands that already have executors; `audio_convert` and `ai_batch` executors |
| [file-undo-transaction-log.md](./file-undo-transaction-log.md) | In Progress | P2 | 11 mypy errors in `common/transaction_log.py` |
| [user-workflows-aliases.md](./user-workflows-aliases.md) | Draft | P1 | Not started |
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
