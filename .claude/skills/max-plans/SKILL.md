---
name: max-plans
description: Create, update, complete, or defer plans in the Max CLI PLANS/ folder so plan status, checkboxes, and the active index stay in sync with the code. Use when starting a planned feature, finishing one, deferring work, or when asked about project status or roadmap.
---

# PLANS workflow

```
PLANS/
├── active/      # plans being worked on + README.md index table
├── completed/   # finished plans
├── deferred/    # parked plans, each with a reason
└── docs/        # design docs (e.g. plugins.md)
```

## Starting work
1. Read `PLANS/active/README.md` and every plan related to the task.
2. If the plan says "Completed" but its checkboxes are open, **verify against the code** before trusting either one. Grep for the commands, classes and tests it describes.
3. If there's no plan and the task spans several files or sessions, create `PLANS/active/<kebab-name>.md`:

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

Then add a row to the table in `PLANS/active/README.md`.

## During work
- Tick `[x]` a box only after its code, tests and docs exist.
- Record a design choice that differs from the plan under **Decisions**.

## Finishing
1. Every box is ticked, or explained under Decisions.
2. Set `**Status:** Completed` and update the `**Updated:**` date.
3. `git mv PLANS/active/<plan>.md PLANS/completed/`.
4. Remove its row from `PLANS/active/README.md`.

## Deferring
When the plan is blocked or out of scope, or type-checker fights exceed their value (AGENTS.md section 5):
1. Mark the open tasks `[D]`.
2. Add a `## Deferred because` section that states the blocker.
3. `git mv` the plan to `PLANS/deferred/` and update the index.

## Status questions
When asked "what's left?" or "what's the status?", report from the code and the checkboxes together. Name each place where they disagree.
