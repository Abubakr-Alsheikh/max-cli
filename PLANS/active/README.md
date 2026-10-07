# Active Plans

Plans being worked on. Finished plans move to `../completed/` and parked ones to `../deferred/`. The workflow lives in `.claude/skills/max-plans/SKILL.md`.

Reconciled against the code on 2026-10-04, before the 1.0 release. Eight plans moved to `../completed/` that day (the old dashboard plans, the task queue, the command catalog, the Download page, the tool pages), and the plugin migration moved to `../deferred/`.

## Before 1.0

Found in the reconciliation on 2026-10-04.

| Problem | Status |
|---------|--------|
| FFmpeg actions replace an existing output without asking (`-y`) when you run one file | Open: waiting for the maintainer to choose between asking first and saving under a new name ([dashboard-first-ai-agent.md](./dashboard-first-ai-agent.md)) |
| Downloads, CLI commands and finished queue tasks never reached the activity log | Fixed: `core/catalog/activity.py` logs them ([cli-dashboard-sync.md](./cli-dashboard-sync.md)) |
| A plugin written like the README example made every `max` command fail | Fixed in `plugins/manager.py` |
| A mistyped group (`max vidoe ...`) went to the AI agent | Fixed: "Did you mean 'video'?" |

## Current Active Plans

| Plan | Status | Priority | What's left |
|------|--------|----------|-------------|
| [agent-phase3-pc-vision-models.md](./agent-phase3-pc-vision-models.md) | In Progress | P1 | 3b waits for a decision: a shell (off by default), stopping processes, a cheaper model, agent evals |
| [dashboard-first-ai-agent.md](./dashboard-first-ai-agent.md) | In Progress | P1 | FFmpeg overwrite (before 1.0); `images` batch options; the `ai` group in the catalog; small local models; onboarding, friendlier errors, an installer |
| [cli-dashboard-sync.md](./cli-dashboard-sync.md) | In Progress | P1 | Download page logging (before 1.0); one activity record for every caller; `max history` |
| [dashboard-design-system.md](./dashboard-design-system.md) | In Progress | P1 | Polish: TUI rule checks in `check_rules.py`, snapshot tests, footer keys, light theme, path autocomplete, Run again in History, results list per page, keyboard parity |
| [file-undo-transaction-log.md](./file-undo-transaction-log.md) | In Progress | P2 | 11 mypy errors in `common/transaction_log.py` (type-only) |
| [paths-from-anywhere.md](./paths-from-anywhere.md) | In Progress | P2 | Path audit for `images` and non-catalog commands; per-command last folder; resolved paths in confirmations |
| [user-workflows-aliases.md](./user-workflows-aliases.md) | Draft | P1 | Not started; post-1.0 idea |
| [feature-packs.md](./feature-packs.md) | Draft (idea) | P2 | Not started; post-1.0 idea |

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
