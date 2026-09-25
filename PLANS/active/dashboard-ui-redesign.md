# Plan: Dashboard UI and UX Redesign

**Status:** Draft (idea captured; plan it later)
**Priority:** P1
**Updated:** 2026-09-26

## Goal

A dashboard that feels like one designed app: every page scrolls, every page follows the same layout rules, and every command form offers the same options as the CLI command.

## The idea (maintainer, 2026-09-26)

- Make the dashboard friendlier, with better UX and UI.
- Pages don't show a scrollbar, so you can't move up and down through long content.
- There's no standard design, and that causes UI problems.
- Forms should expose all the options the command supports, so users can choose.

## What we know today

- Before 2026-09-26, 7 of the 9 pages couldn't scroll at 80x16; only Home and Download could. Fixed; see the task list.
- Each panel sets its own spacing, colours and CSS. `app.py` holds one large shared CSS block, and some panels add their own.
- Dashboard forms show a subset of each command's options. The drift test (`tests/interface/tui/test_preset_drift.py`) checks defaults, not coverage.

## Ideas to plan later

- [ ] A small design standard for the TUI: layout grid, spacing scale, colour tokens, a card component, form field components, empty and loading states, and error display. Write it down in `docs/` or a skill.
- [x] Every page scrolls: `#content > *` has `overflow-y: auto`, tables keep `min-height: 8`, and the Config and Chat inner scroll areas keep `min-height: 6`. `test_every_page_scrolls_in_a_small_terminal` checks all nine pages at 80x16 (2026-09-26).
- [ ] Build forms from the command catalog (see `dashboard-first-ai-agent.md`, Step 2):
  - Every CLI option appears.
  - Advanced options fold away.
  - Help text sits under each field.
- [ ] A consistent page header (title, short description, primary action) and a footer showing keys.
- [ ] Keyboard and mouse parity, with visible focus.
- [ ] Screenshot or snapshot tests for each page, to catch layout regressions.

## Related

- `tui-bugfix-and-ux-improvements.md` (existing bugs), `dashboard-home-analytics-redesign.md`, `interactive-tui-expansion.md`.
- The `textual-builder` skill in `.claude/skills/` for Textual 8 patterns.
