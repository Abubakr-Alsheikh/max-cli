# Plan: Run Commands on Any File or Folder

**Status:** In Progress
**Priority:** P2
**Updated:** 2026-10-04

## Goal

You can point any command at any file or folder, in the CLI and in the dashboard, without first moving into that folder.

## The idea (maintainer, 2026-09-26)

"I should be in the same folder to apply the scripts to the folder or file." Make it easy to run a command on any path, in both the command line and the interface.

## What we know today

- Most commands take a path argument, but several default to `.` (current folder). The docs and examples assume you `cd` first.
- Some commands behave badly with `.`. Hardening fixed `images compress` writing to `./_optimized`; others may have similar edge cases.
- The dashboard asks you to type or paste paths. The Download panel's "Browse" button only shows a hint.
- 2026-10-04: most of this is out of date. Every Browse button opens `widgets/path_picker.PathPicker`; batch commands take files, folders and patterns from anywhere (`core/catalog/batch.py`), and catalog paths expand `~` (`catalog/runner.py:45`).

## Ideas to plan later

- [ ] Audit every command for path handling (partly done: the batch actions and `catalog.runner.coerce_args` expand `~` and take absolute paths; `images` and the non-catalog commands haven't been audited): absolute and relative paths, `~`, quotes, spaces, Windows drive letters, and folders versus single files. Add tests for each case.
- [ ] Shared path resolving in `common/` (expand `~`, resolve, validate, give a friendly "not found, did you mean ..." error), used by every command.
- [x] Dashboard: a real file and folder picker with recent folders and pins (`widgets/path_picker.py`, PR #42).
- [ ] CLI: shell completion for paths (Typer's `--install-completion` exists), and remembering the last folder used per command where it helps.
- [x] Agent: `agent/scope.PathScope` takes folders named in a request and the download folder, and `recent_activity` and `find_files` find recent files (`dashboard-first-ai-agent.md`).
- [ ] Safety: destructive commands show the resolved absolute path in their confirmation.

## Related

- `dashboard-ui-redesign.md` (the picker component), `dashboard-first-ai-agent.md`.
